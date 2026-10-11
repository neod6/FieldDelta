import SwiftUI
import AVFoundation

struct ContentView: View {
    @EnvironmentObject var model: ScannerModel
    @State private var showingCamera = false

    var body: some View {
        NavigationStack {
            Group {
                switch model.screen {
                case .login: login
                case .sites: sites
                case .scan: scan
                case .preview: preview
                case .processing: processing
                case .result: result
                }
            }
            .navigationTitle("FieldDelta")
            .navigationBarTitleDisplayMode(.inline)
            .safeAreaInset(edge: .bottom) {
                if let error = model.error {
                    Text(error).font(.footnote).foregroundStyle(.red)
                        .padding().frame(maxWidth: .infinity).background(.regularMaterial)
                }
            }
            .fullScreenCover(isPresented: $showingCamera) { CameraView(onCapture: model.captured).ignoresSafeArea() }
        }
    }

    private var login: some View {
        Form {
            Section {
                Label("FieldDelta", systemImage: "viewfinder").font(.largeTitle.bold()).padding(.vertical, 12)
                Text("Demo Sign In").foregroundStyle(.secondary)
                TextField("Email", text: $model.email).textContentType(.emailAddress)
                    .keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
                    .accessibilityIdentifier("login.email")
                if let error = model.emailError { Text(error).font(.footnote).foregroundStyle(.red) }
                SecureField("Password", text: $model.password)
                    .accessibilityIdentifier("login.password")
                if let error = model.passwordError { Text(error).font(.footnote).foregroundStyle(.red) }
                Text("Demo access: use any password with 5+ characters.")
                    .font(.footnote).foregroundStyle(.secondary)
                Button { Task { await model.signIn() } } label: {
                    HStack { Text("Sign In"); Spacer(); if model.loading { ProgressView() } else { Image(systemName: "arrow.right") } }
                }.disabled(model.loading).accessibilityIdentifier("login.submit")
            }
            Section("Server") {
                TextField("http://Mac-IP:8000", text: $model.server)
                    .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                    .accessibilityIdentifier("login.server")
            }
        }
    }

    private var sites: some View {
        List {
            Section("Demo Account") {
                ForEach(model.accounts) { account in
                    Button { Task {
                        do { try await model.selectAccount(account) }
                        catch { model.error = ClientError.userMessage(for: error) }
                    } } label: {
                        HStack { Text(account.name); Spacer(); if model.account?.id == account.id { Image(systemName: "checkmark") } }
                    }
                }
            }
            Section("Sites") {
                ForEach(model.sites) { site in
                    Button { Task { await model.selectSite(site) } } label: {
                        HStack { Image(systemName: "building.2"); Text(site.name); Spacer(); Image(systemName: "chevron.right") }
                    }.disabled(model.loading)
                }
            }
        }
        .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Sign Out") { model.screen = .login } } }
    }

    private var scan: some View {
        VStack(spacing: 28) {
            siteHeading
            Spacer()
            Image(systemName: "camera.viewfinder").font(.system(size: 100)).foregroundStyle(.teal)
            if model.hasHistory {
                if let session = model.activeSession {
                    Text("Inspection #\(session.number)").foregroundStyle(.secondary)
                }
                Button { model.chooseInspection(new: true); Task { await openCamera() } } label: {
                    VStack(spacing: 4) {
                        Label("Start New Inspection", systemImage: "plus.viewfinder")
                        Text("Capture New Baseline").font(.caption)
                    }.frame(maxWidth: .infinity).padding(.vertical, 8)
                }.buttonStyle(.borderedProminent)
                Button { model.chooseInspection(new: false); Task { await openCamera() } } label: {
                    VStack(spacing: 4) {
                        Label("Continue Current Inspection", systemImage: "camera")
                        Text("Scan Again").font(.caption)
                    }.frame(maxWidth: .infinity).padding(.vertical, 8)
                }.buttonStyle(.bordered).disabled(!model.hasBaseline)
            } else {
                Button { model.chooseInspection(new: true); Task { await openCamera() } } label: {
                    Label("Capture Baseline", systemImage: "camera").frame(maxWidth: .infinity).padding(.vertical, 12)
                }.buttonStyle(.borderedProminent)
            }
            Spacer()
            Text("Experimental").font(.footnote).foregroundStyle(.secondary)
        }.padding(24)
        .toolbar { ToolbarItem(placement: .topBarLeading) { Button { model.screen = .sites } label: { Image(systemName: "chevron.left") }.accessibilityLabel("Sites") } }
    }

    private var preview: some View {
        VStack(spacing: 16) {
            siteHeading
            Text(model.newInspection ? "New Inspection · Baseline" : "Current Inspection · Comparison")
                .font(.subheadline).foregroundStyle(.secondary)
            if let photo = model.photo {
                Image(uiImage: photo).resizable().scaledToFit().frame(maxHeight: .infinity)
            }
            HStack {
                Button { Task { await openCamera() } } label: { Label("Retake", systemImage: "camera.rotate") }
                    .buttonStyle(.bordered)
                Spacer()
                Button { Task { await model.upload() } } label: { Label("Upload Scan", systemImage: "arrow.up.circle") }
                    .buttonStyle(.borderedProminent)
            }
        }.padding()
        .toolbar { ToolbarItem(placement: .topBarLeading) { Button { model.screen = .scan } label: { Image(systemName: "chevron.left") }.accessibilityLabel("Back") } }
    }

    private var processing: some View {
        VStack(spacing: 24) {
            siteHeading
            Spacer()
            if model.error == nil { ProgressView().controlSize(.large) }
            Text(model.phase).font(.title2)
            if model.error != nil {
                Button("Check Status") { Task { await model.resumeProcessing() } }.buttonStyle(.borderedProminent)
                Button("Sites") { model.screen = .sites }
            }
            Spacer()
        }.padding()
    }

    private var result: some View {
        List {
            Section {
                Label("Scan Complete", systemImage: "checkmark.circle").font(.title2)
                siteHeading
            }
            if let response = model.latestScan?.result {
                Section {
                    countRow("Added", value: response.counts.added, color: .green)
                    countRow("Removed", value: response.counts.removed, color: .red)
                    countRow("Moved", value: response.counts.moved, color: .orange)
                    countRow("Unchanged", value: response.counts.unchanged, color: .secondary)
                    countRow("Uncertain", value: response.counts.uncertain, color: .orange)
                }
                if let warning = response.warning { Section { Text(warning).font(.footnote).foregroundStyle(.secondary) } }
            }
            objectSections
            Section {
                Button { Task { await model.returnToScan() } } label: { Label("Inspection Options", systemImage: "camera") }
                Button("Sites") { model.screen = .sites }
            }
        }
    }

    @ViewBuilder private var objectSections: some View {
        let items = model.latestScan?.objectResults ?? []
        ForEach(["REMOVED", "POSSIBLY_MISSING", "ADDED", "MOVED", "UNCHANGED", "UNCERTAIN"], id: \.self) { status in
            let matching = items.filter { $0.status == status }
            if !matching.isEmpty {
                Section("\(status == "POSSIBLY_MISSING" ? "Possibly Missing" : status.capitalized) (\(matching.count))") {
                    ForEach(matching) { item in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(item.label).font(.headline)
                            if status == "POSSIBLY_MISSING" || status == "UNCERTAIN" {
                                Text("Needs review").font(.footnote).foregroundStyle(.orange)
                            }
                        }
                    }
                }
            }
        }
    }

    private var siteHeading: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(model.account?.name ?? "").font(.subheadline).foregroundStyle(.secondary)
            Text(model.site?.name ?? "").font(.title2.bold())
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private func countRow(_ title: String, value: Int, color: Color) -> some View {
        HStack { Text(title); Spacer(); Text(value, format: .number).monospacedDigit().foregroundStyle(color) }
    }

    private func openCamera() async {
        guard UIImagePickerController.isSourceTypeAvailable(.camera) else {
            model.error = "A physical iPhone camera is required."; return
        }
        let authorized = AVCaptureDevice.authorizationStatus(for: .video) == .authorized
        var allowed = authorized
        if !allowed { allowed = await AVCaptureDevice.requestAccess(for: .video) }
        if allowed { model.error = nil; showingCamera = true }
        else { model.error = "Camera access denied. Enable it in iPhone Settings." }
    }
}
