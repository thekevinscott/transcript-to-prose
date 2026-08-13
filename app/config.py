"""Everything you are likely to change while iterating lives in this file.

Two registries drive both the server and the UI:

  CONTROLS  -- the knobs along the bottom of the page. Each control turns a
               numeric/enum value into a plain-English directive that gets
               injected into the prompt.
  PANELS    -- the output boxes on the right. Each panel is one `claude` call.

The frontend renders itself from these definitions (served at /api/config), so
adding a slider or a new output panel means editing this file only.
"""

import os

# Model for every panel unless the panel overrides it. None = whatever the
# `claude` CLI is configured to use by default.
MODEL = os.environ.get("TTP_MODEL") or None

# Milliseconds of silence in the left textarea before a run fires.
DEBOUNCE_MS = int(os.environ.get("TTP_DEBOUNCE_MS", "1400"))

# Don't bother calling out for fragments shorter than this.
MIN_CHARS = int(os.environ.get("TTP_MIN_CHARS", "40"))


# --------------------------------------------------------------------------
# Controls
# --------------------------------------------------------------------------
# kind "slider": `scale` is a list of buckets; the slider position picks one.
# kind "select": `scale` is a list of buckets; the dropdown picks one directly.
#
# Each bucket is {"label": shown in the UI, "directive": injected into prompts}.
# `panels` limits a control to certain panel ids; omit it to apply everywhere.

CONTROLS = [
    {
        "id": "length",
        "label": "Length",
        "kind": "slider",
        "default": 2,
        "panels": ["prose"],
        "scale": [
            {"label": "Terse", "directive": "Cut hard. Aim for roughly a third of the transcript's length. Keep only what carries meaning."},
            {"label": "Compact", "directive": "Tighten noticeably. Aim for about half the transcript's length."},
            {"label": "Balanced", "directive": "Keep roughly the transcript's length. Trim filler, don't cut substance."},
            {"label": "Expansive", "directive": "Let ideas breathe. Longer sentences and fuller transitions are fine; you may exceed the transcript's length."},
            {"label": "Thorough", "directive": "Develop each point fully, spelling out implications the speaker gestured at. Expect to run well past the transcript's length."},
        ],
    },
    {
        "id": "fidelity",
        "label": "Fidelity",
        "kind": "slider",
        "default": 3,
        "panels": ["prose"],
        "scale": [
            {"label": "Free", "directive": "Rewrite freely. Reorganise, merge, and rephrase to make the argument land; the speaker's phrasing is raw material, not a constraint."},
            {"label": "Loose", "directive": "Rewrite for clarity. Reorder where it helps, and substitute better words where the speaker's choice was imprecise."},
            {"label": "Faithful", "directive": "Preserve the speaker's wording and running order wherever it works. Change things only to fix clarity, grammar, or flow."},
            {"label": "Close", "directive": "Stay close to the speaker's words. Keep their vocabulary and sentence order; mostly you are removing disfluencies and repairing grammar."},
            {"label": "Verbatim", "directive": "Change as little as possible. Strip filler words, false starts, and repetitions; fix punctuation and sentence boundaries. Do not substitute synonyms or reorder anything."},
        ],
    },
    {
        "id": "register",
        "label": "Register",
        "kind": "slider",
        "default": 2,
        "panels": ["prose"],
        "scale": [
            {"label": "Casual", "directive": "Write the way a smart person talks: contractions, short sentences, plain words."},
            {"label": "Conversational", "directive": "Keep it relaxed and readable. Contractions are fine."},
            {"label": "Neutral", "directive": "Write in clear standard prose. No slang, no stiffness."},
            {"label": "Professional", "directive": "Write for a work audience: measured, precise, no colloquialisms."},
            {"label": "Formal", "directive": "Write formally. Full forms rather than contractions, careful and impersonal phrasing."},
        ],
    },
    {
        "id": "structure",
        "label": "Structure",
        "kind": "select",
        "default": 0,
        "panels": ["prose"],
        "scale": [
            {"label": "Flowing", "directive": "Produce continuous prose in paragraphs. No headings, no bullets."},
            {"label": "Paragraphs", "directive": "Break into short, clearly separated paragraphs, one idea each. No headings, no bullets."},
            {"label": "Sectioned", "directive": "Organise under short markdown headings, with prose beneath each. Use bullets only where the content is genuinely a list."},
            {"label": "Bulleted", "directive": "Produce a tight bulleted outline rather than paragraphs. Each bullet is one complete thought."},
        ],
    },
]


# --------------------------------------------------------------------------
# Panels
# --------------------------------------------------------------------------
# kind "prose" -> rendered as text, streams token by token.
# kind "list"  -> model returns one item per line, rendered as a list.
#
# `template` gets .format(transcript=..., directives=...).

_ANTI_PREAMBLE = (
    "Output only the result. No preamble, no sign-off, no commentary about "
    "what you did, no markdown code fences around the whole thing."
)

PANELS = [
    {
        "id": "prose",
        "label": "Prose",
        "kind": "prose",
        "default_on": True,
        "stream": True,
        "system": (
            "You turn spoken dictation into written prose. The input is a raw "
            "speech-to-text transcript: it has filler words, false starts, "
            "repetition, run-ons, and mangled punctuation. Your job is to "
            "produce what the speaker would have written if they had been "
            "writing instead of talking.\n\n"
            "Rules that always hold:\n"
            "- Never invent facts, names, numbers, or claims the speaker did not make.\n"
            "- Never add a conclusion, summary, or call to action they did not say.\n"
            "- If a passage is garbled beyond repair, render your best reading of it rather than dropping it.\n"
            "- Transcription errors are common; silently correct obvious mis-hearings when context makes the intended word clear.\n"
            f"- {_ANTI_PREAMBLE}"
        ),
        "template": (
            "Rewrite the transcript below as prose.\n\n"
            "{directives}\n\n"
            "<transcript>\n{transcript}\n</transcript>"
        ),
    },
    {
        "id": "points",
        "label": "Salient points",
        "kind": "list",
        "default_on": True,
        "system": (
            "You extract the load-bearing points from spoken dictation. "
            "Output one point per line, each starting with '- '. No headings, "
            "no numbering, no preamble, no closing line. Each point is a single "
            "complete sentence in your own words. Never invent anything the "
            "speaker did not say."
        ),
        "template": (
            "List the salient points from the transcript below: the claims, "
            "decisions, and arguments that carry the meaning. At most 8. "
            "Order them by importance, not by when they were said.\n\n"
            "<transcript>\n{transcript}\n</transcript>"
        ),
    },
    {
        "id": "facts",
        "label": "Facts & figures",
        "kind": "list",
        "default_on": True,
        "system": (
            "You extract concrete, checkable facts from spoken dictation: "
            "numbers, dates, names, places, quantities, and specific "
            "commitments. Output one per line, each starting with '- '. Quote "
            "the speaker's own figures exactly. If the transcript contains no "
            "such facts, output nothing at all. Never infer or estimate."
        ),
        "template": (
            "Extract the concrete facts from the transcript below.\n\n"
            "<transcript>\n{transcript}\n</transcript>"
        ),
    },
    {
        "id": "questions",
        "label": "Open threads",
        "kind": "list",
        "default_on": False,
        "system": (
            "You identify what a piece of spoken dictation leaves unresolved: "
            "questions the speaker raised and did not answer, assertions that "
            "need support, and next actions they implied. Output one per line, "
            "each starting with '- '. If nothing is unresolved, output nothing."
        ),
        "template": (
            "What does the transcript below leave open? At most 6 items.\n\n"
            "<transcript>\n{transcript}\n</transcript>"
        ),
    },
]


# --------------------------------------------------------------------------
# Helpers used by the runner and the /api/config endpoint
# --------------------------------------------------------------------------


def panel_by_id(panel_id):
    for panel in PANELS:
        if panel["id"] == panel_id:
            return panel
    return None


def bucket_for(control, value):
    """Clamp `value` to a valid index into the control's scale."""
    try:
        index = int(value)
    except (TypeError, ValueError):
        index = control["default"]
    index = max(0, min(len(control["scale"]) - 1, index))
    return control["scale"][index]


def directives_for(panel_id, values):
    """Build the '{directives}' block for a panel from the UI's control values."""
    lines = []
    for control in CONTROLS:
        if "panels" in control and panel_id not in control["panels"]:
            continue
        lines.append("- " + bucket_for(control, values.get(control["id"], control["default"]))["directive"])
    if not lines:
        return ""
    return "Follow these directives:\n" + "\n".join(lines)


def client_config():
    """The subset of this file the browser needs in order to render itself."""
    return {
        "debounce_ms": DEBOUNCE_MS,
        "min_chars": MIN_CHARS,
        "controls": [
            {
                "id": c["id"],
                "label": c["label"],
                "kind": c["kind"],
                "default": c["default"],
                "panels": c.get("panels"),
                "scale": [b["label"] for b in c["scale"]],
            }
            for c in CONTROLS
        ],
        "panels": [
            {
                "id": p["id"],
                "label": p["label"],
                "kind": p["kind"],
                "default_on": p.get("default_on", True),
            }
            for p in PANELS
        ],
    }
