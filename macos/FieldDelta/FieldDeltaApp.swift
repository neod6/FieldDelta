import AppKit
import SwiftUI
import WebKit

enum LocalConfiguration {
    static let dashboardURL = URL(string: "http://127.0.0.1:8000/")!
    static let healthURL = dashboardURL.appendingPathComponent("health")
    static let projectDirectory = "/Users/yiyao.ding/Desktop/比赛/fielddelta"
}

@MainActor
final class BackendConnection: ObservableObject {
    @Published var available = false
    @Published var checking = true
    @Published var starting = false
    @Published var message = ""
    private var process: Process?
    private var logHandle: FileHandle?

    func check() async {
        checking = true
        defer { checking = false }
        var request = URLRequest(url: LocalConfiguration.healthURL)
        request.timeoutInterval = 3
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            available = (response as? HTTPURLResponse)?.statusCode == 200 && json?["status"] as? String == "ok"
        } catch {
            available = false
        }
    }

    func start() async {
        guard !starting else { return }
        starting = true
        defer { starting = false }
        await check()
        guard !available else { return }
        if process?.isRunning != true {
            let root = URL(fileURLWithPath: LocalConfiguration.projectDirectory)
            let executable = root.appendingPathComponent(".venv/bin/python")
            guard FileManager.default.isExecutableFile(atPath: executable.path) else {
                message = "Local project environment is unavailable. Start the backend from the project folder."
                return
            }
            do {
                let logs = root.appendingPathComponent("macos/logs")
                try FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
                let log = logs.appendingPathComponent("backend.log")
                if !FileManager.default.fileExists(atPath: log.path) {
                    FileManager.default.createFile(atPath: log.path, contents: nil)
                }
                logHandle = try FileHandle(forWritingTo: log)
                try logHandle?.seekToEnd()
                let child = Process()
                child.executableURL = executable
                child.currentDirectoryURL = root
                child.arguments = ["-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
                child.standardOutput = logHandle
                child.standardError = logHandle
                try child.run()
                process = child
            } catch {
                message = "Could not start the local backend. Check macos/logs/backend.log."
                return
            }
        }
        for _ in 0..<20 {
            try? await Task.sleep(for: .seconds(1))
            await check()
            if available { message = ""; return }
            if process?.isRunning == false { break }
        }
        message = "The backend has not become available. Check macos/logs/backend.log."
    }
}

struct DashboardWebView: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> WKWebView {
        let view = WKWebView(frame: .zero)
        view.load(URLRequest(url: url))
        return view
    }

    func updateNSView(_ view: WKWebView, context: Context) {}
}

struct ContentView: View {
    @StateObject private var connection = BackendConnection()
    @State private var revision = UUID()

    var body: some View {
        Group {
            if connection.available {
                DashboardWebView(url: LocalConfiguration.dashboardURL).id(revision)
            } else {
                VStack(spacing: 20) {
                    Text("FieldDelta").font(.largeTitle).fontWeight(.semibold)
                    if connection.checking {
                        ProgressView("Checking local backend...")
                    } else {
                        Text("FieldDelta backend is not running.").foregroundStyle(.secondary)
                        Button(connection.starting ? "Starting..." : "Start Local Backend") {
                            Task { await connection.start() }
                        }.disabled(connection.starting)
                        Button("Open in Browser") { openBrowser() }
                        if !connection.message.isEmpty {
                            Text(connection.message).font(.callout).foregroundStyle(.secondary)
                                .multilineTextAlignment(.center).frame(maxWidth: 480)
                        }
                    }
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .frame(minWidth: 800, minHeight: 600)
        .toolbar {
            ToolbarItemGroup {
                Button { Task { await connection.check(); revision = UUID() } } label: {
                    Label("Open Desktop Dashboard", systemImage: "arrow.clockwise")
                }.help("Check backend and reload dashboard")
                Button { openBrowser() } label: {
                    Label("Open in Browser", systemImage: "safari")
                }.help("Open the same dashboard in the default browser")
            }
        }
        .task { await connection.check() }
    }

    private func openBrowser() {
        NSWorkspace.shared.open(LocalConfiguration.dashboardURL)
    }
}

@main
struct FieldDeltaApp: App {
    var body: some Scene {
        WindowGroup("FieldDelta") { ContentView() }
            .defaultSize(width: 1280, height: 900)
    }
}
