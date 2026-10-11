# FieldDelta for macOS

Open `FieldDelta.xcodeproj` and run the FieldDelta scheme on My Mac.
Local ad-hoc signing is sufficient; no Personal Team, provisioning profile or distribution setup is required.

Build from the project root:

```sh
xcodebuild -project macos/FieldDelta.xcodeproj -scheme FieldDelta -configuration Debug -derivedDataPath macos/build build
```

App: `macos/build/Build/Products/Debug/FieldDelta.app`.
Double-click it in Finder. The app checks http://127.0.0.1:8000/health and embeds the
existing dashboard in WKWebView when available. Open in Browser uses the same URL
in the system default browser. No database, dashboard copy or vision models are embedded.

If offline, Start Local Backend runs the existing `.venv/bin/python -m uvicorn`
from the project folder, binding 0.0.0.0:8000. It checks health first and avoids
starting its own process twice. Output appends to `macos/logs/backend.log`.
The development backend stays running after the wrapper closes so iPhone uploads
continue. Configure the single project path / URLs in `LocalConfiguration` in
`FieldDelta/FieldDeltaApp.swift` if the project moves.

DEVELOPMENT ONLY: HTTP ATS exception and disabled App Sandbox allow this local
hackathon wrapper to use the Python checkout. No keys are bundled. Do not distribute
this as a production app; production requires HTTPS and a proper backend lifecycle.

## Verified On This Mac

- Xcode 26.3 Debug build: BUILD SUCCEEDED.
- Ad-hoc codesign: valid on disk, satisfies Designated Requirement.
- Real app launched and WKWebView displayed Demo Warehouse / Loading Area,
  the two real iPhone scans, and confirmed Mouse with NOT OBSERVED state.
- With the owned backend stopped, the friendly offline screen appeared.
- Start Local Backend successfully launched the existing Python environment,
  bound 0.0.0.0:8000, passed /health, and restored the same history.
- Open in Browser opened http://127.0.0.1:8000/ in the system default Chrome.
- Enrollment/review persisted across backend restart. Web and native views use
  the same server, SQLite database and uploaded image files.
