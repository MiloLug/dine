import SwiftUI

struct LauncherView: View {
    @ObservedObject var library: AppLibrary

    @State private var showAdd = false
    @State private var newName = ""

    private let columns = Array(repeating: GridItem(.flexible()), count: 4)

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVGrid(columns: columns, spacing: 24) {
                    ForEach(library.apps) { app in
                        AppIconView(app: app)
                    }
                }
                .padding()
            }
            .overlay {
                if library.apps.isEmpty {
                    ContentUnavailableView(
                        "No Apps", systemImage: "square.grid.2x2",
                        description: Text("Tap + to add one."))
                }
            }
            .navigationTitle("Apps")
            .toolbar {
                ToolbarItemGroup(placement: .topBarLeading) {
                    NavigationLink("hello++") { HelloView() }
                    NavigationLink("probe") { ProbeView() }
                    NavigationLink("art") { ArtView() }
                    NavigationLink("atl") { AtlView() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        newName = ""
                        showAdd = true
                    } label: {
                        Image(systemName: "plus")
                    }
                    .accessibilityLabel("Add App")
                }
            }
            .alert("Add App", isPresented: $showAdd) {
                TextField("Name", text: $newName)
                Button("Cancel", role: .cancel) {}
                Button("Add") { library.add(name: newName) }
                    .disabled(newName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
    }
}
