import WidgetKit
import SwiftUI
import UserNotifications

// MARK: — Data ────────────────────────────────────────────────────

struct ActiveTask {
    var dir:     String   // "ClaudeWidget"
    var model:   String   // "sonnet"
    var message: String   // first line of last agent reply
}

struct ClaudeData {
    var streak:      Int        = 0
    var windowPct:   Double     = 0    // 0..100
    var resetSecs:   Double     = 0
    var msgs5h:      Int        = 0
    var activeTasks: [ActiveTask] = []
    var username:    String     = NSUserName()
    var isActive:    Bool       { !activeTasks.isEmpty }
}

// MARK: — JSONL helpers ────────────────────────────────────────────

private let claudeDir = URL(fileURLWithPath: "/Users/\(NSUserName())/.claude")

private func shortModel(_ raw: String) -> String {
    let p = raw.split(separator: "-")
    return p.count >= 2 ? String(p[1]) : raw        // "claude-sonnet-4-6" → "sonnet"
}

private func readJSONLLast(_ url: URL) -> (dir: String, model: String, message: String) {
    guard let raw = try? String(contentsOf: url, encoding: .utf8) else { return ("", "", "") }
    let lines = raw.components(separatedBy: "\n")

    var dir   = ""
    var model = ""
    var msg   = ""

    // Walk lines in reverse; pick up the first hit for each field we need
    for line in lines.reversed() {
        let t = line.trimmingCharacters(in: .whitespaces)
        guard !t.isEmpty,
              let data = t.data(using: .utf8),
              let obj  = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { continue }

        // cwd  →  dir (max 16 chars, no truncation indicator needed)
        if dir.isEmpty, let cwd = obj["cwd"] as? String {
            let name = URL(fileURLWithPath: cwd).lastPathComponent
            dir = name.count > 16 ? String(name.prefix(16)) : name
        }

        // message.model  →  model
        if let m = obj["message"] as? [String: Any] {
            if model.isEmpty, let mv = m["model"] as? String { model = shortModel(mv) }

            // assistant text  →  first meaningful line, max 72 chars
            if msg.isEmpty, m["role"] as? String == "assistant" {
                var raw = ""
                if let blocks = m["content"] as? [[String: Any]] {
                    for b in blocks where b["type"] as? String == "text" {
                        if let text = b["text"] as? String {
                            let line = text.components(separatedBy: "\n")
                                .map    { $0.trimmingCharacters(in: .whitespaces) }
                                .first  { !$0.isEmpty && !$0.hasPrefix("#") && !$0.hasPrefix("```") }
                            if let line { raw = line; break }
                        }
                    }
                } else if let text = m["content"] as? String {
                    raw = text.trimmingCharacters(in: .whitespacesAndNewlines)
                }
                if !raw.isEmpty {
                    msg = raw.count > 72 ? String(raw.prefix(72)) : raw
                }
            }
        }

        if !dir.isEmpty && !model.isEmpty && !msg.isEmpty { break }
    }

    return (dir, model, msg)
}

// MARK: — Reader ───────────────────────────────────────────────────

struct ClaudeReader {
    static func read() -> ClaudeData {
        var d   = ClaudeData()
        let now = Date()
        let cal = Calendar.current

        // ── history.jsonl — for streak + 5h window ──────────────
        var msgs: [[String: Any]] = []
        let histURL = claudeDir.appendingPathComponent("history.jsonl")
        if let raw = try? String(contentsOf: histURL, encoding: .utf8) {
            for line in raw.components(separatedBy: "\n") {
                let t = line.trimmingCharacters(in: .whitespaces)
                guard !t.isEmpty,
                      let data = t.data(using: .utf8),
                      let obj  = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                else { continue }
                msgs.append(obj)
            }
        }
        msgs.sort { ($0["timestamp"] as? Double ?? 0) < ($1["timestamp"] as? Double ?? 0) }

        // streak
        var byDay: [Int: Int] = [:]
        for msg in msgs {
            let ts  = (msg["timestamp"] as? Double ?? 0) / 1000
            let dt  = Date(timeIntervalSince1970: ts)
            let ord = cal.ordinality(of: .day, in: .era, for: dt) ?? 0
            byDay[ord, default: 0] += 1
        }
        let todayOrd = cal.ordinality(of: .day, in: .era, for: now) ?? 0
        var dayOrd   = todayOrd
        while (byDay[dayOrd] ?? 0) > 0 { d.streak += 1; dayOrd -= 1 }

        // 5-hour rolling window
        let cut5h  = now.addingTimeInterval(-5 * 3600)
        let msgs5h = msgs.filter {
            (($0["timestamp"] as? Double ?? 0) / 1000) >= cut5h.timeIntervalSince1970
        }
        d.msgs5h = msgs5h.count
        if let firstTs = msgs5h.first?["timestamp"] as? Double {
            let t0      = Date(timeIntervalSince1970: firstTs / 1000)
            let resetAt = t0.addingTimeInterval(5 * 3600)
            d.windowPct = min(now.timeIntervalSince(t0) / (5 * 3600) * 100, 100)
            d.resetSecs = max(resetAt.timeIntervalSince(now), 0)
        }

        // ── Active tasks — project JSONLs modified < 5 min ago ──
        let cut5m   = now.addingTimeInterval(-5 * 60)
        let projDir = claudeDir.appendingPathComponent("projects")
        if let dirs = try? FileManager.default.contentsOfDirectory(
                at: projDir, includingPropertiesForKeys: [.isDirectoryKey]) {
            for dir in dirs {
                guard (try? dir.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true else { continue }
                guard let files = try? FileManager.default.contentsOfDirectory(
                        at: dir, includingPropertiesForKeys: [.contentModificationDateKey])
                else { continue }
                for f in files where f.pathExtension == "jsonl" {
                    guard let mt = (try? f.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate,
                          mt >= cut5m
                    else { continue }
                    let (dirName, model, message) = readJSONLLast(f)
                    d.activeTasks.append(ActiveTask(
                        dir:     dirName.isEmpty ? "Unknown" : dirName,
                        model:   model.isEmpty   ? "claude"  : model,
                        message: message
                    ))
                }
            }
        }

        // 85% wall notification
        if d.windowPct >= 85 { maybeNotify(pct: d.windowPct) }

        return d
    }

    private static func maybeNotify(pct: Double) {
        let ud = UserDefaults.standard
        guard !ud.bool(forKey: "wall85Notified") else { return }
        ud.set(true, forKey: "wall85Notified")
        let c = UNMutableNotificationContent()
        c.title = "Claude Code · Rate Limit"
        c.body  = String(format: "%.0f%% of 5-hour window used", pct)
        c.sound = .default
        UNUserNotificationCenter.current()
            .add(UNNotificationRequest(identifier: "wall85", content: c, trigger: nil))
    }
}

// MARK: — Timeline ─────────────────────────────────────────────────

struct ClaudeEntry: TimelineEntry {
    let date:      Date
    let data:      ClaudeData
    let updatedAt: String   // "2:48 AM" — time data was fetched
}

private func timeStamp() -> String {
    let f = DateFormatter(); f.dateFormat = "h:mm a"; return f.string(from: Date())
}

struct ClaudeProvider: TimelineProvider {
    func placeholder(in _: Context) -> ClaudeEntry { .init(date: .now, data: .init(), updatedAt: "—") }
    func getSnapshot(in _: Context, completion: @escaping (ClaudeEntry) -> Void) {
        completion(.init(date: .now, data: ClaudeReader.read(), updatedAt: timeStamp()))
    }
    func getTimeline(in _: Context, completion: @escaping (Timeline<ClaudeEntry>) -> Void) {
        let d = ClaudeReader.read()
        completion(Timeline(entries: [.init(date: .now, data: d, updatedAt: timeStamp())],
                            policy: .after(.now.addingTimeInterval(60))))
    }
}

// MARK: — Palette ──────────────────────────────────────────────────

private let bgColor  = Color(red: 0.059, green: 0.051, blue: 0.047)
private let amber    = Color(red: 0.910, green: 0.660, blue: 0.490)
private let orange   = Color(red: 0.784, green: 0.455, blue: 0.282)
private let green    = Color(red: 0.373, green: 0.659, blue: 0.510)
private let purple   = Color(red: 0.541, green: 0.478, blue: 0.722)
private let red      = Color(red: 0.780, green: 0.350, blue: 0.350)
private let textMain = Color(red: 0.910, green: 0.875, blue: 0.816)
private let muted    = Color(red: 0.420, green: 0.388, blue: 0.357)
private let logoGrad = LinearGradient(
    colors: [Color(red: 0.722, green: 0.384, blue: 0.220),
             Color(red: 0.910, green: 0.635, blue: 0.459)],
    startPoint: .topLeading, endPoint: .bottomTrailing
)

// MARK: — Status ───────────────────────────────────────────────────

private struct Status {
    let headline: String   // "Work as normal"
    let detail:   String   // "38% · 3h 20m left"
    let color:    Color
    let icon:     String   // SF Symbol name
}

private func status(pct: Double, resetSecs: Double, msgs5h: Int) -> Status {
    let timeStr = resetSecs > 0 ? timeLeft(resetSecs) + " remaining" : "window clear"

    switch pct {
    case 0..<1:
        return Status(headline: "All clear", detail: "No usage in last 5h",
                      color: green, icon: "checkmark.circle.fill")
    case 1..<50:
        return Status(headline: "Work as normal", detail: timeStr,
                      color: green, icon: "checkmark.circle.fill")
    case 50..<70:
        return Status(headline: "Pace yourself", detail: timeStr,
                      color: amber, icon: "exclamationmark.circle.fill")
    case 70..<85:
        return Status(headline: "Slow down", detail: timeStr,
                      color: orange, icon: "exclamationmark.triangle.fill")
    default:
        return Status(headline: "Take a break", detail: timeStr,
                      color: red, icon: "xmark.octagon.fill")
    }
}

private func timeLeft(_ secs: Double) -> String {
    guard secs > 1 else { return "done" }
    let h = Int(secs) / 3600
    let m = (Int(secs) % 3600) / 60
    return h > 0 ? "\(h)h \(m)m" : "\(m)m"
}

// MARK: — Shared components ────────────────────────────────────────

struct ClaudeLogo: View {
    var size: CGFloat = 22
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.28)
                .fill(logoGrad)
                .frame(width: size, height: size)
            Text("◆")
                .font(.system(size: size * 0.50, weight: .bold))
                .foregroundColor(.white)
        }
    }
}

struct RateBar: View {
    let pct: Double
    private var barColor: Color {
        if pct > 80 { return red }
        if pct > 50 { return orange }
        return green
    }
    var body: some View {
        ZStack(alignment: .leading) {
            Rectangle().fill(Color.white.opacity(0.07))
            Rectangle()
                .fill(barColor)
                .scaleEffect(x: CGFloat(min(max(pct, 0), 100) / 100), anchor: .leading)
        }
        .frame(height: 3)
        .cornerRadius(2)
        .clipped()
    }
}

// MARK: — Small widget ─────────────────────────────────────────────

struct SmallView: View {
    let data: ClaudeData
    var body: some View {
        let s = status(pct: data.windowPct, resetSecs: data.resetSecs, msgs5h: data.msgs5h)
        VStack(alignment: .leading, spacing: 0) {

            HStack(spacing: 6) {
                ClaudeLogo(size: 20)
                Text("Claude")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(textMain)
                Spacer()
                if data.isActive {
                    Circle().fill(green).frame(width: 6, height: 6)
                        .shadow(color: green.opacity(0.8), radius: 3)
                }
            }

            Spacer()

            // Status headline — the key info
            Image(systemName: s.icon)
                .font(.system(size: 18))
                .foregroundColor(s.color)
            Spacer().frame(height: 3)
            Text(s.headline)
                .font(.system(size: 13, weight: .bold))
                .foregroundColor(s.color)
            Text(s.detail)
                .font(.system(size: 8, design: .monospaced))
                .foregroundColor(muted)

            Spacer()

            // Streak
            Label("\(data.streak)d", systemImage: "flame.fill")
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(amber)

            Spacer().frame(height: 7)

            RateBar(pct: data.windowPct)
        }
        .padding(12)
        .containerBackground(bgColor, for: .widget)
    }
}

// MARK: — Medium widget ────────────────────────────────────────────

struct MediumView: View {
    let entry: ClaudeEntry

    var body: some View {
        let data = entry.data
        let s    = status(pct: data.windowPct, resetSecs: data.resetSecs, msgs5h: data.msgs5h)

        HStack(alignment: .top, spacing: 0) {

            // ── Left panel ────────────────────────────────────────
            VStack(alignment: .leading, spacing: 0) {

                // Header
                HStack(spacing: 7) {
                    ClaudeLogo(size: 24)
                    Text("Claude")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundColor(textMain)
                        .fixedSize()
                    Spacer()
                    Text(entry.updatedAt)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundColor(muted)
                        .fixedSize()
                }

                Spacer().frame(height: 10)

                // Rate bar + labels
                Text("5H WINDOW")
                    .font(.system(size: 7, weight: .bold))
                    .tracking(0.7)
                    .foregroundColor(muted)
                Spacer().frame(height: 5)
                RateBar(pct: data.windowPct)
                Spacer().frame(height: 4)
                HStack {
                    Text(String(format: "%.0f%%", data.windowPct))
                        .font(.system(size: 9, weight: .semibold, design: .monospaced))
                        .foregroundColor(s.color)
                    Spacer()
                    Text(timeLeft(data.resetSecs))
                        .font(.system(size: 9, weight: .semibold, design: .monospaced))
                        .foregroundColor(s.color)
                }

                Spacer()

                // Status — the money section
                HStack(spacing: 5) {
                    Image(systemName: s.icon)
                        .font(.system(size: 11))
                        .foregroundColor(s.color)
                    Text(s.headline)
                        .font(.system(size: 14, weight: .bold))
                        .foregroundColor(s.color)
                }
                Text(s.detail)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(muted)
                    .lineLimit(1)

                Spacer()

                // Streak
                Label("\(data.streak)d streak", systemImage: "flame.fill")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(amber)
            }
            .frame(maxWidth: .infinity)

            // ── Vertical divider ──────────────────────────────────
            Rectangle()
                .fill(Color.white.opacity(0.07))
                .frame(width: 1)
                .padding(.horizontal, 12)

            // ── Right panel — active tasks ────────────────────────
            VStack(alignment: .leading, spacing: 0) {

                Text("ACTIVE TASKS")
                    .font(.system(size: 7, weight: .bold))
                    .tracking(0.8)
                    .foregroundColor(muted)

                Spacer().frame(height: 8)

                if data.activeTasks.isEmpty {
                    Spacer()
                    Text("No active sessions\nin last 5 min")
                        .font(.system(size: 9))
                        .foregroundColor(muted.opacity(0.55))
                        .multilineTextAlignment(.leading)
                    Spacer()
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(Array(data.activeTasks.prefix(2).enumerated()), id: \.offset) { _, task in
                            VStack(alignment: .leading, spacing: 2) {
                                // dir + model badge — strings are pre-sized, no truncation needed
                                HStack(spacing: 5) {
                                    Circle().fill(green)
                                        .frame(width: 5, height: 5)
                                        .shadow(color: green.opacity(0.7), radius: 2)
                                    Text(task.dir)
                                        .font(.system(size: 10, weight: .semibold))
                                        .foregroundColor(textMain)
                                    Spacer()
                                    Text(task.model)
                                        .font(.system(size: 7, weight: .semibold))
                                        .foregroundColor(purple)
                                        .padding(.horizontal, 4)
                                        .padding(.vertical, 1)
                                        .background(purple.opacity(0.15))
                                        .cornerRadius(3)
                                }
                                // Agent message — pre-cut to 72 chars
                                if !task.message.isEmpty {
                                    Text(task.message)
                                        .font(.system(size: 8))
                                        .foregroundColor(muted)
                                        .fixedSize(horizontal: false, vertical: true)
                                        .padding(.leading, 10)
                                }
                            }
                        }
                    }
                    Spacer()
                }

                // Username — bottom right
                HStack {
                    Spacer()
                    Text(data.username)
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundColor(muted.opacity(0.6))
                }
            }
            .frame(width: 130)
        }
        .padding(14)
        .containerBackground(bgColor, for: .widget)
    }
}

// MARK: — Entry view ───────────────────────────────────────────────

struct ClaudeWidgetEntryView: View {
    @Environment(\.widgetFamily) var family
    let entry: ClaudeEntry
    var body: some View {
        let tapURL = URL(string: "claudewidget://open")!
        switch family {
        case .systemSmall: SmallView(data: entry.data).widgetURL(tapURL)
        default:           MediumView(entry: entry).widgetURL(tapURL)
        }
    }
}

// MARK: — Widget + Bundle ──────────────────────────────────────────

struct ClaudeCodeWidget: Widget {
    let kind = "ClaudeCodeWidget"
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: ClaudeProvider()) { entry in
            ClaudeWidgetEntryView(entry: entry)
        }
        .configurationDisplayName("Claude Code")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

@main
struct ClaudeWidgetBundle: WidgetBundle {
    var body: some Widget { ClaudeCodeWidget() }
}
