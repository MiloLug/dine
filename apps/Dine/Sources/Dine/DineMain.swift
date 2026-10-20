import CDbgAgent
import SwiftUI

@main
struct DineMain: App {
    @StateObject private var library = AppLibrary()
    @StateObject private var navigator = Navigator()

    init() {
        dine_dbg_agent_start()
    }

    var body: some Scene {
        WindowGroup {
            LauncherView(library: library)
                .environmentObject(navigator)
        }
    }
}
