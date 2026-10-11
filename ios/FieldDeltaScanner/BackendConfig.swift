import Foundation

enum BackendConfig {
    // Configure the Mac address in the app's Server field. No API keys belong here.
    static let defaultURL = "http://104.39.143.77:8000"
    static var urlString: String {
        get {
            guard let saved = UserDefaults.standard.string(forKey: "backendURL"),
                  let host = URL(string: saved)?.host,
                  !["127.0.0.1", "localhost", "::1", "fielddelta.local"].contains(host) else { return defaultURL }
            return saved
        }
        set { UserDefaults.standard.set(newValue, forKey: "backendURL") }
    }
}
