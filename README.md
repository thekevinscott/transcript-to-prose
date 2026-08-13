# transcript-to-prose

Dictate on the left, get polished prose plus extracted points on the right.
Runs on a machine in your tailnet and is reachable from any other device on it.

The server binds to the tailnet interface only, so the URL is
`http://<host>:8788`, where `<host>` is that machine's MagicDNS name or the
address from `tailscale ip -4`. It prints the bound address on startup.

## What it is

- A stdlib Python HTTP server (`http.server`, no web framework).
- One dependency: `claude-agent-sdk`, which drives the local `claude` CLI.
- One static page of vanilla JS. No build step, no bundler, no npm.

Typing in the left textarea debounces, then POSTs to `/api/run`, which fans the
transcript out across the enabled output panels concurrently. Results stream
back as newline-delimited JSON; the prose panel fills in token by token while
the extraction panels are still working.

## Where to make changes

Almost everything lives in **`app/config.py`**. The browser renders its sliders
and panels from `/api/config`, which is generated from that file, so the
frontend needs no edits when you change either registry.

**Add a slider** — append to `CONTROLS`. Each entry is a list of buckets; a
bucket is a UI label plus the directive injected into the prompt when selected.
`"kind": "select"` gives a dropdown instead of a slider. `"panels"` restricts
which panels a control affects (omit it and it applies to all).

**Add an output panel** — append to `PANELS`. `"kind": "prose"` renders as text
(set `"stream": True` for token streaming); `"kind": "list"` expects one `- `
item per line and renders a list. Each panel is an independent `claude` call
with its own system prompt, and may override `"model"`.

Other files, in rough order of how often you'll touch them:

| File | Role |
|---|---|
| `app/config.py` | Controls, panels, prompts, defaults |
| `static/app.js` | UI behaviour: debounce, streaming, persistence |
| `static/style.css` | Appearance |
| `app/runner.py` | Fan-out, prompt assembly, list parsing |
| `app/claude.py` | The `claude-agent-sdk` call |
| `app/server.py` | Routing and the NDJSON stream |

## Behaviour worth knowing

- Runs fire 1.4s after you stop typing, and only above 40 characters. Cmd+Enter
  forces a run; changing a slider triggers one immediately.
- An identical transcript + settings won't re-run. In-flight requests are
  aborted when you keep typing.
- Transcript, slider positions, and panel toggles persist in `localStorage`.
- The Claude call runs with no tools and `setting_sources=[]`, so your global
  `~/.claude/CLAUDE.md` does not leak into the prose style.

## Running it

Managed by systemd, already enabled and started:

```
systemctl --user status transcript-to-prose
systemctl --user restart transcript-to-prose   # after editing config.py
journalctl --user -u transcript-to-prose -f
```

Or in the foreground: `uv run python main.py`

Binds to the tailnet IP only (auto-detected via `tailscale ip -4`), so it is
not exposed to the LAN. Env overrides: `TTP_HOST`, `TTP_PORT`, `TTP_MODEL`,
`TTP_DEBOUNCE_MS`, `TTP_MIN_CHARS`.
