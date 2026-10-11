import SwiftUI

@main
struct FieldDeltaScannerApp: App {
    @StateObject private var model = ScannerModel()
    var body: some Scene {
        WindowGroup { ContentView().environmentObject(model).tint(.teal) }
    }
}
