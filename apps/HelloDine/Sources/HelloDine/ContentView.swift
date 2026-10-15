import CDineHello
import OSLog
import SwiftUI

private let log = Logger(subsystem: "dev.dine.HelloDine", category: "app")

struct ContentView: View {
    private let native = String(cString: dine_hello())

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "globe")
                .imageScale(.large)
                .foregroundStyle(.tint)
            Text("Hello, world!")
            Text(native)
                .font(.footnote.monospaced())
                .multilineTextAlignment(.center)
        }
        .padding()
        .onAppear { log.notice("HelloDine native: \(native, privacy: .public)") }
    }
}
