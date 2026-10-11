# Run FieldDelta On A Physical iPhone

1. Open `/Users/yiyao.ding/Desktop/比赛/fielddelta/ios/FieldDeltaScanner.xcodeproj` in Xcode. Select scheme `FieldDeltaScanner`.
2. Connect your unlocked iPhone with a USB cable. Trust the Mac on the phone. In iPhone Settings > Privacy & Security enable Developer Mode if requested, then follow the restart/confirmation prompts.
3. In the target's Signing & Capabilities select your Apple ID Personal Team (add it in Xcode Settings > Accounts if needed). Keep automatic signing. The bundle identifier is `com.yiyaoding.fielddelta.scanner.demo`; it is valid and personalized, but uniqueness is confirmed only by provisioning. Change its suffix if Xcode reports a collision. No paid-only capabilities are enabled.
4. Choose your physical iPhone as the run destination, NOT the iPhone 17 Pro simulator. The Mac currently detects **NEO-X max**, an **iPhone 16 Plus**, as connected; signing/installation/capture have not been tested. Press Run. If requested, trust your development certificate in iPhone Settings > General > VPN & Device Management. Minimum iOS version: 17.
5. Start the Mac backend as described in `../PRODUCT_DEMO.md`. Put Mac and phone on the same trusted Wi-Fi. In the app login screen's **Server** field enter `http://104.39.143.77:8000`, the current Wi-Fi (en0) address. This is now prefilled. This single value persists on the phone. Old localhost defaults are migrated; physical-device builds explicitly reject localhost. The fallback constant is in `FieldDeltaScanner/BackendConfig.swift`; do not scatter IP addresses through the source. Update this field when the Mac address changes.
6. Before signing in, open `http://104.39.143.77:8000/health` in iPhone Safari. It must return JSON. Allow Mac firewall access for the server if prompted. Campus/guest Wi-Fi may isolate devices even on the same SSID. This address is NOT RFC1918-private: only use the demo service on a trusted network with inbound access appropriately restricted; do not assume it is isolated from the internet. The Mac-side health request succeeded, but the phone-side request is still unverified. Do not use `127.0.0.1` on a physical phone.
7. Enter any email containing `@` and any password with at least five characters. Sign In first checks the backend health endpoint and then loads the predefined Demo Warehouse; there is no authentication request and the password is neither sent nor saved. Never use a real password for this demo. Invalid email shows `Enter a valid email.`; a short password shows `Password must contain at least 5 characters.`. Network failures show `Cannot reach FieldDelta server. Check that your iPhone and Mac are on the same network.` rather than a raw networking exception.
8. Select Storage A or Loading Area (Campus Lab is optional). Tap Capture Baseline, permit Camera and Local Network access, and take a rear-camera photo. Review it, Retake if necessary, then Upload Scan. Wait for actual backend counts. Subsequent captures show Scan Again. Baseline objects remain provisional; cloud failures and ambiguous comparisons are marked uncertain.

Debug uses **NSAllowsArbitraryLoads=true only** under NSAppTransportSecurity. This is DEVELOPMENT ONLY for the hackathon's configurable IP-address HTTP backend. Do not also add NSAllowsLocalNetworking inside that dictionary: on current iOS its presence overrides NSAllowsArbitraryLoads to false. NSLocalNetworkUsageDescription is separate and remains configured, as does NSCameraUsageDescription. Release has no ATS exceptions and requires HTTPS by default. Do not distribute the Debug security configuration as a production app.

The latest interface inspection still finds `104.39.143.77/16` assigned directly to Wi-Fi en0. No RFC1918 Wi-Fi IPv4 is currently available. `169.254.1.41` belongs to a separate link-local interface, not the intended same-Wi-Fi demo network. The current URL candidate is `http://104.39.143.77:8000`, not a guessed private address or an internet public-IP lookup. Mac-side health succeeds; only a phone-side health/login request proves whether Wi-Fi peer access is allowed. If the phone cannot reach it, use a trusted shared Wi-Fi or hotspot and re-read the Mac Wi-Fi IPv4; do not assume this campus/public-looking network permits device-to-device connections.

Latest update: signed Debug build for NEO-X max succeeded with zero errors/warnings; the updated app was installed and launched on the physical phone. Camera opening and photo upload still need phone interaction and backend-log confirmation. No vision pipeline files were changed.

Apple ATS rule: https://developer.apple.com/documentation/bundleresources/information-property-list/nsapptransportsecurity/nsallowsarbitraryloads

The simulator validates login/site layout but cannot prove real rear-camera capture, device signing or Wi-Fi connectivity. No API key, model, database or heavy vision processing is bundled in this app.

## Landscape Orientation Fix

Upload sends raw CGImage pixels and the UIImage capture orientation as the EXIF
numeric `image_orientation` multipart field. The backend bakes that orientation
into the pixels before resizing, detection, DINO, registration, cloud vision or
display. Embedded non-default EXIF takes precedence to avoid double rotation.
Original upload bytes and a small orientation audit record are retained beside
the canonical JPEG. No CSS rotation is used.

Reinstall this client update before testing new landscape captures. The signed
arm64 physical-device Debug build succeeded; NEO-X max was unavailable during
verification, so installing and testing a new capture still require reconnecting
the phone and pressing Run in Xcode.
