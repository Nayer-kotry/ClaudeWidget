import SwiftUI

@main
struct ClaudeWidgetApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .onOpenURL { _ in
                    launchDashboard()
                    WidgetCenterBridge.reload()
                }
        }
    }
}

func launchDashboard() {
    let script = "\(NSHomeDirectory())/.claude/widget.py"
    let task   = Process()
    task.launchPath = "/usr/bin/env"
    task.arguments  = ["python3", script]
    try? task.run()
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
        NSWorkspace.shared.open(URL(string: "http://localhost:7823")!)
    }
}
