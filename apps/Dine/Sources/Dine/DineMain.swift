import SwiftUI

@main
struct DineMain: App {
    @StateObject private var library = AppLibrary()
    @StateObject private var navigator = Navigator()

    init() {
        #if DEBUG
        startDevServices()
        #endif
    }

    var body: some Scene {
        WindowGroup {
            LauncherView(library: library)
                .environmentObject(navigator)
        }
    }
}
