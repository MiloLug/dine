import CArtBridge
import OSLog
import SwiftUI

private let log = Logger(subsystem: "dev.dine.Dine", category: "art")

/// Shows the ART platform probe; the run buttons run runtime-suite dex jars in-process. The VM's
/// own output goes to the log (category `art`), not to this view.
struct ArtView: View {
    @State private var lines: [String] = []

    var body: some View {
        List {
            Section {
                Button("run hello") { run("dine-0001-hello") }
                Button("run jni args") { run("dine-0002-jni-args") }
                Button("run https") { run("dine-0003-https") }
                Button("run park") { run("dine-0004-park") }
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

    private func run(_ test: String) {
        // `art/` holds the boot jars (xtool.yml); it's also ANDROID_ROOT.
        guard let root = Bundle.main.path(forResource: "art", ofType: nil),
              let jar = Bundle.main.path(forResource: test, ofType: "jar"),
              let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
        else {
            return log.error("art: boot jars, \(test, privacy: .public).jar or caches dir missing")
        }
        dine_art_run(root, caches.path, jar, "Main")
    }
}
