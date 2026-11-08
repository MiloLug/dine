#if DEBUG
import CArtBridge
import OSLog
import SwiftUI

private let log = Logger(subsystem: "dev.dine.Dine", category: "art")

/// Runs a bundled APK through ATL in the app container, a second one beside the first in ATL's VM;
/// the apps' output goes to the log (category `art`). ATL creates the process's only VM, so it runs
/// before any art screen run.
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
                tile("dialog", activity: "dev/dine/dialog/ContentActivity", title: "dialog content")
                tile("dialog", activity: "dev/dine/dialog/StackActivity", title: "dialog stack")
                tile("dialog", activity: "dev/dine/dialog/ViewActivity", title: "dialog view")
                tile("dialog", activity: "dev/dine/dialog/ChoiceActivity", title: "dialog choice")
                tile("dialog", activity: "dev/dine/dialog/ProgressActivity", title: "dialog progress")
                tile("nav", activity: "dev/dine/nav/MainActivity")
                tile("nav", activity: "dev/dine/nav/ImmersiveActivity", title: "nav immersive")
                tile("views", activity: "dev/dine/views/MainActivity")
                tile("widgets", activity: "dev/dine/widgets/MainActivity")
                tile("widgets", activity: "dev/dine/widgets/ControlsActivity", title: "controls")
                tile("widgets", activity: "dev/dine/widgets/TextActivity", title: "text")
                tile("widgets", activity: "dev/dine/widgets/DrawStayActivity", title: "draw")
                tile("widgets", activity: "dev/dine/widgets/ListsActivity", title: "lists")
                tile("windows", activity: "dev/dine/windows/MainActivity")
                tile("windows", activity: "dev/dine/windows/StateActivity", title: "windows state")
                tile("windows", activity: "dev/dine/windows/PopupActivity", title: "windows popup")
                tile("windows", activity: "dev/dine/windows/ResizeActivity", title: "keyboard resize")
                tile("windows", activity: "dev/dine/windows/PanActivity", title: "keyboard pan")
                tile("windows", activity: "dev/dine/windows/ConfigActivity", title: "config")
                tile("org.happysanta.gd_29", activity: "org/happysanta/gd/GDActivity", title: "gravity")
                tile("AdaptiveIconDemo", activity: "com/example/adaptiveicondemo/MainActivity", title: "adaptive icon")
                tile("views_widgets_samples_flower_finder", activity: "com/example/recyclersample/flowerList/FlowersListActivity", title: "flowers")
                tile("com.leocardz.multitouch.test_19", activity: "com/leocardz/multitouch/test/MultitouchTest", title: "multitouch")
                tile("com.ashwin.example.accelerometerdemo", activity: "com/ashwin/example/accelerometerdemo/MainActivity", title: "accelerometer")
                // the package suite's installer app: installs ext through a session, confirmed from the Application context
                tile("driver", in: "dev/package", activity: "dev/dine/pkg/driver/Main", title: "installer",
                     scenario: "session-app-context:ext")
            }
            .padding()
        }
        .navigationTitle("atl")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func tile(_ apk: String, in directory: String = "dev", activity: String, title: String? = nil,
                      scenario: String? = nil) -> some View {
        Button { run(apk, in: directory, activity: activity, title: title ?? apk, scenario: scenario) } label: {
            AppIconView(name: title ?? apk)
        }
        .buttonStyle(.plain)
    }

    /// `scenario`: the driver app's DINE_TEST_SCENARIO; its fixtures are the APKs beside it.
    private func run(_ apk: String, in directory: String, activity: String, title: String, scenario: String?) {
        // `art/` holds the runtime boot jars, `atl/` ATL's jars, `dev/` the test APKs (xtool.yml)
        guard let root = Bundle.main.path(forResource: "art", ofType: nil),
              let atl = Bundle.main.path(forResource: "atl", ofType: nil),
              let path = Bundle.main.path(forResource: apk, ofType: "apk", inDirectory: directory),
              let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first,
              let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
        else {
            return log.error("atl: art/, atl/, \(directory, privacy: .public)/\(apk, privacy: .public).apk or a library dir missing")
        }
        // the prefix: the package registry, installed APKs and app data, out of the purgeable Caches
        let prefix = support.appendingPathComponent("dine")
        do {
            try FileManager.default.createDirectory(at: prefix, withIntermediateDirectories: true)
        } catch {
            return log.error("atl: can't create \(prefix.path, privacy: .public): \(error, privacy: .public)")
        }
        if let scenario {
            setenv("DINE_TEST_SCENARIO", scenario, 1)
            setenv("DINE_TEST_FIXTURES", (path as NSString).deletingLastPathComponent, 1)
        }
        navigator.run(title, apk: path) { window, listener, app in
            dine_atl_run(root, atl, prefix.path, caches.path, path, activity, window, listener, app)
        }
    }
}
#endif
