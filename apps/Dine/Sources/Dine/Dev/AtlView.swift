#if DEBUG
import CArtBridge
import OSLog
import SwiftUI

private let log = Logger(subsystem: "dev.dine.Dine", category: "art")

/// Runs a bundled APK through ATL in the app container; the app's output goes to the log (category
/// `art`). ATL creates the process's only VM, so it runs before any art screen run.
struct AtlView: View {
    @EnvironmentObject private var navigator: Navigator

    var body: some View {
        List {
            Button("run demo") { run("demo_app", activity: "com/example/demo_application/MainActivity") }
            Button("run looper") { run("looper", activity: "dev/dine/looper/MainActivity") }
            Button("run dialog") { run("dialog", activity: "dev/dine/dialog/MainActivity") }
            Button("run nav") { run("nav", activity: "dev/dine/nav/MainActivity") }
        }
        .navigationTitle("atl")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func run(_ apk: String, activity: String) {
        // `art/` holds the boot jars, `atl/` ATL's jars, `dev/` the test APKs (xtool.yml)
        guard let root = Bundle.main.path(forResource: "art", ofType: nil),
              let atl = Bundle.main.path(forResource: "atl", ofType: nil),
              let path = Bundle.main.path(forResource: apk, ofType: "apk", inDirectory: "dev"),
              let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
        else {
            return log.error("atl: art/, atl/, dev/\(apk, privacy: .public).apk or caches dir missing")
        }
        navigator.run(apk) { listener in
            dine_atl_run(root, atl, caches.path, path, activity, listener)
        }
    }
}
#endif
