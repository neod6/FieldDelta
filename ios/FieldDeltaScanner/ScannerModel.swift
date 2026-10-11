import SwiftUI
import UIKit

@MainActor
final class ScannerModel: ObservableObject {
    enum Screen { case login, sites, scan, preview, processing, result }
    @Published var screen: Screen = .login
    @Published var server = BackendConfig.urlString
    @Published var email = "demo@fielddelta.local"
    @Published var password = ""
    @Published var emailError: String?
    @Published var passwordError: String?
    @Published var accounts: [DemoAccount] = []
    @Published var sites: [Site] = []
    @Published var account: DemoAccount?
    @Published var site: Site?
    @Published var hasBaseline = false
    @Published var hasHistory = false
    @Published var activeSession: InspectionSession?
    @Published var newInspection = false
    private var uploadSessionId: String?
    @Published var photo: UIImage?
    @Published var error: String?
    @Published var loading = false
    @Published var phase = "Uploading..."
    @Published var latestScan: ScanRecord?
    private var pendingScanID: String?

    private func client() throws -> APIClient {
        guard let url = URL(string: server.trimmingCharacters(in: .whitespacesAndNewlines)),
              ["http", "https"].contains(url.scheme ?? ""), url.host != nil,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil else {
            throw ClientError.message("Enter a valid Mac backend URL.")
        }
        #if !targetEnvironment(simulator)
        guard !["127.0.0.1", "localhost", "::1"].contains(url.host ?? "") else {
            throw ClientError.message("On a real iPhone, use your Mac's Wi-Fi IP, not localhost.")
        }
        #endif
        BackendConfig.urlString = url.absoluteString
        return APIClient(baseURL: url)
    }

    func signIn() async {
        error = nil
        emailError = email.contains("@") ? nil : "Enter a valid email."
        passwordError = password.count >= 5 ? nil : "Password must contain at least 5 characters."
        guard emailError == nil, passwordError == nil else { return }
        loading = true; error = nil
        defer { loading = false }
        do {
            let health: ServerHealth = try await client().get("health")
            guard health.status == "ok" else { throw ClientError.message(ClientError.connectionMessage) }
            accounts = try await client().get("accounts")
            guard let demo = accounts.first(where: { $0.id == "demo-warehouse" }) else {
                throw ClientError.message("Demo account is unavailable.")
            }
            try await selectAccount(demo)
            password = ""
            screen = .sites
        } catch { self.error = ClientError.userMessage(for: error) }
    }

    func selectAccount(_ selection: DemoAccount) async throws {
        let all: [Site] = try await client().get("sites")
        account = selection
        sites = all.filter { $0.accountId == selection.id }
        site = nil
    }

    func selectSite(_ selection: Site) async {
        loading = true; error = nil
        defer { loading = false }
        do {
            let state: SiteState = try await client().get("sites/\(selection.id)/state")
            site = selection; hasBaseline = state.hasBaseline
            hasHistory = state.hasHistory ?? state.hasBaseline
            activeSession = state.activeSession
            photo = nil; latestScan = nil; pendingScanID = nil
            screen = .scan
        } catch { self.error = ClientError.userMessage(for: error) }
    }

    func captured(_ image: UIImage) { photo = image; error = nil; screen = .preview }

    func chooseInspection(new: Bool) {
        newInspection = new
        uploadSessionId = activeSession?.id
    }

    func returnToScan() async {
        guard let site else { return }
        await selectSite(site)
    }

    func upload() async {
        guard let photo, let account, let site else { return }
        error = nil; screen = .processing; phase = "Uploading..."
        do {
            let record = try await client().upload(photo, account: account, site: site,
                                                   newInspection: newInspection, sessionId: uploadSessionId)
            pendingScanID = record.id
            try await poll(record.id)
        } catch {
            self.error = ClientError.userMessage(for: error)
            screen = pendingScanID == nil ? .preview : .processing
        }
    }

    func resumeProcessing() async {
        guard let pendingScanID else { return }
        error = nil
        do { try await poll(pendingScanID) }
        catch { self.error = ClientError.userMessage(for: error) }
    }

    private func poll(_ id: String) async throws {
        phase = "Processing..."
        for _ in 0..<180 {
            try Task.checkCancellation()
            let record: ScanRecord = try await client().get("scans/\(id)")
            if record.processingStatus == "complete" {
                guard record.result != nil else { throw ClientError.message("Scan completed without a result.") }
                latestScan = record; hasBaseline = true; pendingScanID = nil
                hasHistory = true
                screen = .result; return
            }
            if record.processingStatus == "failed" { throw ClientError.message(record.error ?? "Scan failed.") }
            phase = record.processingStatus == "queued" ? "Queued..." : "Processing..."
            try await Task.sleep(for: .seconds(2))
        }
        throw ClientError.message("Processing is taking longer than expected. Check status again.")
    }
}
