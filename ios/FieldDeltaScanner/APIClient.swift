import Foundation
import UIKit

struct DemoAccount: Decodable, Identifiable { let id: String; let name: String }
struct Site: Decodable, Identifiable {
    let id: String
    let accountId: String
    let name: String
    let hasBaseline: Int
}
struct InspectionSession: Decodable { let id: String; let number: Int }
struct SiteState: Decodable {
    let hasBaseline: Bool
    let hasHistory: Bool?
    let activeSession: InspectionSession?
}
struct ServerHealth: Decodable { let status: String }
struct Counts: Decodable {
    let added: Int
    let removed: Int
    let moved: Int
    let unchanged: Int
    let uncertain: Int
}
struct ScanResult: Decodable {
    let mode: String
    let counts: Counts
    let warning: String?
}
struct ScanRecord: Decodable, Identifiable {
    let id: String
    let scanType: String
    let processingStatus: String
    let error: String?
    let result: ScanResult?
    let sessionId: String?
    let objectResults: [ObjectResult]?
}

struct ObjectResult: Decodable, Identifiable {
    let objectId: String
    let label: String
    let status: String
    let reason: String
    var id: String { objectId }
}

enum ClientError: LocalizedError {
    case message(String)
    static let connectionMessage = "Cannot reach FieldDelta server. Check that your iPhone and Mac are on the same network."
    static func userMessage(for error: Error) -> String {
        if error is URLError || (error as NSError).domain == NSURLErrorDomain { return connectionMessage }
        if let known = error as? ClientError { return known.errorDescription ?? "Please try again." }
        if error is DecodingError { return "FieldDelta server returned an unreadable response." }
        return "Something went wrong. Please try again."
    }
    var errorDescription: String? {
        switch self { case .message(let text): return text }
    }
}

struct APIClient {
    let baseURL: URL
    private var decoder: JSONDecoder {
        let value = JSONDecoder()
        value.keyDecodingStrategy = .convertFromSnakeCase
        return value
    }

    func get<T: Decodable>(_ path: String) async throws -> T {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.timeoutInterval = 30
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(data, response)
        return try decoder.decode(T.self, from: data)
    }

    func upload(_ photo: UIImage, account: DemoAccount, site: Site, newInspection: Bool, sessionId: String?) async throws -> ScanRecord {
        guard let pixels = photo.cgImage,
              let image = UIImage(cgImage: pixels, scale: 1, orientation: .up).jpegData(compressionQuality: 0.85) else {
            throw ClientError.message("Could not encode the captured photo.")
        }
        // Send unrotated sensor pixels plus their orientation; the Mac bakes it once.
        let orientation: Int
        switch photo.imageOrientation {
        case .up: orientation = 1
        case .upMirrored: orientation = 2
        case .down: orientation = 3
        case .downMirrored: orientation = 4
        case .leftMirrored: orientation = 5
        case .right: orientation = 6
        case .rightMirrored: orientation = 7
        case .left: orientation = 8
        @unknown default: orientation = 1
        }
        let boundary = "FieldDelta-\(UUID().uuidString)"
        var body = Data()
        func append(_ value: String) { body.append(Data(value.utf8)) }
        var fields = ["account_id": account.id, "site_id": site.id,
                      "timestamp": ISO8601DateFormatter().string(from: Date()),
                      "new_inspection": newInspection ? "true" : "false",
                      "image_orientation": String(orientation)]
        if let sessionId { fields["session_id"] = sessionId }
        for (key, value) in fields {
            append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(key)\"\r\n\r\n\(value)\r\n")
        }
        append("--\(boundary)\r\nContent-Disposition: form-data; name=\"image\"; filename=\"scan.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n")
        body.append(image)
        append("\r\n--\(boundary)--\r\n")
        var request = URLRequest(url: baseURL.appendingPathComponent("sites/\(site.id)/scan"))
        request.httpMethod = "POST"
        request.timeoutInterval = 90
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        let (data, response) = try await URLSession.shared.upload(for: request, from: body)
        try validate(data, response)
        return try decoder.decode(ScanRecord.self, from: data)
    }

    private func validate(_ data: Data, _ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else { throw ClientError.message("Invalid server response.") }
        if !(200..<300).contains(http.statusCode) {
            let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            throw ClientError.message(json?["detail"] as? String ?? "Server error \(http.statusCode).")
        }
    }
}
