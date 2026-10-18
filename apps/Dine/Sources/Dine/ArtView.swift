import CArtBridge
import OSLog
import SwiftUI

private let log = Logger(subsystem: "dev.dine.Dine", category: "art")

/// Shows the ART platform probe; `run hello` runs the runtime suite's hello dex in-process. The
/// VM's own output goes to the log (category `art`), not to this view.
struct ArtView: View {
    @State private var lines: [String] = []

    var body: some View {
        List {
            Section {
                Button("run hello", action: runHello)
            }
            Section("Probe") {
                ForEach(lines, id: \.self) { Text($0).font(.caption.monospaced()) }
            }
        }
        .navigationTitle("art")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear(perform: probe)
    }

    private func probe() {
        guard lines.isEmpty else { return }
        lines = String(cString: dine_art_probe()).split(separator: "\n").map(String.init)
    }

    private func runHello() {
        // `art/` holds the boot jars (xtool.yml); it's also ANDROID_ROOT.
        guard let root = Bundle.main.path(forResource: "art", ofType: nil),
              let jar = Bundle.main.path(forResource: "dine-0001-hello", ofType: "jar"),
              let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
        else {
            return log.error("art: boot jars, hello jar or caches dir missing")
        }
        if dine_art_run(root, caches.path, jar, "Main") != 0 {
            log.notice("art: a run is still active")
        }
    }
}
