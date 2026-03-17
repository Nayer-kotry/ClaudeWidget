import SwiftUI
import UserNotifications

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

            Text("Widget installed.\n\nTo add it to your desktop:\nRight-click desktop → Edit Widgets → search \"Claude\"")
                .multilineTextAlignment(.center)
                .foregroundColor(.secondary)
                .frame(maxWidth: 320)

            HStack(spacing: 12) {
                Button("Open Dashboard") {
                    launchDashboard()
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
        .onAppear {
            UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .sound]) { _, _ in }
        }
    }
}

#Preview { ContentView() }
