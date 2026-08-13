"""Thin wrapper around claude-agent-sdk.

One function, `ask`, which sends a single prompt and yields text as it arrives.
No tools, no filesystem access, no user/project settings — this is a pure
text-in/text-out call so the app's prompts are the only thing steering output.
"""

import dataclasses

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    StreamEvent,
    TextBlock,
    query,
)

_OPTION_FIELDS = {f.name for f in dataclasses.fields(ClaudeAgentOptions)}


def _options(**kwargs):
    """Build options, dropping any field this SDK version doesn't have."""
    return ClaudeAgentOptions(**{k: v for k, v in kwargs.items() if k in _OPTION_FIELDS and v is not None})


async def ask(prompt, system=None, model=None, stream=False):
    """Yield chunks of Claude's reply.

    With stream=False you get exactly one chunk: the whole reply. With
    stream=True you get text deltas as the model produces them.
    """
    options = _options(
        system_prompt=system,
        model=model,
        max_turns=1,
        allowed_tools=[],
        disallowed_tools=["Bash", "Read", "Write", "Edit", "WebSearch", "WebFetch", "Task"],
        permission_mode="bypassPermissions",
        # Do not load ~/.claude/CLAUDE.md or any project settings; they would
        # bleed the user's coding preferences into the prose.
        setting_sources=[],
        include_partial_messages=bool(stream),
    )

    streamed_any = False
    async for message in query(prompt=prompt, options=options):
        if stream and isinstance(message, StreamEvent):
            event = message.event or {}
            if event.get("type") == "content_block_delta":
                delta = event.get("delta") or {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    streamed_any = True
                    yield delta["text"]
        elif isinstance(message, AssistantMessage):
            if stream and streamed_any:
                # Already emitted as deltas; don't duplicate.
                continue
            for block in message.content:
                if isinstance(block, TextBlock) and block.text:
                    yield block.text


async def ask_text(prompt, system=None, model=None):
    """Non-streaming convenience wrapper returning the whole reply."""
    parts = []
    async for chunk in ask(prompt, system=system, model=model, stream=False):
        parts.append(chunk)
    return "".join(parts).strip()
