import CArtBridge
import OSLog
import SwiftUI

private let log = Logger(subsystem: "dev.dine.Dine", category: "art")

/// Runs a bundled APK headless through ATL; it shows nothing, the app's output goes to the log
/// (category `art`). ATL creates the process's only VM, so it runs before any art screen run.
struct AtlView: View {
    var body: some View {
        List {
            Button("run demo") { run("demo_app", activity: "com/example/demo_application/MainActivity") }
        }
        .navigationTitle("atl")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func run(_ apk: String, activity: String) {
        // `art/` holds the boot jars, `atl/` ATL's jars and the test APKs (xtool.yml)
        guard let root = Bundle.main.path(forResource: "art", ofType: nil),
              let atl = Bundle.main.path(forResource: "atl", ofType: nil),
              let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
        else {
            return log.error("atl: art/, atl/ or caches dir missing")
        }
        if dine_atl_run(root, atl, caches.path, atl + "/" + apk + ".apk", activity) != 0 {
            log.notice("atl: not started, relaunch Dine")
        }
    }
}
