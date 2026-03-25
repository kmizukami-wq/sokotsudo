import SwiftUI

@main
struct CRAgentApp: App {
    @StateObject private var coordinator = AgentCoordinator()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(coordinator)
        }
    }
}
