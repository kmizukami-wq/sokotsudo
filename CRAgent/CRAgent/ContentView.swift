import SwiftUI

struct ContentView: View {
    @EnvironmentObject var coordinator: AgentCoordinator
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            AgentDashboardView()
                .navigationTitle("CR Agent")
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button {
                            showSettings = true
                        } label: {
                            Image(systemName: "gearshape.fill")
                        }
                    }
                }
                .sheet(isPresented: $showSettings) {
                    SettingsView()
                }
        }
    }
}
