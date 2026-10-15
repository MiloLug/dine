import SwiftUI

@main
struct DineMain: App {
    @StateObject private var library = AppLibrary()

    var body: some Scene {
        WindowGroup {
            LauncherView(library: library)
        }
    }
}
