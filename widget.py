#!/usr/bin/env python3
"""Claude Code Usage Dashboard  —  personal use only.
Run: python3 ~/.claude/widget.py  →  opens http://localhost:7823
"""

import json, sys, threading, webbrowser, signal
from datetime import datetime, timedelta
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

CLAUDE_DIR   = Path.home() / ".claude"
HISTORY_FILE = CLAUDE_DIR / "history.jsonl"
STATS_FILE   = CLAUDE_DIR / "stats-cache.json"
PORT = 7823

# ── Data ────────────────────────────────────────────────────────

def parse_history():
    if not HISTORY_FILE.exists():
        return []
    msgs = []
    with open(HISTORY_FILE, errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: msgs.append(json.loads(line))
            except: pass
    return sorted(msgs, key=lambda m: m.get("timestamp", 0))

def parse_stats():
    if not STATS_FILE.exists(): return {}
    try:
        with open(STATS_FILE) as f: return json.load(f)
    except: return {}

def compute_data():
    messages = parse_history()
    stats    = parse_stats()
    now      = datetime.now()
    today    = now.date()
    week_start = today - timedelta(days=today.weekday())

    by_date    = defaultdict(list)
    by_session = defaultdict(list)
    by_project = defaultdict(int)
    hour_dist  = defaultdict(int)

    for msg in messages:
        ts  = msg.get("timestamp", 0) / 1000
        dt  = datetime.fromtimestamp(ts)
        sid = msg.get("sessionId", "unknown")
        prj = msg.get("project", "unknown")
        by_date[dt.date()].append(msg)
        by_session[sid].append(msg)
        by_project[prj] += 1
        hour_dist[dt.hour] += 1

    cur_sid   = messages[-1].get("sessionId") if messages else None
    cur_msgs  = by_session.get(cur_sid, [])
    session_start = None
    if cur_msgs:
        session_start = datetime.fromtimestamp(cur_msgs[0]["timestamp"] / 1000)

    # 5-hour window
    cutoff_5h   = now - timedelta(seconds=5*3600)
    msgs_5h     = [m for m in messages
                   if datetime.fromtimestamp(m.get("timestamp",0)/1000) >= cutoff_5h]
    first_in_window = None
    reset_at        = None
    if msgs_5h:
        first_in_window = datetime.fromtimestamp(msgs_5h[0]["timestamp"] / 1000)
        reset_at = first_in_window + timedelta(seconds=5*3600)

    time_left_str = "Full capacity"
    window_pct    = 0.0
    reset_at_iso  = None
    if reset_at and reset_at > now:
        secs_left = (reset_at - now).total_seconds()
        h = int(secs_left // 3600)
        m = int((secs_left % 3600) // 60)
        s = int(secs_left % 60)
        time_left_str = f"{h}h {m:02d}m {s:02d}s"
        elapsed       = (now - first_in_window).total_seconds()
        window_pct    = min(elapsed / (5*3600), 1.0)
        reset_at_iso  = reset_at.isoformat()
    else:
        window_pct = 0.0

    # 30-day chart
    daily_activity = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        daily_activity.append({"date": d.isoformat(), "count": len(by_date.get(d, []))})

    # top projects
    top_projects = sorted(by_project.items(), key=lambda x: x[1], reverse=True)[:8]
    top_projects = [{"project": p.replace(str(Path.home()), "~"), "count": c}
                    for p, c in top_projects]

    # recent sessions
    sessions_list = []
    for sid, msgs in by_session.items():
        if not msgs: continue
        t0 = datetime.fromtimestamp(msgs[0]["timestamp"] / 1000)
        t1 = datetime.fromtimestamp(msgs[-1]["timestamp"] / 1000)
        prj = msgs[-1].get("project", "").replace(str(Path.home()), "~")
        sessions_list.append({
            "sessionId":    sid[:8],
            "messageCount": len(msgs),
            "start":        t0.strftime("%b %d %H:%M"),
            "durationMin":  round((t1 - t0).total_seconds() / 60),
            "project":      prj,
        })
    sessions_list.sort(key=lambda s: s["start"], reverse=True)

    today_count = len(by_date.get(today, []))
    week_count  = sum(len(by_date.get(today - timedelta(days=i), [])) for i in range(7))

    # streak
    streak = 0
    d = today
    while by_date.get(d):
        streak += 1
        d -= timedelta(days=1)

    peak_hour  = max(hour_dist, key=lambda h: hour_dist[h]) if hour_dist else 0
    peak_label = datetime(2000,1,1,peak_hour).strftime("%-I %p")

    # active sessions (projects modified <5 min ago)
    active_sessions = []
    projects_dir = CLAUDE_DIR / "projects"
    if projects_dir.exists():
        cutoff_5min = now - timedelta(minutes=5)
        for proj_dir in sorted(projects_dir.iterdir()):
            if not proj_dir.is_dir(): continue
            for f in proj_dir.glob("*.jsonl"):
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime >= cutoff_5min:
                    proj_name = proj_dir.name \
                        .replace(f"-Users-{Path.home().name}-", "~/") \
                        .replace("-", "/")
                    active_sessions.append({
                        "project": proj_name,
                        "lastSeen": mtime.strftime("%H:%M:%S"),
                    })

    model_usage = {
        k: {
            "inputTokens":  v.get("inputTokens", 0),
            "outputTokens": v.get("outputTokens", 0),
            "cacheRead":    v.get("cacheReadInputTokens", 0),
        }
        for k, v in stats.get("modelUsage", {}).items()
    }

    return {
        "nowIso":          now.isoformat(),
        "todayCount":      today_count,
        "weekCount":       week_count,
        "totalMessages":   len(messages),
        "totalSessions":   len(by_session),
        "firstMessage":    (datetime.fromtimestamp(messages[0]["timestamp"]/1000)
                            .strftime("%b %d, %Y") if messages else "—"),
        "streak":          streak,
        "peakHour":        peak_label,
        "currentSession":  {
            "id":           cur_sid[:8] if cur_sid else "—",
            "messageCount": len(cur_msgs),
            "start":        session_start.strftime("%H:%M") if session_start else "—",
            "project":      (cur_msgs[-1].get("project","").replace(str(Path.home()),"~")
                             if cur_msgs else "—"),
        },
        "rateLimit": {
            "timeLeft":    time_left_str,
            "windowPct":   round(window_pct * 100, 1),
            "msgs5h":      len(msgs_5h),
            "resetAtIso":  reset_at_iso,
            "windowStart": first_in_window.strftime("%H:%M") if first_in_window else "—",
        },
        "dailyActivity":  daily_activity,
        "topProjects":    top_projects,
        "hourDist":       [hour_dist.get(h, 0) for h in range(24)],
        "recentSessions": sessions_list[:14],
        "modelUsage":     model_usage,
        "activeSessions": active_sessions,
    }

# ── HTML ─────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Claude Code · Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
/* ── Design tokens ─────────────────────────────── */
:root {
  --bg:         #0f0d0c;
  --surface:    #161310;
  --card:       #1c1916;
  --card-hover: #211e1a;
  --border:     #2a2520;
  --text:       #e8dfd0;
  --muted:      #6b635a;
  --dim:        #38332e;
  --orange:     #cc7b4a;
  --amber:      #e8a87c;
  --amber-dim:  rgba(232,168,124,.12);
  --purple:     #8a7ab8;
  --green:      #5fa882;
  --red:        #b85a5a;
  --blue:       #5a96c4;
  --r:          12px;
  --font:       -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --mono:       'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--bg);color:var(--text);font-family:var(--font);font-size:14px;line-height:1.5;min-height:100%}
body{padding:24px 28px;max-width:1380px;margin:0 auto}

/* scrollbar */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}

/* ── Header ────────────────────────────────────── */
.header{
  display:flex;align-items:center;justify-content:space-between;
  margin-bottom:24px;flex-wrap:wrap;gap:12px;
}
.logo{display:flex;align-items:center;gap:11px}
.diamond{
  width:34px;height:34px;border-radius:9px;flex-shrink:0;
  background:linear-gradient(135deg,#b86238,var(--amber));
  display:flex;align-items:center;justify-content:center;
  font-size:16px;color:#fff;
  box-shadow:0 4px 16px rgba(204,123,74,.35);
}
.logo-name{font-size:17px;font-weight:650;letter-spacing:-.3px;color:var(--text)}
.logo-sub{font-size:11px;color:var(--muted);margin-top:1px}
.header-right{text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:4px}
.clock{font-family:var(--mono);font-size:13px;color:var(--muted);letter-spacing:.3px}
.live-pill{
  display:inline-flex;align-items:center;gap:5px;
  background:rgba(95,168,130,.13);color:var(--green);
  font-size:10px;font-weight:700;letter-spacing:.6px;
  padding:2px 9px;border-radius:99px;border:1px solid rgba(95,168,130,.2);
}
.live-dot{width:5px;height:5px;border-radius:50%;background:var(--green);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

/* ── Grids ─────────────────────────────────────── */
.row{display:grid;gap:12px;margin-bottom:12px}
.row4{grid-template-columns:repeat(4,1fr)}
.row2{grid-template-columns:1fr 1fr}
.row3{grid-template-columns:2fr 1fr 1fr}
.row21{grid-template-columns:2fr 1fr}
.row12{grid-template-columns:1fr 2fr}
@media(max-width:960px){.row4,.row3{grid-template-columns:repeat(2,1fr)}.row21,.row12{grid-template-columns:1fr}}
@media(max-width:580px){.row4,.row2{grid-template-columns:1fr}}

/* ── Card ──────────────────────────────────────── */
.card{
  background:var(--card);border:1px solid var(--border);border-radius:var(--r);
  padding:18px 20px;position:relative;overflow:hidden;
  transition:background .15s,border-color .15s;
}
.card:hover{background:var(--card-hover);border-color:#38332e}
.card-stripe{
  position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,var(--orange),var(--amber));
  opacity:.55;
}
.card-label{
  font-size:10px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;
  color:var(--muted);margin-bottom:7px;
}
.card-value{
  font-family:var(--mono);font-size:34px;font-weight:800;line-height:1;
  letter-spacing:-1.5px;margin-bottom:4px;
}
.card-sub{font-size:11px;color:var(--muted)}
.v-orange{color:var(--amber)}
.v-purple{color:var(--purple)}
.v-green {color:var(--green)}
.v-blue  {color:var(--blue)}
.card-title{font-size:12px;font-weight:650;color:var(--text);margin-bottom:14px;letter-spacing:-.1px}

/* ── Rate Limit hero card ──────────────────────── */
.rl-card{padding:20px 24px}
.rl-inner{display:flex;align-items:center;gap:28px;flex-wrap:wrap}
.rl-ring-wrap{flex-shrink:0;position:relative;width:108px;height:108px}
.rl-ring-wrap svg{position:absolute;inset:0;width:100%;height:100%}
.rl-center{
  position:absolute;inset:0;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:1px;
}
.rl-pct{font-family:var(--mono);font-size:19px;font-weight:800;color:var(--text)}
.rl-pct-label{font-size:8px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:var(--muted)}
.rl-info{flex:1;min-width:180px}
.rl-time{font-family:var(--mono);font-size:26px;font-weight:800;line-height:1.1;letter-spacing:-1px;color:var(--amber)}
.rl-time.full{color:var(--green)}
.rl-detail{font-size:11px;color:var(--muted);margin-top:6px;line-height:1.8}
.rl-detail b{color:var(--text)}
.rl-bar-wrap{flex:1;min-width:200px}
.rl-bar-label{display:flex;justify-content:space-between;font-size:10px;font-family:var(--mono);color:var(--muted);margin-bottom:6px}
.bar-track{height:7px;background:rgba(255,255,255,.05);border-radius:4px;overflow:hidden}
.bar-fill{height:100%;border-radius:4px;transition:width .6s ease;position:relative}
.bar-fill::after{content:'';position:absolute;inset:0;background:linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.15),rgba(255,255,255,0));animation:shim 2s infinite}
@keyframes shim{0%{transform:translateX(-100%)}100%{transform:translateX(200%)}}

/* ── Active sessions ───────────────────────────── */
.sessions-active{display:flex;flex-direction:column;gap:7px}
.sess-item{display:flex;align-items:center;gap:8px}
.sess-dot{
  width:6px;height:6px;border-radius:50%;background:var(--green);flex-shrink:0;
  box-shadow:0 0 6px rgba(95,168,130,.6);
}
.sess-proj{font-family:var(--mono);font-size:11px;color:var(--text);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.sess-time{font-family:var(--mono);font-size:10px;color:var(--muted);flex-shrink:0}
.empty-msg{font-size:12px;color:var(--muted);opacity:.5}

/* ── Claude Flower (thinking animation) ─────────── */
.active-flower-wrap{display:flex;align-items:center;gap:13px;padding:2px 0 12px}
.claude-flower{flex-shrink:0;animation:flowerSpin 12s linear infinite;transform-origin:center}
@keyframes flowerSpin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
.flower-petal{animation:petalBreath 1.8s ease-in-out infinite}
.flower-petal:nth-child(1){animation-delay:0s}
.flower-petal:nth-child(2){animation-delay:.3s}
.flower-petal:nth-child(3){animation-delay:.6s}
.flower-petal:nth-child(4){animation-delay:.9s}
.flower-petal:nth-child(5){animation-delay:1.2s}
.flower-petal:nth-child(6){animation-delay:1.5s}
@keyframes petalBreath{0%,100%{opacity:.14}50%{opacity:.62}}
.clauding-text{font-family:var(--mono);font-size:14px;font-weight:700;color:var(--amber);letter-spacing:-.1px;line-height:1.1}
.clauding-sub{font-size:10px;color:var(--muted);margin-top:4px}
.dot-wave span{display:inline-block;animation:dotBounce 1.2s ease-in-out infinite;opacity:0}
.dot-wave span:nth-child(1){animation-delay:0s}
.dot-wave span:nth-child(2){animation-delay:.15s}
.dot-wave span:nth-child(3){animation-delay:.3s}
@keyframes dotBounce{0%,60%,100%{opacity:0;transform:translateY(0)}30%{opacity:1;transform:translateY(-3px)}}

/* ── Chart containers ──────────────────────────── */
.chart-wrap{position:relative;width:100%}
.h200{height:200px}.h160{height:160px}.h120{height:120px}

/* ── Project bars ──────────────────────────────── */
.proj-list{display:flex;flex-direction:column;gap:8px}
.proj-row{display:flex;align-items:center;gap:9px}
.proj-name{font-family:var(--mono);font-size:10px;color:var(--muted);
  width:160px;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.proj-track{flex:1;height:5px;background:rgba(255,255,255,.05);border-radius:3px;overflow:hidden}
.proj-fill{height:100%;border-radius:3px;background:linear-gradient(90deg,var(--orange),var(--amber))}
.proj-count{font-family:var(--mono);font-size:10px;color:var(--muted);width:32px;text-align:right;flex-shrink:0}

/* ── Sessions table ────────────────────────────── */
.sess-table{width:100%;border-collapse:collapse;font-size:11px}
.sess-table th{
  text-align:left;padding:5px 8px;font-size:9px;font-weight:700;
  letter-spacing:.6px;text-transform:uppercase;color:var(--muted);
  border-bottom:1px solid var(--border);
}
.sess-table td{padding:7px 8px;font-family:var(--mono);border-bottom:1px solid rgba(255,255,255,.03)}
.sess-table tr:last-child td{border-bottom:none}
.sess-table tbody tr:first-child td{color:var(--amber)}
.tag{
  background:rgba(138,122,184,.14);color:var(--purple);
  border-radius:4px;padding:1px 6px;font-size:9px;
}

/* ── Stat rows (quick stats) ───────────────────── */
.stat-row{
  display:flex;justify-content:space-between;align-items:center;
  padding:8px 0;border-bottom:1px solid rgba(255,255,255,.04);
}
.stat-row:last-child{border-bottom:none}
.stat-row-label{font-size:11px;color:var(--muted)}
.stat-row-val{font-family:var(--mono);font-size:12px;font-weight:600}

/* ── Model legend ──────────────────────────────── */
.model-legend{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px;justify-content:center}
.model-chip{text-align:center}
.model-chip-name{font-family:var(--mono);font-size:9px;color:var(--muted)}
.model-chip-val{font-family:var(--mono);font-size:10px;font-weight:600}

/* ── Footer ────────────────────────────────────── */
.footer{margin-top:20px;text-align:center;font-size:10px;color:var(--dim);padding-bottom:8px}

/* ── Fade-in ───────────────────────────────────── */
.card{animation:fadeUp .3s ease both}
@keyframes fadeUp{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.row .card:nth-child(1){animation-delay:.04s}
.row .card:nth-child(2){animation-delay:.08s}
.row .card:nth-child(3){animation-delay:.12s}
.row .card:nth-child(4){animation-delay:.16s}
</style>
</head>
<body>

<!-- ── Header ─────────────────────────────────── -->
<div class="header">
  <div class="logo">
    <div class="diamond">◆</div>
    <div>
      <div class="logo-name">Claude Code</div>
      <div class="logo-sub">Usage Dashboard</div>
    </div>
  </div>
  <div class="header-right">
    <div class="clock" id="clock">—</div>
    <div class="live-pill"><span class="live-dot"></span>LIVE</div>
  </div>
</div>

<!-- ── Row 1: Stat cards ─────────────────────── -->
<div class="row row4">
  <div class="card">
    <div class="card-stripe"></div>
    <div class="card-label">Today</div>
    <div class="card-value v-orange" id="v-today">—</div>
    <div class="card-sub">messages sent</div>
  </div>
  <div class="card">
    <div class="card-label">This Week</div>
    <div class="card-value v-purple" id="v-week">—</div>
    <div class="card-sub">since Monday</div>
  </div>
  <div class="card">
    <div class="card-label">Current Session</div>
    <div class="card-value v-green" id="v-session">—</div>
    <div class="card-sub" id="v-session-sub">—</div>
  </div>
  <div class="card">
    <div class="card-label">All Time</div>
    <div class="card-value v-blue" id="v-alltime">—</div>
    <div class="card-sub" id="v-alltime-sub">—</div>
  </div>
</div>

<!-- ── Row 2: Rate limit + Active sessions ────── -->
<div class="row row21">
  <!-- Rate limit hero -->
  <div class="card rl-card">
    <div class="card-title">⏱ Rate Limit  ·  5-Hour Rolling Window</div>
    <div class="rl-inner">
      <!-- Ring -->
      <div class="rl-ring-wrap">
        <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="ringGreen" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="#3a7a5a"/>
              <stop offset="100%" stop-color="#5fa882"/>
            </linearGradient>
            <linearGradient id="ringAmber" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="#b86238"/>
              <stop offset="100%" stop-color="#e8a87c"/>
            </linearGradient>
            <linearGradient id="ringRed" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="#8a3535"/>
              <stop offset="100%" stop-color="#c46060"/>
            </linearGradient>
          </defs>
          <!-- Track -->
          <circle cx="50" cy="50" r="42" fill="none" stroke="#2a2520" stroke-width="8"/>
          <!-- Progress arc -->
          <circle id="ring-arc" cx="50" cy="50" r="42" fill="none"
                  stroke="url(#ringAmber)" stroke-width="8" stroke-linecap="round"
                  stroke-dasharray="263.9" stroke-dashoffset="263.9"
                  transform="rotate(-90 50 50)"
                  style="transition:stroke-dashoffset .7s ease,stroke .4s"/>
        </svg>
        <div class="rl-center">
          <div class="rl-pct" id="rl-pct">0%</div>
          <div class="rl-pct-label">used</div>
        </div>
      </div>
      <!-- Countdown + details -->
      <div class="rl-info">
        <div class="rl-time" id="rl-time">—</div>
        <div class="rl-detail" id="rl-detail">—</div>
      </div>
      <!-- Bar -->
      <div class="rl-bar-wrap">
        <div class="rl-bar-label">
          <span id="rl-bar-label-left">0%</span>
          <span id="rl-bar-label-right">—</span>
        </div>
        <div class="bar-track">
          <div class="bar-fill" id="rl-bar" style="width:0%;background:linear-gradient(90deg,var(--orange),var(--amber))"></div>
        </div>
        <div id="rl-msgs" style="font-size:10px;font-family:var(--mono);color:var(--muted);margin-top:6px">—</div>
      </div>
    </div>
  </div>
  <!-- Active sessions -->
  <div class="card">
    <div class="card-title">⚡ Active Now</div>
    <div class="sessions-active" id="active-sessions">
      <div class="empty-msg">No active sessions</div>
    </div>
  </div>
</div>

<!-- ── Row 3: 30-day activity chart ──────────── -->
<div class="row">
  <div class="card">
    <div class="card-title">📅 30-Day Activity</div>
    <div class="chart-wrap h200"><canvas id="actChart"></canvas></div>
  </div>
</div>

<!-- ── Row 4: Hour heatmap + Projects ─────────── -->
<div class="row row2">
  <div class="card">
    <div class="card-title">🕐 Activity by Hour of Day</div>
    <div class="chart-wrap h120"><canvas id="hourChart"></canvas></div>
  </div>
  <div class="card">
    <div class="card-title">📁 Top Projects</div>
    <div class="proj-list" id="proj-list">—</div>
  </div>
</div>

<!-- ── Row 5: Sessions + Stats + Models ───────── -->
<div class="row row3">
  <div class="card">
    <div class="card-title">🕒 Recent Sessions</div>
    <table class="sess-table">
      <thead>
        <tr><th>ID</th><th>Started</th><th>Msgs</th><th>Min</th><th>Project</th></tr>
      </thead>
      <tbody id="sess-tbody"></tbody>
    </table>
  </div>
  <div class="card">
    <div class="card-title">📊 Quick Stats</div>
    <div class="stat-row"><span class="stat-row-label">Total sessions</span><span class="stat-row-val" id="qs-sessions">—</span></div>
    <div class="stat-row"><span class="stat-row-label">Active streak</span><span class="stat-row-val" id="qs-streak">—</span></div>
    <div class="stat-row"><span class="stat-row-label">Peak hour</span><span class="stat-row-val" id="qs-peak">—</span></div>
    <div class="stat-row"><span class="stat-row-label">Using Claude since</span><span class="stat-row-val" id="qs-since">—</span></div>
    <div class="stat-row"><span class="stat-row-label">Current project</span><span class="stat-row-val" id="qs-proj" style="max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">—</span></div>
  </div>
  <div class="card">
    <div class="card-title">🤖 Model Usage</div>
    <div class="chart-wrap h160"><canvas id="modelChart"></canvas></div>
    <div class="model-legend" id="model-legend"></div>
  </div>
</div>

<div class="footer">Refreshes every 15 s &nbsp;·&nbsp; Data from ~/.claude &nbsp;·&nbsp; Personal use only</div>

<script>
const CIRC = 263.9; // 2π × 42
const PALETTE = ['#cc7b4a','#8a7ab8','#5fa882','#5a96c4','#b85a5a'];
let resetAtDate = null;
let actChart, hourChart, modelChart;

// ── Clock ticks every second ──────────────────
function tickClock() {
  const d = new Date();
  document.getElementById('clock').textContent =
    d.toLocaleDateString('en-US',{weekday:'short',month:'short',day:'numeric'}) +
    '  ' + d.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
}
tickClock(); setInterval(tickClock, 1000);

// ── Countdown ticks every second ─────────────
function tickCountdown() {
  if (!resetAtDate) return;
  const now  = new Date();
  const left = (resetAtDate - now) / 1000;
  if (left <= 0) {
    document.getElementById('rl-time').textContent = 'Full capacity';
    document.getElementById('rl-time').className = 'rl-time full';
    resetAtDate = null;
    return;
  }
  const h = Math.floor(left / 3600);
  const m = Math.floor((left % 3600) / 60);
  const s = Math.floor(left % 60);
  document.getElementById('rl-time').textContent =
    h + 'h ' + String(m).padStart(2,'0') + 'm ' + String(s).padStart(2,'0') + 's';
}
setInterval(tickCountdown, 1000);

function fmt(n){ return n >= 1000 ? (n/1000).toFixed(1)+'k' : String(n); }

// ── Build / update charts ────────────────────
Chart.defaults.color = '#6b635a';
Chart.defaults.borderColor = '#2a2520';
Chart.defaults.font.family = "'SF Mono','Fira Code',monospace";
Chart.defaults.font.size = 10;

function buildCharts(d) {
  // Activity bar chart
  const aCtx = document.getElementById('actChart').getContext('2d');
  const todayStr = d.dailyActivity[d.dailyActivity.length-1].date;
  const aGrad = aCtx.createLinearGradient(0, 0, 0, 200);
  aGrad.addColorStop(0,   'rgba(204,123,74,.75)');
  aGrad.addColorStop(1,   'rgba(204,123,74,.10)');
  const aGradToday = aCtx.createLinearGradient(0, 0, 0, 200);
  aGradToday.addColorStop(0, 'rgba(232,168,124,.95)');
  aGradToday.addColorStop(1, 'rgba(232,168,124,.20)');

  if (actChart) actChart.destroy();
  actChart = new Chart(aCtx, {
    type: 'bar',
    data: {
      labels: d.dailyActivity.map(x => {
        const [,mo,dy] = x.date.split('-');
        return `${mo}/${dy}`;
      }),
      datasets: [{
        data: d.dailyActivity.map(x => x.count),
        backgroundColor: d.dailyActivity.map(x => x.date === todayStr ? aGradToday : aGrad),
        borderRadius: 4,
        borderSkipped: false,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: {
        title: ctx => ctx[0].label,
        label: ctx => ` ${ctx.raw} messages`,
      }}},
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 0, maxTicksLimit: 12 }},
        y: { grid: { color:'rgba(255,255,255,.03)' }, ticks: { callback: v => fmt(v) }},
      },
    }
  });

  // Hour heatmap
  const hCtx = document.getElementById('hourChart').getContext('2d');
  const maxH  = Math.max(...d.hourDist, 1);
  if (hourChart) hourChart.destroy();
  hourChart = new Chart(hCtx, {
    type: 'bar',
    data: {
      labels: Array.from({length:24}, (_,i) => i % 6 === 0 ? `${i}h` : ''),
      datasets: [{
        data: d.hourDist,
        backgroundColor: d.hourDist.map(v => {
          const a = 0.12 + 0.72 * (v / maxH);
          return `rgba(138,122,184,${a.toFixed(2)})`;
        }),
        borderRadius: 3,
        borderSkipped: false,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: {
        title: ctx => `${ctx[0].dataIndex}:00 – ${ctx[0].dataIndex+1}:00`,
        label: ctx => ` ${ctx.raw} messages`,
      }}},
      scales: {
        x: { grid: { display: false }},
        y: { display: false },
      },
    }
  });

  // Model donut
  const mCtx = document.getElementById('modelChart').getContext('2d');
  const models  = Object.keys(d.modelUsage);
  const mTotals = models.map(m => (d.modelUsage[m].inputTokens||0) + (d.modelUsage[m].outputTokens||0));
  if (modelChart) modelChart.destroy();
  if (models.length > 0) {
    modelChart = new Chart(mCtx, {
      type: 'doughnut',
      data: {
        labels: models.map(m => m.split('-').slice(1,3).join(' ')),
        datasets: [{
          data: mTotals,
          backgroundColor: PALETTE,
          borderWidth: 2,
          borderColor: '#1c1916',
          hoverOffset: 5,
        }]
      },
      options: {
        cutout: '62%',
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: ctx => ` ${fmt(ctx.raw)} tokens` }},
        },
      }
    });
    document.getElementById('model-legend').innerHTML = models.map((m,i) => {
      const short = m.split('-').slice(1,3).join(' ');
      const tok   = fmt(mTotals[i]);
      return `<div class="model-chip">
        <div class="model-chip-name" style="color:${PALETTE[i]}">${short}</div>
        <div class="model-chip-val">${tok} tok</div>
      </div>`;
    }).join('');
  }
}

// ── DOM update ───────────────────────────────
function updateDOM(d) {
  const rl = d.rateLimit;

  // Stat cards
  document.getElementById('v-today').textContent   = fmt(d.todayCount);
  document.getElementById('v-week').textContent    = fmt(d.weekCount);
  document.getElementById('v-session').textContent = fmt(d.currentSession.messageCount);
  document.getElementById('v-session-sub').textContent = `since ${d.currentSession.start}`;
  document.getElementById('v-alltime').textContent = fmt(d.totalMessages);
  document.getElementById('v-alltime-sub').textContent = `${d.totalSessions} sessions`;

  // Rate limit ring
  const pct    = rl.windowPct;
  const isFull = pct === 0;
  const arc    = document.getElementById('ring-arc');
  const offset = CIRC * (1 - pct / 100);
  arc.style.strokeDashoffset = offset;
  arc.style.stroke = pct > 80 ? 'url(#ringRed)' : pct > 50 ? 'url(#ringAmber)' : 'url(#ringGreen)';

  document.getElementById('rl-pct').textContent = `${pct}%`;
  const timeEl = document.getElementById('rl-time');
  if (isFull) {
    timeEl.textContent = 'Full capacity';
    timeEl.className = 'rl-time full';
    resetAtDate = null;
  } else {
    timeEl.className = 'rl-time';
    if (rl.resetAtIso) resetAtDate = new Date(rl.resetAtIso);
    tickCountdown();
  }

  const resetStr = rl.resetAtIso
    ? new Date(rl.resetAtIso).toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit'})
    : '—';
  document.getElementById('rl-detail').innerHTML = isFull
    ? `<b>Window clear</b> — no messages in last 5h`
    : `Window opened at <b>${rl.windowStart}</b><br>Resets at <b>${resetStr}</b>`;

  // Bar
  document.getElementById('rl-bar').style.width = `${pct}%`;
  document.getElementById('rl-bar-label-left').textContent = `${pct}% used`;
  document.getElementById('rl-bar-label-right').textContent = isFull ? 'Clear' : `↺ resets ${resetStr}`;
  document.getElementById('rl-msgs').textContent = isFull
    ? '0 messages in current window'
    : `${rl.msgs5h} messages in current window`;

  // Bar color
  const barFill = document.getElementById('rl-bar');
  barFill.style.background = pct > 80
    ? 'linear-gradient(90deg,#8a3535,#c46060)'
    : pct > 50
    ? 'linear-gradient(90deg,var(--orange),var(--amber))'
    : 'linear-gradient(90deg,#3a7a5a,#5fa882)';

  // Active sessions
  const activeEl = document.getElementById('active-sessions');
  if (d.activeSessions.length === 0) {
    activeEl.innerHTML = '<div class="empty-msg">No active sessions in last 5 min</div>';
  } else {
    const n = d.activeSessions.length;
    const sessRows = d.activeSessions.map(s =>
      `<div class="sess-item">
        <div class="sess-dot"></div>
        <div class="sess-proj" title="${s.project}">${s.project}</div>
        <div class="sess-time">${s.lastSeen}</div>
      </div>`
    ).join('');
    activeEl.innerHTML = `
      <div class="active-flower-wrap">
        <svg class="claude-flower" viewBox="0 0 100 100" width="46" height="46" xmlns="http://www.w3.org/2000/svg">
          <circle class="flower-petal" cx="72" cy="50" r="16" fill="#e8a87c"/>
          <circle class="flower-petal" cx="61" cy="70" r="16" fill="#e8a87c"/>
          <circle class="flower-petal" cx="39" cy="70" r="16" fill="#e8a87c"/>
          <circle class="flower-petal" cx="28" cy="50" r="16" fill="#e8a87c"/>
          <circle class="flower-petal" cx="39" cy="30" r="16" fill="#e8a87c"/>
          <circle class="flower-petal" cx="61" cy="30" r="16" fill="#e8a87c"/>
          <circle cx="50" cy="50" r="11" fill="#cc7b4a" opacity=".55"/>
        </svg>
        <div>
          <div class="clauding-text">Clauding<span class="dot-wave"><span>.</span><span>.</span><span>.</span></span></div>
          <div class="clauding-sub">${n} session${n !== 1 ? 's' : ''} active</div>
        </div>
      </div>
      ${sessRows}`;
  }

  // Projects
  const maxP = d.topProjects[0]?.count || 1;
  document.getElementById('proj-list').innerHTML = d.topProjects.map(p =>
    `<div class="proj-row">
      <div class="proj-name" title="${p.project}">${p.project}</div>
      <div class="proj-track"><div class="proj-fill" style="width:${Math.round(p.count/maxP*100)}%"></div></div>
      <div class="proj-count">${p.count}</div>
    </div>`
  ).join('');

  // Sessions table
  document.getElementById('sess-tbody').innerHTML = d.recentSessions.map(s =>
    `<tr>
      <td><span class="tag">${s.sessionId}</span></td>
      <td>${s.start}</td>
      <td>${s.messageCount}</td>
      <td>${s.durationMin}</td>
      <td style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px;color:var(--muted)">${s.project}</td>
    </tr>`
  ).join('');

  // Quick stats
  document.getElementById('qs-sessions').textContent = d.totalSessions;
  document.getElementById('qs-streak').textContent   = d.streak + (d.streak === 1 ? ' day' : ' days');
  document.getElementById('qs-peak').textContent     = d.peakHour;
  document.getElementById('qs-since').textContent    = d.firstMessage;
  const proj = d.currentSession.project || '—';
  document.getElementById('qs-proj').textContent = proj.split('/').pop() || proj;
  document.getElementById('qs-proj').title = proj;
}

// ── Fetch & refresh ──────────────────────────
async function refresh() {
  try {
    const res  = await fetch('/api/data');
    const data = await res.json();
    updateDOM(data);
    buildCharts(data);
  } catch(e) { console.warn('refresh error', e); }
}

refresh();
setInterval(refresh, 15000);
</script>
</body>
</html>
"""

# ── HTTP server ───────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def do_GET(self):
        if self.path == '/api/data':
            try:
                body = json.dumps(compute_data()).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', len(body))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_error(500, str(e))
        elif self.path in ('/', '/index.html'):
            body = HTML.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

# ── Entry point ───────────────────────────────

def main():
    url = f'http://localhost:{PORT}'
    server = HTTPServer(('127.0.0.1', PORT), Handler)

    def open_browser():
        import time; time.sleep(0.4)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    print(f'\n  Claude Code Dashboard  →  {url}')
    print(f'  Auto-refreshes every 15 s  ·  Ctrl+C to stop\n')
    signal.signal(signal.SIGINT, lambda *_: (server.server_close(), sys.exit(0)))
    server.serve_forever()

if __name__ == '__main__':
    main()
