# Claude Code Widget

A macOS desktop widget that shows your Claude Code usage at a glance — rate limit status, active sessions with live agent messages, streak, and a one-click dashboard.

![Widget preview showing Claude Code stats]

## What it shows

**Medium widget**
- Rate limit status with plain-English advice ("Work as normal", "Pace yourself", "Take a break")
- 5-hour window progress bar + time remaining
- Active coding sessions — directory name, model, and the agent's current message
- 🔥 Streak

**Small widget**
- Status at a glance
- Time remaining in window
- Streak

Clicking the widget opens the full dashboard at `localhost:7823`.

---

## Requirements

| Requirement | Version |
|---|---|
| macOS | Sonoma 14+ |
| Xcode | 15+ (free, from App Store) |
| Python | 3.9+ (ships with macOS) |
| Apple ID | Free account is fine |

No Claude API key needed — the widget reads local Claude Code data from `~/.claude/`.

---

## Quick setup (5 minutes)

### 1. Clone and generate the project

```bash
git clone https://github.com/YOUR_USERNAME/ClaudeWidget.git
cd ClaudeWidget
python3 setup.py   # generates Xcode files + installs widget.py to ~/.claude/
```

You can clone it **anywhere** — the project uses relative paths internally and installs the dashboard script to `~/.claude/` automatically.

This writes all Xcode source files.

### 2. Open in Xcode

```bash
open ClaudeWidget.xcodeproj
```

### 3. Sign both targets

In Xcode:
1. Click **ClaudeWidget** in the project navigator (top item)
2. Select the **ClaudeWidget** target → **Signing & Capabilities** → set Team to your Apple ID
3. Repeat for the **ClaudeWidgetExtension** target

A free Apple ID works — no paid developer account needed.

### 4. Build & run

Press **Cmd+R** (or Product → Run).

A small window appears confirming the widget is installed.

### 5. Add the widget to your desktop

Right-click your desktop → **Edit Widgets** → search **"Claude"** → drag it to your desktop.

Both **Small** and **Medium** sizes are available.

---

## Dashboard

The widget comes with a full usage dashboard:

```bash
python3 ~/.claude/widget.py
# Opens http://localhost:7823 automatically
```

Or click the widget to launch it directly.

The dashboard shows 30-day activity, session history, model usage, top projects, and rate limit details — all auto-refreshed every 15 seconds.

---

## Development workflow

After editing source files:

```bash
make build    # kill app → build → install → done
make dev      # same + re-launch the host app
make reset    # full reset (use after structural widget changes)
make clean    # clean build folder
```

### When do you need `make reset`?

Only when the widget view structure changes significantly (e.g. adding new data fields to `ClaudeEntry`). For normal UI tweaks, `make build` is enough.

### Manual workflow (Xcode only)

1. Edit source in VS Code or Xcode
2. In Xcode: **Cmd+B** (Build)
3. The post-build script automatically:
   - Copies the app to `~/Applications/`
   - Kills `WidgetKitService` so macOS picks up the new binary
4. The widget reloads within a few seconds

If the widget seems stuck showing old content, run `make reset` then re-add it.

---

## File overview

```
ClaudeWidget/
├── setup.py                    ← Run once to generate Xcode project
├── make_icon.py                ← Regenerate the app icon
├── Makefile                    ← Dev shortcuts
├── ClaudeWidgetApp/
│   ├── ClaudeWidgetApp.swift   ← Host app entry, URL handler
│   ├── ContentView.swift       ← App window UI
│   ├── WidgetCenterBridge.swift← Triggers widget refresh
│   └── AppIcon.icns            ← App icon (pre-generated)
├── ClaudeWidgetExtension/
│   └── ClaudeWidget.swift      ← All widget logic + UI
└── ~/.claude/
    ├── history.jsonl           ← Claude Code reads/writes this
    ├── stats-cache.json        ← Token usage by model
    ├── projects/               ← Per-project conversations
    └── widget.py               ← Dashboard server
```

---

## Privacy

All data is local — `~/.claude/` on your own machine. Nothing is sent anywhere.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Widget shows blank | Run `make reset`, then re-add widget from desktop |
| Data shows 0s | Check that `~/.claude/history.jsonl` exists (use Claude Code first) |
| "No active sessions" | Sessions show if a project file was modified in the last 5 minutes |
| Dashboard won't open | Run `python3 ~/.claude/widget.py` manually to see any errors |
| Build fails with signing error | Make sure both targets have a Team set in Signing & Capabilities |

---

## License

Personal use. Claude and Claude Code are trademarks of Anthropic.
