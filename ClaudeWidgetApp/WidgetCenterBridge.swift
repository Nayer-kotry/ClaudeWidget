import WidgetKit

struct WidgetCenterBridge {
    static func reload() {
        WidgetCenter.shared.reloadAllTimelines()
    }
}
