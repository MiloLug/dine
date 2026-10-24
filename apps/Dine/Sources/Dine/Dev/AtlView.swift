#if DEBUG
import CArtBridge
import OSLog
import SwiftUI

private let log = Logger(subsystem: "dev.dine.Dine", category: "art")

/// Runs a bundled APK through ATL in the app container; the app's output goes to the log (category
/// `art`). ATL creates the process's only VM, so it runs before any art screen run.
struct AtlView: View {
    @EnvironmentObject private var navigator: Navigator

    private let columns = Array(repeating: GridItem(.flexible()), count: 4)

    var body: some View {
        ScrollView {
            LazyVGrid(columns: columns, spacing: 24) {
                tile("demo_app", activity: "com/example/demo_application/MainActivity")
                tile("looper", activity: "dev/dine/looper/MainActivity")
                tile("dialog", activity: "dev/dine/dialog/MainActivity")
                tile("dialog", activity: "dev/dine/dialog/KeepActivity", title: "dialog keep")
                tile("nav", activity: "dev/dine/nav/MainActivity")
                tile("views", activity: "dev/dine/views/MainActivity")
                tile("widgets", activity: "dev/dine/widgets/MainActivity")
                tile("widgets", activity: "dev/dine/widgets/ControlsActivity", title: "controls")
                tile("widgets", activity: "dev/dine/widgets/TextActivity", title: "text")
            }
            .padding()
        }
        .navigationTitle("atl")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func tile(_ apk: String, activity: String, title: String? = nil) -> some View {
        Button { run(apk, activity: activity, title: title ?? apk) } label: { AppIconView(name: title ?? apk) }
            .buttonStyle(.plain)
    }

    private func run(_ apk: String, activity: String, title: String) {
        // `art/` holds the runtime boot jars, `atl/` ATL's jars, `dev/` the test APKs (xtool.yml)
        guard let root = Bundle.main.path(forResource: "art", ofType: nil),
              let atl = Bundle.main.path(forResource: "atl", ofType: nil),
              let path = Bundle.main.path(forResource: apk, ofType: "apk", inDirectory: "dev"),
              let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
        else {
            return log.error("atl: art/, atl/, dev/\(apk, privacy: .public).apk or caches dir missing")
        }
        navigator.run(title) { window, listener in
            dine_atl_run(root, atl, caches.path, path, activity, window, listener)
        }
    }
}
#endif
