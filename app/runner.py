"""Fan a transcript out across the configured panels, concurrently.

Each panel is one independent `claude` call. Results are emitted as they
arrive rather than gathered up, so the prose starts appearing while the
extraction panels are still thinking.
"""

import asyncio
import re

from . import config
from .claude import ask


class ClientGone(Exception):
    """Raised by the emit callback when the browser has disconnected."""


_FENCE = re.compile(r"^```[a-zA-Z]*\n(.*)\n```$", re.DOTALL)
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def _clean_prose(text):
    text = text.strip()
    match = _FENCE.match(text)
    if match:
        text = match.group(1).strip()
    return text


def _parse_list(text):
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("```"):
            continue
        stripped = _BULLET.sub("", line).strip()
        if stripped:
            items.append(stripped)
    return items


def _build_prompt(panel, transcript, values):
    return panel["template"].format(
        transcript=transcript.strip(),
        directives=config.directives_for(panel["id"], values),
    )


async def _run_panel(panel, transcript, values, emit):
    panel_id = panel["id"]
    emit({"type": "start", "panel": panel_id})
    prompt = _build_prompt(panel, transcript, values)
    streaming = panel["kind"] == "prose" and panel.get("stream", False)
    parts = []
    try:
        async for chunk in ask(
            prompt,
            system=panel.get("system"),
            model=panel.get("model") or config.MODEL,
            stream=streaming,
        ):
            parts.append(chunk)
            if streaming:
                emit({"type": "delta", "panel": panel_id, "text": chunk})
    except ClientGone:
        raise
    except Exception as exc:  # surface the failure in the panel, don't kill the run
        emit({"type": "error", "panel": panel_id, "message": f"{type(exc).__name__}: {exc}"})
        return

    text = "".join(parts)
    if panel["kind"] == "list":
        emit({"type": "done", "panel": panel_id, "items": _parse_list(text)})
    else:
        emit({"type": "done", "panel": panel_id, "text": _clean_prose(text)})


async def run(payload, emit):
    """Run every requested panel. `emit` is a sync callable taking a dict."""
    transcript = (payload.get("transcript") or "").strip()
    values = payload.get("controls") or {}
    requested = payload.get("panels")

    if requested is None:
        panels = [p for p in config.PANELS if p.get("default_on", True)]
    else:
        panels = [p for p in config.PANELS if p["id"] in requested]

    if not transcript or not panels:
        emit({"type": "complete"})
        return

    try:
        await asyncio.gather(*(_run_panel(p, transcript, values, emit) for p in panels))
    except ClientGone:
        return
    emit({"type": "complete"})
