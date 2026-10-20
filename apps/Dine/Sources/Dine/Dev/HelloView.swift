#if DEBUG
import CDineHello
import OSLog
import SwiftUI

private let log = Logger(subsystem: "dev.dine.Dine", category: "app")
struct HelloView: View {
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
        .navigationTitle("hello++")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { log.notice("Dine native: \(native, privacy: .public)") }
    }
}
#endif
