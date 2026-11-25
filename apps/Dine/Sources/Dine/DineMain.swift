import SwiftUI

@main
struct DineMain: App {
    @StateObject private var library = AppLibrary()
    @StateObject private var navigator = Navigator()

    var body: some Scene {
        WindowGroup {
            LauncherView(library: library)
                .environmentObject(navigator)
        }
    }
}
