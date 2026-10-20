#if DEBUG
import CDbgAgent
import SwiftUI

/// Dine's dev screens on the launcher's stack.
enum DevScreen: Hashable {
    case hello, probe, art, atl
}

extension View {
    /// The launcher's links to the dev screens, and their destinations.
    func devScreens() -> some View {
        toolbar {
            ToolbarItemGroup(placement: .topBarLeading) {
                NavigationLink("hello++", value: DevScreen.hello)
                NavigationLink("probe", value: DevScreen.probe)
                NavigationLink("art", value: DevScreen.art)
                NavigationLink("atl", value: DevScreen.atl)
            }
        }
        .navigationDestination(for: DevScreen.self) { screen in
            switch screen {
            case .hello: HelloView()
            case .probe: ProbeView()
            case .art: ArtView()
            case .atl: AtlView()
            }
        }
    }
}

/// The debug agent (native/dev/dbgagent); it listens only when launched with DINE_DBG_AGENT_PORT.
func startDevServices() {
    dine_dbg_agent_start()
}
#endif
