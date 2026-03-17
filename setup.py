#!/usr/bin/env python3
"""
Claude Code Widget – Xcode project generator.

Run once:  python3 ~/Documents/ClaudeWidget/setup.py
Then:
  1. open ~/Documents/ClaudeWidget/ClaudeWidget.xcodeproj
  2. In Xcode, click ClaudeWidget target → Signing & Capabilities →
     select your Apple ID team (any free account works)
  3. Do the same for ClaudeWidgetExtension target
  4. Product → Run  (or Cmd+R)
  5. Right-click your desktop → Edit Widgets → find "Claude Code"
"""

import os, textwrap
from pathlib import Path

ROOT = Path(__file__).parent
APP_DIR = ROOT / "ClaudeWidgetApp"
EXT_DIR = ROOT / "ClaudeWidgetExtension"
PROJ_DIR = ROOT / "ClaudeWidget.xcodeproj"

for d in [APP_DIR, EXT_DIR, PROJ_DIR]:
    d.mkdir(exist_ok=True)

def write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip())
    print(f"  wrote {path.relative_to(ROOT)}")

# ─────────────────────────────────────────────
#  1.  HOST APP SOURCE
# ─────────────────────────────────────────────
write(APP_DIR / "ClaudeWidgetApp.swift", """
    import SwiftUI

    @main
    struct ClaudeWidgetApp: App {
        var body: some Scene {
            WindowGroup {
                ContentView()
            }
        }
    }
""")

write(APP_DIR / "ContentView.swift", """
    import SwiftUI

    struct ContentView: View {
        var body: some View {
            VStack(spacing: 24) {
                ZStack {
                    RoundedRectangle(cornerRadius: 14)
                        .fill(LinearGradient(
                            colors: [Color(red:0.80,green:0.47,blue:0.36),
                                     Color(red:0.91,green:0.66,blue:0.49)],
                            startPoint: .topLeading, endPoint: .bottomTrailing))
                        .frame(width: 64, height: 64)
                    Text("◆")
                        .font(.system(size: 34))
                        .foregroundColor(.white)
                }

                Text("Claude Code Widget")
                    .font(.title2.weight(.semibold))

                Text("Widget installed.\\n\\nTo add it to your desktop:\\nRight-click desktop → Edit Widgets → search \\"Claude\\"")
                    .multilineTextAlignment(.center)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: 320)

                HStack(spacing: 12) {
                    Button("Open Dashboard") {
                        let script = "\\(NSHomeDirectory())/.claude/widget.py"
                        let task = Process()
                        task.launchPath = "/usr/bin/env"
                        task.arguments = ["python3", script]
                        try? task.run()
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                            NSWorkspace.shared.open(URL(string: "http://localhost:7823")!)
                        }
                    }
                    .buttonStyle(.borderedProminent)

                    Button("Refresh Widget") {
                        WidgetCenterBridge.reload()
                    }
                    .buttonStyle(.bordered)
                }
            }
            .padding(48)
            .frame(minWidth: 420, minHeight: 320)
        }
    }
""")

write(APP_DIR / "WidgetCenterBridge.swift", """
    import WidgetKit

    struct WidgetCenterBridge {
        static func reload() {
            WidgetCenter.shared.reloadAllTimelines()
        }
    }
""")

# ─────────────────────────────────────────────
#  2.  WIDGET EXTENSION SOURCE
# ─────────────────────────────────────────────
write(EXT_DIR / "ClaudeWidget.swift", r"""
    import WidgetKit
    import SwiftUI
    import Foundation

    // MARK: - Data Model

    struct ClaudeStats {
        var todayCount:      Int    = 0
        var weekCount:       Int    = 0
        var sessionMessages: Int    = 0
        var sessionStart:    String = "--:--"
        var rateLimitPct:    Double = 0      // 0-100
        var resetTimeStr:    String = "Full capacity"
        var msgs5h:          Int    = 0
        var activeSessions:  [ActiveSession] = []
        var totalSessions:   Int    = 0
        var streak:          Int    = 0
        var currentProject:  String = "—"
    }

    struct ActiveSession: Identifiable {
        var id:           String
        var project:      String
        var lastActivity: Date
    }

    // MARK: - Data Reader

    func readClaudeStats() -> ClaudeStats {
        var stats = ClaudeStats()
        let home        = FileManager.default.homeDirectoryForCurrentUser
        let historyURL  = home.appendingPathComponent(".claude/history.jsonl")

        guard let data    = try? Data(contentsOf: historyURL),
              let content = String(data: data, encoding: .utf8) else { return stats }

        struct Msg { let ts: Double; let sid: String; let proj: String }
        var messages: [Msg] = []

        for line in content.split(separator: "\n", omittingEmptySubsequences: true) {
            guard let d    = line.data(using: .utf8),
                  let json = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
                  let ts   = json["timestamp"] as? Double,
                  let sid  = json["sessionId"]  as? String else { continue }
            messages.append(Msg(ts: ts / 1000,
                                sid: sid,
                                proj: json["project"] as? String ?? "unknown"))
        }
        messages.sort { $0.ts < $1.ts }

        let now       = Date()
        let cal       = Calendar.current
        let today     = cal.startOfDay(for: now)
        let weekComps = cal.dateComponents([.yearForWeekOfYear, .weekOfYear], from: now)
        let weekStart = cal.date(from: weekComps) ?? today
        let ago5h     = now.addingTimeInterval(-5 * 3600)

        var bySession: [String: [Msg]] = [:]
        var byDate:    [String: Int]   = [:]
        var ts5h:      [Double]        = []
        let df = DateFormatter(); df.dateFormat = "yyyy-MM-dd"

        for m in messages {
            let d = Date(timeIntervalSince1970: m.ts)
            byDate[df.string(from: d), default: 0] += 1
            bySession[m.sid, default: []].append(m)
            if d >= today    { stats.todayCount += 1 }
            if d >= weekStart { stats.weekCount  += 1 }
            if d >= ago5h    { ts5h.append(m.ts) }
        }

        stats.msgs5h        = ts5h.count
        stats.totalSessions = bySession.count

        // Current session
        if let last = messages.last {
            let cur = bySession[last.sid] ?? []
            stats.sessionMessages = cur.count
            if let first = cur.first {
                let tf = DateFormatter(); tf.dateFormat = "HH:mm"
                stats.sessionStart = tf.string(from: Date(timeIntervalSince1970: first.ts))
            }
            stats.currentProject = last.proj
                .replacingOccurrences(of: home.path + "/", with: "~/")
                .components(separatedBy: "/").last ?? "~"
        }

        // Rate-limit window
        if let firstTs = ts5h.first {
            let firstDate = Date(timeIntervalSince1970: firstTs)
            let elapsed   = now.timeIntervalSince(firstDate)
            stats.rateLimitPct = min(elapsed / (5 * 3600) * 100, 100)
            let reset = firstDate.addingTimeInterval(5 * 3600)
            if reset > now {
                let left = reset.timeIntervalSince(now)
                let h = Int(left / 3600)
                let m = Int(left.truncatingRemainder(dividingBy: 3600) / 60)
                stats.resetTimeStr = "\(h)h \(String(format: "%02d", m))m"
            } else {
                stats.rateLimitPct = 0
                stats.resetTimeStr = "Full capacity"
            }
        }

        // Active-day streak
        var check = today
        while true {
            if byDate[df.string(from: check)] != nil { stats.streak += 1 }
            else { break }
            check = check.addingTimeInterval(-86400)
        }

        // Active Claude instances (session file modified < 5 min ago)
        let projectsURL = home.appendingPathComponent(".claude/projects")
        let ago5min     = now.addingTimeInterval(-300)
        let username    = NSUserName()

        if let projs = try? FileManager.default.contentsOfDirectory(
            at: projectsURL,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: .skipsHiddenFiles)
        {
            for projDir in projs {
                let rawName = projDir.lastPathComponent
                let projName = rawName
                    .replacingOccurrences(of: "-Users-\(username)-", with: "~/")
                    .replacingOccurrences(of: "-", with: "/")

                if let files = try? FileManager.default.contentsOfDirectory(
                    at: projDir,
                    includingPropertiesForKeys: [.contentModificationDateKey],
                    options: .skipsHiddenFiles)
                {
                    for file in files where file.pathExtension == "jsonl" {
                        if let attrs   = try? file.resourceValues(forKeys: [.contentModificationDateKey]),
                           let modDate = attrs.contentModificationDate,
                           modDate >= ago5min
                        {
                            let sid = String(file.deletingPathExtension().lastPathComponent.prefix(8))
                            stats.activeSessions.append(
                                ActiveSession(id: sid, project: projName, lastActivity: modDate))
                        }
                    }
                }
            }
        }

        return stats
    }

    // MARK: - Timeline Provider

    struct ClaudeProvider: TimelineProvider {
        func placeholder(in context: Context) -> ClaudeEntry {
            var s = ClaudeStats()
            s.todayCount = 142; s.weekCount = 891; s.sessionMessages = 67
            s.sessionStart = "14:30"; s.rateLimitPct = 45
            s.resetTimeStr = "2h 30m"; s.msgs5h = 23; s.streak = 5
            s.currentProject = "iris"
            return ClaudeEntry(date: Date(), stats: s)
        }

        func getSnapshot(in context: Context, completion: @escaping (ClaudeEntry) -> Void) {
            completion(ClaudeEntry(date: Date(), stats: readClaudeStats()))
        }

        func getTimeline(in context: Context, completion: @escaping (Timeline<ClaudeEntry>) -> Void) {
            let entry = ClaudeEntry(date: Date(), stats: readClaudeStats())
            let next  = Calendar.current.date(byAdding: .minute, value: 5, to: Date())!
            completion(Timeline(entries: [entry], policy: .after(next)))
        }
    }

    struct ClaudeEntry: TimelineEntry {
        let date:  Date
        let stats: ClaudeStats
    }

    // MARK: - Small Widget View

    struct SmallView: View {
        let stats: ClaudeStats

        var limColor: Color {
            stats.rateLimitPct > 80 ? .red : stats.rateLimitPct > 50 ? .orange : .green
        }

        var body: some View {
            VStack(alignment: .leading, spacing: 6) {
                // Header
                HStack(spacing: 5) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(LinearGradient(
                            colors: [Color(red:0.80,green:0.47,blue:0.36),
                                     Color(red:0.91,green:0.66,blue:0.49)],
                            startPoint: .topLeading, endPoint: .bottomTrailing))
                        .frame(width: 14, height: 14)
                        .overlay(Text("◆").font(.system(size: 7)).foregroundColor(.white))
                    Text("Claude")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.white)
                    Spacer()
                    if !stats.activeSessions.isEmpty {
                        Circle().fill(Color.green).frame(width: 5, height: 5)
                    }
                }

                // Today
                VStack(alignment: .leading, spacing: 1) {
                    Text("TODAY")
                        .font(.system(size: 7, weight: .bold, design: .monospaced))
                        .foregroundColor(Color.white.opacity(0.35))
                    Text("\(stats.todayCount)")
                        .font(.system(size: 30, weight: .bold, design: .monospaced))
                        .foregroundColor(Color(red:0.91,green:0.66,blue:0.49))
                        .minimumScaleFactor(0.5)
                }

                Spacer()

                // Rate limit bar
                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Text("5H WINDOW")
                            .font(.system(size: 7, weight: .bold, design: .monospaced))
                            .foregroundColor(Color.white.opacity(0.35))
                        Spacer()
                        Text(stats.resetTimeStr)
                            .font(.system(size: 8, weight: .semibold, design: .monospaced))
                            .foregroundColor(limColor)
                    }
                    GeometryReader { g in
                        ZStack(alignment: .leading) {
                            RoundedRectangle(cornerRadius: 2)
                                .fill(Color.white.opacity(0.08))
                                .frame(height: 4)
                            RoundedRectangle(cornerRadius: 2)
                                .fill(limColor)
                                .frame(width: max(0, g.size.width * CGFloat(stats.rateLimitPct / 100)),
                                       height: 4)
                        }
                    }.frame(height: 4)
                }

                Text(stats.currentProject)
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundColor(Color.white.opacity(0.3))
                    .lineLimit(1)
                    .truncationMode(.head)
            }
            .padding(12)
            .widgetBg()
        }
    }

    // MARK: - Medium Widget View

    struct MediumView: View {
        let stats: ClaudeStats

        var limColor: Color {
            stats.rateLimitPct > 80 ? .red : stats.rateLimitPct > 50 ? .orange : .green
        }

        var body: some View {
            HStack(spacing: 0) {
                // ── LEFT PANE ──────────────────────────────
                VStack(alignment: .leading, spacing: 10) {
                    // Header
                    HStack(spacing: 6) {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(LinearGradient(
                                colors: [Color(red:0.80,green:0.47,blue:0.36),
                                         Color(red:0.91,green:0.66,blue:0.49)],
                                startPoint: .topLeading, endPoint: .bottomTrailing))
                            .frame(width: 18, height: 18)
                            .overlay(Text("◆").font(.system(size: 10)).foregroundColor(.white))
                        Text("Claude Code")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(.white)
                        Spacer()
                        Text(Date(), style: .time)
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundColor(Color.white.opacity(0.25))
                    }

                    // Stat trio
                    HStack(spacing: 14) {
                        statCell("TODAY",   "\(stats.todayCount)",
                                 Color(red:0.91,green:0.66,blue:0.49))
                        statCell("WEEK",    "\(stats.weekCount)",
                                 Color(red:0.54,green:0.50,blue:0.77))
                        statCell("SESSION", "\(stats.sessionMessages)",
                                 Color(red:0.41,green:0.69,blue:0.54))
                    }

                    Spacer()

                    // Rate limit
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("5H WINDOW  ·  \(stats.msgs5h) msgs")
                                .font(.system(size: 8, design: .monospaced))
                                .foregroundColor(Color.white.opacity(0.35))
                            Spacer()
                            Text(stats.rateLimitPct == 0 ? "● Clear" : "↺ \(stats.resetTimeStr)")
                                .font(.system(size: 9, weight: .semibold, design: .monospaced))
                                .foregroundColor(limColor)
                        }
                        GeometryReader { g in
                            ZStack(alignment: .leading) {
                                RoundedRectangle(cornerRadius: 2)
                                    .fill(Color.white.opacity(0.08))
                                    .frame(height: 5)
                                RoundedRectangle(cornerRadius: 2)
                                    .fill(LinearGradient(
                                        colors: [limColor.opacity(0.7), limColor],
                                        startPoint: .leading, endPoint: .trailing))
                                    .frame(
                                        width: max(0, g.size.width * CGFloat(stats.rateLimitPct / 100)),
                                        height: 5)
                            }
                        }.frame(height: 5)
                    }
                }
                .padding(14)

                // Divider
                Rectangle()
                    .fill(Color.white.opacity(0.07))
                    .frame(width: 1)
                    .padding(.vertical, 12)

                // ── RIGHT PANE ─────────────────────────────
                VStack(alignment: .leading, spacing: 6) {
                    Text("ACTIVE NOW")
                        .font(.system(size: 8, weight: .bold, design: .monospaced))
                        .foregroundColor(Color.white.opacity(0.35))

                    if stats.activeSessions.isEmpty {
                        Text("No active sessions")
                            .font(.system(size: 9))
                            .foregroundColor(Color.white.opacity(0.2))
                    } else {
                        ForEach(stats.activeSessions.prefix(4)) { s in
                            HStack(spacing: 5) {
                                Circle().fill(Color.green).frame(width: 4, height: 4)
                                Text(s.project)
                                    .font(.system(size: 9, design: .monospaced))
                                    .foregroundColor(Color.white.opacity(0.7))
                                    .lineLimit(1)
                                    .truncationMode(.head)
                            }
                        }
                    }

                    Spacer()

                    HStack(spacing: 4) {
                        Text("🔥").font(.system(size: 11))
                        Text("\(stats.streak)d streak")
                            .font(.system(size: 9, weight: .semibold, design: .monospaced))
                            .foregroundColor(Color.white.opacity(0.5))
                    }

                    Text(stats.currentProject)
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundColor(Color.white.opacity(0.25))
                        .lineLimit(1)
                        .truncationMode(.head)
                }
                .padding(.vertical, 14)
                .padding(.horizontal, 12)
                .frame(width: 130, alignment: .leading)
            }
            .widgetBg()
        }

        func statCell(_ label: String, _ value: String, _ color: Color) -> some View {
            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(.system(size: 7, weight: .bold, design: .monospaced))
                    .foregroundColor(Color.white.opacity(0.35))
                Text(value)
                    .font(.system(size: 22, weight: .bold, design: .monospaced))
                    .foregroundColor(color)
                    .minimumScaleFactor(0.5)
            }
        }
    }

    // MARK: - Widget Definition

    struct ClaudeCodeWidget: Widget {
        let kind = "ClaudeCodeWidget"
        var body: some WidgetConfiguration {
            StaticConfiguration(kind: kind, provider: ClaudeProvider()) { entry in
                ClaudeWidgetEntryView(entry: entry)
            }
            .configurationDisplayName("Claude Code")
            .description("Usage, rate limit, and active sessions.")
            .supportedFamilies([.systemSmall, .systemMedium])
        }
    }

    struct ClaudeWidgetEntryView: View {
        @Environment(\.widgetFamily) var family
        let entry: ClaudeEntry
        var body: some View {
            switch family {
            case .systemSmall: SmallView(stats: entry.stats)
            default:           MediumView(stats: entry.stats)
            }
        }
    }

    @main
    struct ClaudeWidgetBundle: WidgetBundle {
        var body: some Widget { ClaudeCodeWidget() }
    }

    // MARK: - Helpers

    extension View {
        @ViewBuilder func widgetBg() -> some View {
            let bg = Color(red: 0.07, green: 0.07, blue: 0.065)
            if #available(macOS 14.0, *) {
                self.containerBackground(bg, for: .widget)
            } else {
                self.background(bg)
            }
        }
    }
""")

# ─────────────────────────────────────────────
#  3.  Info.plists
# ─────────────────────────────────────────────
write(APP_DIR / "Info.plist", """
    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
        "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
        <key>CFBundleDevelopmentRegion</key>
        <string>$(DEVELOPMENT_LANGUAGE)</string>
        <key>CFBundleExecutable</key>
        <string>$(EXECUTABLE_NAME)</string>
        <key>CFBundleIdentifier</key>
        <string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
        <key>CFBundleInfoDictionaryVersion</key>
        <string>6.0</string>
        <key>CFBundleName</key>
        <string>$(PRODUCT_NAME)</string>
        <key>CFBundlePackageType</key>
        <string>$(PRODUCT_BUNDLE_PACKAGE_TYPE)</string>
        <key>CFBundleShortVersionString</key>
        <string>1.0</string>
        <key>CFBundleVersion</key>
        <string>1</string>
        <key>NSHighResolutionCapable</key>
        <true/>
        <key>NSPrincipalClass</key>
        <string>NSApplication</string>
    </dict>
    </plist>
""")

write(EXT_DIR / "Info.plist", """
    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
        "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
        <key>CFBundleDevelopmentRegion</key>
        <string>$(DEVELOPMENT_LANGUAGE)</string>
        <key>CFBundleExecutable</key>
        <string>$(EXECUTABLE_NAME)</string>
        <key>CFBundleIdentifier</key>
        <string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
        <key>CFBundleInfoDictionaryVersion</key>
        <string>6.0</string>
        <key>CFBundleName</key>
        <string>$(PRODUCT_NAME)</string>
        <key>CFBundlePackageType</key>
        <string>$(PRODUCT_BUNDLE_PACKAGE_TYPE)</string>
        <key>CFBundleShortVersionString</key>
        <string>1.0</string>
        <key>CFBundleVersion</key>
        <string>1</string>
        <key>NSExtension</key>
        <dict>
            <key>NSExtensionPointIdentifier</key>
            <string>com.apple.widgetkit-extension</string>
        </dict>
    </dict>
    </plist>
""")

# ─────────────────────────────────────────────
#  4.  Entitlements (no sandbox = read ~/.claude directly)
# ─────────────────────────────────────────────
write(APP_DIR / "ClaudeWidget.entitlements", """
    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
        "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
        <key>com.apple.security.app-sandbox</key>
        <false/>
    </dict>
    </plist>
""")

write(EXT_DIR / "ClaudeWidgetExtension.entitlements", """
    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
        "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
        <key>com.apple.security.app-sandbox</key>
        <false/>
    </dict>
    </plist>
""")

# ─────────────────────────────────────────────
#  5.  project.pbxproj
# ─────────────────────────────────────────────

# UUID constants (24 hex chars each)
P  = "AABB000000000000CCDD0001"   # project root
MG = "AABB000000000000CCDD0002"   # main group
PG = "AABB000000000000CCDD0003"   # products group
AG = "AABB000000000000CCDD0004"   # app group
EG = "AABB000000000000CCDD0005"   # ext group

# File references
A_APP    = "AABB000000000000CCDD0010"  # ClaudeWidgetApp.swift
A_CNT    = "AABB000000000000CCDD0011"  # ContentView.swift
A_WCB    = "AABB000000000000CCDD0012"  # WidgetCenterBridge.swift
E_WGT    = "AABB000000000000CCDD0013"  # ClaudeWidget.swift (ext)
A_INFOP  = "AABB000000000000CCDD0014"  # ClaudeWidgetApp/Info.plist
E_INFOP  = "AABB000000000000CCDD0015"  # ClaudeWidgetExtension/Info.plist
A_ENT    = "AABB000000000000CCDD0016"  # ClaudeWidget.entitlements
E_ENT    = "AABB000000000000CCDD0017"  # ClaudeWidgetExtension.entitlements

# Products
A_PROD   = "AABB000000000000CCDD0020"  # ClaudeWidget.app
E_PROD   = "AABB000000000000CCDD0021"  # ClaudeWidgetExtension.appex

# Build files
BF_A_APP = "AABB000000000000CCDD0030"  # ClaudeWidgetApp.swift → App Sources
BF_A_CNT = "AABB000000000000CCDD0031"  # ContentView.swift → App Sources
BF_A_WCB = "AABB000000000000CCDD0032"  # WidgetCenterBridge.swift → App Sources
BF_E_WGT = "AABB000000000000CCDD0033"  # ClaudeWidget.swift → Ext Sources
BF_E_EMB = "AABB000000000000CCDD0034"  # ClaudeWidgetExtension.appex → App Embed

# Build phases
BP_A_SRC = "AABB000000000000CCDD0040"  # App Sources
BP_A_FW  = "AABB000000000000CCDD0041"  # App Frameworks
BP_A_RES = "AABB000000000000CCDD0042"  # App Resources
BP_A_EMB = "AABB000000000000CCDD0043"  # App Embed Extensions
BP_E_SRC = "AABB000000000000CCDD0050"  # Ext Sources
BP_E_FW  = "AABB000000000000CCDD0051"  # Ext Frameworks
BP_E_RES = "AABB000000000000CCDD0052"  # Ext Resources

# Targets
T_APP    = "AABB000000000000CCDD0060"
T_EXT    = "AABB000000000000CCDD0061"

# Target dependency
PROXY    = "AABB000000000000CCDD0070"
DEP      = "AABB000000000000CCDD0071"

# Build configs
PC_DBG   = "AABB000000000000CCDD0080"
PC_REL   = "AABB000000000000CCDD0081"
AC_DBG   = "AABB000000000000CCDD0082"
AC_REL   = "AABB000000000000CCDD0083"
EC_DBG   = "AABB000000000000CCDD0084"
EC_REL   = "AABB000000000000CCDD0085"

# Config lists
CL_PROJ  = "AABB000000000000CCDD0090"
CL_APP   = "AABB000000000000CCDD0091"
CL_EXT   = "AABB000000000000CCDD0092"

pbxproj = f"""// !$*UTF8*$!
{{
\tarchiveVersion = 1;
\tclasses = {{
\t}};
\tobjectVersion = 56;
\tobjects = {{

/* Begin PBXBuildFile section */
\t\t{BF_A_APP} /* ClaudeWidgetApp.swift in Sources */ = {{isa = PBXBuildFile; fileRef = {A_APP} /* ClaudeWidgetApp.swift */; }};
\t\t{BF_A_CNT} /* ContentView.swift in Sources */ = {{isa = PBXBuildFile; fileRef = {A_CNT} /* ContentView.swift */; }};
\t\t{BF_A_WCB} /* WidgetCenterBridge.swift in Sources */ = {{isa = PBXBuildFile; fileRef = {A_WCB} /* WidgetCenterBridge.swift */; }};
\t\t{BF_E_WGT} /* ClaudeWidget.swift in Sources */ = {{isa = PBXBuildFile; fileRef = {E_WGT} /* ClaudeWidget.swift */; }};
\t\t{BF_E_EMB} /* ClaudeWidgetExtension.appex in Embed Foundation Extensions */ = {{isa = PBXBuildFile; fileRef = {E_PROD} /* ClaudeWidgetExtension.appex */; settings = {{ATTRIBUTES = (RemoveHeadersOnCopy, ); }}; }};
/* End PBXBuildFile section */

/* Begin PBXCopyFilesBuildPhase section */
\t\t{BP_A_EMB} /* Embed Foundation Extensions */ = {{
\t\t\tisa = PBXCopyFilesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tdstPath = "";
\t\t\tdstSubfolderSpec = 13;
\t\t\tfiles = (
\t\t\t\t{BF_E_EMB} /* ClaudeWidgetExtension.appex in Embed Foundation Extensions */,
\t\t\t);
\t\t\tname = "Embed Foundation Extensions";
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXCopyFilesBuildPhase section */

/* Begin PBXFileReference section */
\t\t{A_APP}  /* ClaudeWidgetApp.swift */          = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = ClaudeWidgetApp.swift; sourceTree = "<group>"; }};
\t\t{A_CNT}  /* ContentView.swift */              = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = ContentView.swift; sourceTree = "<group>"; }};
\t\t{A_WCB}  /* WidgetCenterBridge.swift */       = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = WidgetCenterBridge.swift; sourceTree = "<group>"; }};
\t\t{E_WGT}  /* ClaudeWidget.swift */             = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = ClaudeWidget.swift; sourceTree = "<group>"; }};
\t\t{A_INFOP} /* ClaudeWidgetApp/Info.plist */    = {{isa = PBXFileReference; lastKnownFileType = text.plist.xml; path = Info.plist; sourceTree = "<group>"; }};
\t\t{E_INFOP} /* ClaudeWidgetExtension/Info.plist */ = {{isa = PBXFileReference; lastKnownFileType = text.plist.xml; path = Info.plist; sourceTree = "<group>"; }};
\t\t{A_ENT}  /* ClaudeWidget.entitlements */      = {{isa = PBXFileReference; lastKnownFileType = text.plist.entitlements; path = ClaudeWidget.entitlements; sourceTree = "<group>"; }};
\t\t{E_ENT}  /* ClaudeWidgetExtension.entitlements */ = {{isa = PBXFileReference; lastKnownFileType = text.plist.entitlements; path = ClaudeWidgetExtension.entitlements; sourceTree = "<group>"; }};
\t\t{A_PROD} /* ClaudeWidget.app */               = {{isa = PBXFileReference; explicitFileType = wrapper.application; includeInIndex = 0; path = ClaudeWidget.app; sourceTree = BUILT_PRODUCTS_DIR; }};
\t\t{E_PROD} /* ClaudeWidgetExtension.appex */    = {{isa = PBXFileReference; explicitFileType = "wrapper.app-extension"; includeInIndex = 0; path = ClaudeWidgetExtension.appex; sourceTree = BUILT_PRODUCTS_DIR; }};
/* End PBXFileReference section */

/* Begin PBXFrameworksBuildPhase section */
\t\t{BP_A_FW} /* Frameworks */ = {{
\t\t\tisa = PBXFrameworksBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
\t\t{BP_E_FW} /* Frameworks */ = {{
\t\t\tisa = PBXFrameworksBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXFrameworksBuildPhase section */

/* Begin PBXGroup section */
\t\t{MG} = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
\t\t\t\t{AG} /* ClaudeWidgetApp */,
\t\t\t\t{EG} /* ClaudeWidgetExtension */,
\t\t\t\t{PG} /* Products */,
\t\t\t);
\t\t\tsourceTree = "<group>";
\t\t}};
\t\t{PG} /* Products */ = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
\t\t\t\t{A_PROD} /* ClaudeWidget.app */,
\t\t\t\t{E_PROD} /* ClaudeWidgetExtension.appex */,
\t\t\t);
\t\t\tname = Products;
\t\t\tsourceTree = "<group>";
\t\t}};
\t\t{AG} /* ClaudeWidgetApp */ = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
\t\t\t\t{A_APP} /* ClaudeWidgetApp.swift */,
\t\t\t\t{A_CNT} /* ContentView.swift */,
\t\t\t\t{A_WCB} /* WidgetCenterBridge.swift */,
\t\t\t\t{A_INFOP} /* Info.plist */,
\t\t\t\t{A_ENT}  /* ClaudeWidget.entitlements */,
\t\t\t);
\t\t\tpath = ClaudeWidgetApp;
\t\t\tsourceTree = "<group>";
\t\t}};
\t\t{EG} /* ClaudeWidgetExtension */ = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
\t\t\t\t{E_WGT}  /* ClaudeWidget.swift */,
\t\t\t\t{E_INFOP} /* Info.plist */,
\t\t\t\t{E_ENT}  /* ClaudeWidgetExtension.entitlements */,
\t\t\t);
\t\t\tpath = ClaudeWidgetExtension;
\t\t\tsourceTree = "<group>";
\t\t}};
/* End PBXGroup section */

/* Begin PBXNativeTarget section */
\t\t{T_APP} /* ClaudeWidget */ = {{
\t\t\tisa = PBXNativeTarget;
\t\t\tbuildConfigurationList = {CL_APP} /* Build configuration list for PBXNativeTarget "ClaudeWidget" */;
\t\t\tbuildPhases = (
\t\t\t\t{BP_A_SRC} /* Sources */,
\t\t\t\t{BP_A_FW}  /* Frameworks */,
\t\t\t\t{BP_A_RES} /* Resources */,
\t\t\t\t{BP_A_EMB} /* Embed Foundation Extensions */,
\t\t\t);
\t\t\tbuildRules = (
\t\t\t);
\t\t\tdependencies = (
\t\t\t\t{DEP} /* PBXTargetDependency */,
\t\t\t);
\t\t\tname = ClaudeWidget;
\t\t\tproductName = ClaudeWidget;
\t\t\tproductReference = {A_PROD} /* ClaudeWidget.app */;
\t\t\tproductType = "com.apple.product-type.application";
\t\t}};
\t\t{T_EXT} /* ClaudeWidgetExtension */ = {{
\t\t\tisa = PBXNativeTarget;
\t\t\tbuildConfigurationList = {CL_EXT} /* Build configuration list for PBXNativeTarget "ClaudeWidgetExtension" */;
\t\t\tbuildPhases = (
\t\t\t\t{BP_E_SRC} /* Sources */,
\t\t\t\t{BP_E_FW}  /* Frameworks */,
\t\t\t\t{BP_E_RES} /* Resources */,
\t\t\t);
\t\t\tbuildRules = (
\t\t\t);
\t\t\tdependencies = (
\t\t\t);
\t\t\tname = ClaudeWidgetExtension;
\t\t\tproductName = ClaudeWidgetExtension;
\t\t\tproductReference = {E_PROD} /* ClaudeWidgetExtension.appex */;
\t\t\tproductType = "com.apple.product-type.app-extension";
\t\t}};
/* End PBXNativeTarget section */

/* Begin PBXProject section */
\t\t{P} /* Project object */ = {{
\t\t\tisa = PBXProject;
\t\t\tattributes = {{
\t\t\t\tBuildIndependentTargetsInParallel = 1;
\t\t\t\tLastSwiftUpdateCheck = 1600;
\t\t\t\tLastUpgradeCheck = 1600;
\t\t\t\tTargetAttributes = {{
\t\t\t\t\t{T_APP} = {{
\t\t\t\t\t\tCreatedOnToolsVersion = 16.0;
\t\t\t\t\t}};
\t\t\t\t\t{T_EXT} = {{
\t\t\t\t\t\tCreatedOnToolsVersion = 16.0;
\t\t\t\t\t}};
\t\t\t\t}};
\t\t\t}};
\t\t\tbuildConfigurationList = {CL_PROJ} /* Build configuration list for PBXProject */;
\t\t\tcompatibilityVersion = "Xcode 14.0";
\t\t\tdevelopmentRegion = en;
\t\t\thasScannedForEncodings = 0;
\t\t\tknownRegions = (
\t\t\t\ten,
\t\t\t\tBase,
\t\t\t);
\t\t\tmainGroup = {MG};
\t\t\tproductRefGroup = {PG} /* Products */;
\t\t\tprojectDirPath = "";
\t\t\tprojectRoot = "";
\t\t\ttargets = (
\t\t\t\t{T_APP} /* ClaudeWidget */,
\t\t\t\t{T_EXT} /* ClaudeWidgetExtension */,
\t\t\t);
\t\t}};
/* End PBXProject section */

/* Begin PBXResourcesBuildPhase section */
\t\t{BP_A_RES} /* Resources */ = {{
\t\t\tisa = PBXResourcesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
\t\t{BP_E_RES} /* Resources */ = {{
\t\t\tisa = PBXResourcesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXResourcesBuildPhase section */

/* Begin PBXSourcesBuildPhase section */
\t\t{BP_A_SRC} /* Sources */ = {{
\t\t\tisa = PBXSourcesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
\t\t\t\t{BF_A_APP} /* ClaudeWidgetApp.swift in Sources */,
\t\t\t\t{BF_A_CNT} /* ContentView.swift in Sources */,
\t\t\t\t{BF_A_WCB} /* WidgetCenterBridge.swift in Sources */,
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
\t\t{BP_E_SRC} /* Sources */ = {{
\t\t\tisa = PBXSourcesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
\t\t\t\t{BF_E_WGT} /* ClaudeWidget.swift in Sources */,
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXSourcesBuildPhase section */

/* Begin PBXContainerItemProxy section */
\t\t{PROXY} /* PBXContainerItemProxy */ = {{
\t\t\tisa = PBXContainerItemProxy;
\t\t\tcontainerPortal = {P} /* Project object */;
\t\t\tproxyType = 1;
\t\t\tremoteGlobalIDString = {T_EXT};
\t\t\tremoteInfo = ClaudeWidgetExtension;
\t\t}};
/* End PBXContainerItemProxy section */

/* Begin PBXTargetDependency section */
\t\t{DEP} /* PBXTargetDependency */ = {{
\t\t\tisa = PBXTargetDependency;
\t\t\ttarget = {T_EXT} /* ClaudeWidgetExtension */;
\t\t\ttargetProxy = {PROXY} /* PBXContainerItemProxy */;
\t\t}};
/* End PBXTargetDependency section */

/* Begin XCBuildConfiguration section */
\t\t{PC_DBG} /* Debug */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tALWAYS_SEARCH_USER_PATHS = NO;
\t\t\t\tCLANG_ENABLE_MODULES = YES;
\t\t\t\tCLANG_ENABLE_OBJC_ARC = YES;
\t\t\t\tCOPY_PHASE_STRIP = NO;
\t\t\t\tDEBUG_INFORMATION_FORMAT = dwarf;
\t\t\t\tENABLE_STRICT_OBJC_MSGSEND = YES;
\t\t\t\tENABLE_TESTABILITY = YES;
\t\t\t\tGCC_DYNAMIC_NO_PIC = NO;
\t\t\t\tGCC_OPTIMIZATION_LEVEL = 0;
\t\t\t\tMACOSX_DEPLOYMENT_TARGET = 13.0;
\t\t\t\tMTL_ENABLE_DEBUG_INFO = INCLUDE_SOURCE;
\t\t\t\tMTL_FAST_MATH = YES;
\t\t\t\tONLY_ACTIVE_ARCH = YES;
\t\t\t\tSDKROOT = macosx;
\t\t\t\tSWIFT_ACTIVE_COMPILATION_CONDITIONS = DEBUG;
\t\t\t\tSWIFT_OPTIMIZATION_LEVEL = "-Onone";
\t\t\t}};
\t\t\tname = Debug;
\t\t}};
\t\t{PC_REL} /* Release */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tALWAYS_SEARCH_USER_PATHS = NO;
\t\t\t\tCLANG_ENABLE_MODULES = YES;
\t\t\t\tCLANG_ENABLE_OBJC_ARC = YES;
\t\t\t\tCOPY_PHASE_STRIP = NO;
\t\t\t\tDEBUG_INFORMATION_FORMAT = "dwarf-with-dsym";
\t\t\t\tENABLE_NS_ASSERTIONS = NO;
\t\t\t\tENABLE_STRICT_OBJC_MSGSEND = YES;
\t\t\t\tMACOSX_DEPLOYMENT_TARGET = 13.0;
\t\t\t\tMTL_FAST_MATH = YES;
\t\t\t\tSDKROOT = macosx;
\t\t\t\tSWIFT_COMPILATION_MODE = wholemodule;
\t\t\t\tSWIFT_OPTIMIZATION_LEVEL = "-O";
\t\t\t}};
\t\t\tname = Release;
\t\t}};
\t\t{AC_DBG} /* Debug */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tASSET_CATALOG_COMPILER_OPTIMIZATION = space;
\t\t\t\tCODE_SIGN_ENTITLEMENTS = ClaudeWidgetApp/ClaudeWidget.entitlements;
\t\t\t\tCODE_SIGN_IDENTITY = "Apple Development";
\t\t\t\tCODE_SIGN_STYLE = Automatic;
\t\t\t\tCOMBINE_HIDPI_IMAGES = YES;
\t\t\t\tDEVELOPMENT_TEAM = "";
\t\t\t\tINFOPLIST_FILE = ClaudeWidgetApp/Info.plist;
\t\t\t\tLD_RUNPATH_SEARCH_PATHS = (
\t\t\t\t\t"$(inherited)",
\t\t\t\t\t"@executable_path/../Frameworks",
\t\t\t\t);
\t\t\t\tMACOSX_DEPLOYMENT_TARGET = 13.0;
\t\t\t\tPRODUCT_BUNDLE_IDENTIFIER = "com.personal.claudewidget";
\t\t\t\tPRODUCT_NAME = ClaudeWidget;
\t\t\t\tSWIFT_EMIT_LOC_STRINGS = YES;
\t\t\t\tSWIFT_VERSION = 5;
\t\t\t}};
\t\t\tname = Debug;
\t\t}};
\t\t{AC_REL} /* Release */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tASSET_CATALOG_COMPILER_OPTIMIZATION = space;
\t\t\t\tCODE_SIGN_ENTITLEMENTS = ClaudeWidgetApp/ClaudeWidget.entitlements;
\t\t\t\tCODE_SIGN_IDENTITY = "Apple Development";
\t\t\t\tCODE_SIGN_STYLE = Automatic;
\t\t\t\tCOMBINE_HIDPI_IMAGES = YES;
\t\t\t\tDEVELOPMENT_TEAM = "";
\t\t\t\tINFOPLIST_FILE = ClaudeWidgetApp/Info.plist;
\t\t\t\tLD_RUNPATH_SEARCH_PATHS = (
\t\t\t\t\t"$(inherited)",
\t\t\t\t\t"@executable_path/../Frameworks",
\t\t\t\t);
\t\t\t\tMACOSX_DEPLOYMENT_TARGET = 13.0;
\t\t\t\tPRODUCT_BUNDLE_IDENTIFIER = "com.personal.claudewidget";
\t\t\t\tPRODUCT_NAME = ClaudeWidget;
\t\t\t\tSWIFT_EMIT_LOC_STRINGS = YES;
\t\t\t\tSWIFT_VERSION = 5;
\t\t\t}};
\t\t\tname = Release;
\t\t}};
\t\t{EC_DBG} /* Debug */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tCODE_SIGN_ENTITLEMENTS = ClaudeWidgetExtension/ClaudeWidgetExtension.entitlements;
\t\t\t\tCODE_SIGN_IDENTITY = "Apple Development";
\t\t\t\tCODE_SIGN_STYLE = Automatic;
\t\t\t\tDEVELOPMENT_TEAM = "";
\t\t\t\tINFOPLIST_FILE = ClaudeWidgetExtension/Info.plist;
\t\t\t\tLD_RUNPATH_SEARCH_PATHS = (
\t\t\t\t\t"$(inherited)",
\t\t\t\t\t"@executable_path/../Frameworks",
\t\t\t\t\t"@executable_path/../../../../Frameworks",
\t\t\t\t);
\t\t\t\tMACOSX_DEPLOYMENT_TARGET = 13.0;
\t\t\t\tPRODUCT_BUNDLE_IDENTIFIER = "com.personal.claudewidget.extension";
\t\t\t\tPRODUCT_NAME = ClaudeWidgetExtension;
\t\t\t\tSKIP_INSTALL = YES;
\t\t\t\tSWIFT_EMIT_LOC_STRINGS = YES;
\t\t\t\tSWIFT_VERSION = 5;
\t\t\t}};
\t\t\tname = Debug;
\t\t}};
\t\t{EC_REL} /* Release */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tCODE_SIGN_ENTITLEMENTS = ClaudeWidgetExtension/ClaudeWidgetExtension.entitlements;
\t\t\t\tCODE_SIGN_IDENTITY = "Apple Development";
\t\t\t\tCODE_SIGN_STYLE = Automatic;
\t\t\t\tDEVELOPMENT_TEAM = "";
\t\t\t\tINFOPLIST_FILE = ClaudeWidgetExtension/Info.plist;
\t\t\t\tLD_RUNPATH_SEARCH_PATHS = (
\t\t\t\t\t"$(inherited)",
\t\t\t\t\t"@executable_path/../Frameworks",
\t\t\t\t\t"@executable_path/../../../../Frameworks",
\t\t\t\t);
\t\t\t\tMACOSX_DEPLOYMENT_TARGET = 13.0;
\t\t\t\tPRODUCT_BUNDLE_IDENTIFIER = "com.personal.claudewidget.extension";
\t\t\t\tPRODUCT_NAME = ClaudeWidgetExtension;
\t\t\t\tSKIP_INSTALL = YES;
\t\t\t\tSWIFT_EMIT_LOC_STRINGS = YES;
\t\t\t\tSWIFT_VERSION = 5;
\t\t\t}};
\t\t\tname = Release;
\t\t}};
/* End XCBuildConfiguration section */

/* Begin XCConfigurationList section */
\t\t{CL_PROJ} /* Build configuration list for PBXProject */ = {{
\t\t\tisa = XCConfigurationList;
\t\t\tbuildConfigurations = (
\t\t\t\t{PC_DBG} /* Debug */,
\t\t\t\t{PC_REL} /* Release */,
\t\t\t);
\t\t\tdefaultConfigurationIsVisible = 0;
\t\t\tdefaultConfigurationName = Release;
\t\t}};
\t\t{CL_APP} /* Build configuration list for PBXNativeTarget "ClaudeWidget" */ = {{
\t\t\tisa = XCConfigurationList;
\t\t\tbuildConfigurations = (
\t\t\t\t{AC_DBG} /* Debug */,
\t\t\t\t{AC_REL} /* Release */,
\t\t\t);
\t\t\tdefaultConfigurationIsVisible = 0;
\t\t\tdefaultConfigurationName = Release;
\t\t}};
\t\t{CL_EXT} /* Build configuration list for PBXNativeTarget "ClaudeWidgetExtension" */ = {{
\t\t\tisa = XCConfigurationList;
\t\t\tbuildConfigurations = (
\t\t\t\t{EC_DBG} /* Debug */,
\t\t\t\t{EC_REL} /* Release */,
\t\t\t);
\t\t\tdefaultConfigurationIsVisible = 0;
\t\t\tdefaultConfigurationName = Release;
\t\t}};
/* End XCConfigurationList section */

\t}};
\trootObject = {P} /* Project object */;
}}
"""

(PROJ_DIR / "project.pbxproj").write_text(pbxproj)
print(f"  wrote ClaudeWidget.xcodeproj/project.pbxproj")


# ─────────────────────────────────────────────
#  Install widget.py dashboard to ~/.claude/
# ─────────────────────────────────────────────
import shutil as _shutil
_widget_src = ROOT / "widget.py"
_claude_dir = Path.home() / ".claude"
if _widget_src.exists() and _claude_dir.exists():
    _shutil.copy2(_widget_src, _claude_dir / "widget.py")
    print(f"  installed widget.py → {_claude_dir / 'widget.py'}")

# ─────────────────────────────────────────────
#  Done
# ─────────────────────────────────────────────
print(f"""
✅  Project generated at:
    {ROOT}

Next steps:
  1. open "{ROOT}/ClaudeWidget.xcodeproj"
  2. In Xcode: click 'ClaudeWidget' in the target list (left sidebar)
     → Signing & Capabilities → Team → pick your Apple ID
     Do the same for 'ClaudeWidgetExtension'
  3. Press Cmd+R to build and run
  4. Right-click your desktop → Edit Widgets → search "Claude"
  5. Add Small or Medium size — done!

The widget refreshes every 5 minutes automatically.
No Xcode running required after the first build.

Optional — full browser dashboard:
  python3 ~/.claude/widget.py
  # opens http://localhost:7823
""")
