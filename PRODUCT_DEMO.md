# FieldDelta Experimental Product Shell

## Status

The native SwiftUI project has passed a signed build for NEO-X max, was installed and launched on the physical iPhone, and the simulator login/site-selection flow connects to the actual backend. Rear-camera operation, phone-side health access and photo upload still require physical-phone interaction and verification. Vision is NOT production-ready.

V2 registration, ROI, DINOv2, Hungarian matching, registry and UNKNOWN/NOT_OBSERVED are preserved unchanged. Product processing runs on the Mac. Baselines are provisional candidate enrollment, not confirmed inventory. Added/Removed are intentionally not accepted automatically without independent supporting evidence.

## Mac Backend

```sh
cd /Users/yiyao.ding/Desktop/比赛/fielddelta
.venv/bin/python -m pip install -r requirements-product.txt
.venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Local API documentation: http://127.0.0.1:8000/docs

This API has DEMO authentication only. It does not enforce real user authorization. Use a trusted network, do not forward port 8000, and do not expose it to the public internet. HTTP is a development setting, not suitable for sensitive field photographs. Uploaded data and SQLite live only on the Mac; cloud-enabled comparisons also send two reduced-resolution photos to Luminal.

Routes: `GET /accounts`, `GET /sites?account_id=...`, `GET /sites/{id}/state`, `GET /sites/{id}/scans`, `POST /sites/{id}/scan`, `GET /scans/{id}`, `GET /scans/{id}/image`, `GET /sites/{id}/registry`.

Upload is multipart with `account_id`, `site_id`, timezone-qualified ISO-8601 `timestamp`, `image`. Response 202 contains a scan ID; poll `/scans/{id}` until complete/failed. JPEG, PNG and HEIC are supported (20 MB / 30 MP limits). Photos are EXIF-oriented and reduced before processing. Single-worker queuing bounds local model memory. Interrupted processing resumes on restart. All result counts come from persisted backend decisions.

Defaults: Demo Warehouse has Storage A and Loading Area; Campus Lab has Desk 01 and Equipment Room. Equipment Room is used for actual development-photo transport checks; failed test history remains visible. Storage A starts empty for the first phone scan.

## Cloud And Hybrid

`.env` is ignored and mode 0600. It is loaded by absolute project-root path. Luminal uses `LUMINAL_API_KEY`, `LUMINAL_BASE_URL=https://flash.luminal.cloud/v1` and `LUMINAL_MODEL=deepseek-ai/DeepSeek-V4.1-Flash`. If the key is absent, the Mac reuses the existing ignored sibling `autoevolve/.env`; nothing is copied to the phone. OpenAI requests are no longer made. `CLOUD_VISION_ENABLED=false` disables photo transmission. No credential is present in iOS source.

Both images are submitted together through OpenAI-compatible Chat Completions on Luminal. The endpoint supports JSON object mode but rejects JSON Schema mode with HTTP 400. The Mac validates seven required fields, unique physical identities, normalized boxes, exactly one decision per identity and uncertainty reasons; invalid responses are rejected, not silently repaired. Reasoning is disabled using the existing Luminal configuration, with 3500 output tokens. HTTP 503 receives at most three attempts with 2/5-second backoff plus jitter. Local evidence includes registration, ROI, semantic suggestions, DINO evidence and registry IDs. Confidence is heuristic, not calibrated.

The hybrid accepts sufficiently strong independent MOVED/UNCHANGED agreement only. Unmatched objects, disagreement, unreliable registration and unsupported Added/Removed remain UNCERTAIN. The underlying local UNKNOWN/NOT_OBSERVED states remain available in local evidence; uncertainty counts are observations requiring review, not guaranteed unique inventory counts. There is no automatic second-verification request yet.

```sh
.venv/bin/python scripts/benchmark_hybrid.py
```

The benchmark supports the existing 21 development-photo pairs only, cloud-only plus cloud-with-local-evidence then hybrid fusion. Requests run sequentially, successes are fingerprint-cached, and comparison history is retained. Four representative pairs covering all seven development photos were tested, not all 21 pairs. Fresh validation data is excluded. The no-change control passed the zero-confident-change criterion, but three other final pairs failed identity consistency validation in at least one mode. See `results/luminal/REPORT.md` and `results/luminal_development/summary.json`. Previous OpenAI failures are preserved separately in `results/hybrid_development/`.

## Verification

24 unit tests cover V1/V2, API validation/persistence, hybrid/schema logic and bounded Luminal retries; transport fixtures do NOT establish vision accuracy. `scripts/test_product_live.py` submits real IMG_3377 and IMG_3378 to Equipment Room and writes actual outputs to `results/product_live_test.json`. The existing live-test file records the earlier OpenAI-era run. Cloud failure conservatively yields unverified local observations, never invented confident results.

OpenAI implementation references: https://developers.openai.com/api/docs/guides/images-vision?api-mode=responses and https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses
