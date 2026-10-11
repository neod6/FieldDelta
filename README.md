# FieldDelta

Experimental physical-site change detection. V1/V2 and a thin native iPhone product shell are implemented. Vision accuracy is NOT production-ready.

The first seven real photos exposed V1 failures. V2 remains separately preserved; see `V2_README.md` and `results/v2/REPORT.md`. These seven photos are development data. Product-shell work is now proceeding independently of the accuracy gate: see `PRODUCT_DEMO.md` and `ios/README.md`.

## Setup

```sh
cd /Users/yiyao.ding/Desktop/比赛/fielddelta
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/smoke_models.py
.venv/bin/python -m unittest discover -s tests -v
```

V1 models download once into `data/models/`. CPU is the default for reproducibility; `--device mps` can be tried on Apple Silicon. V1 photos stay local after model download. The cloud experiment now sends selected photos to Luminal from the Mac, never from the phone; OpenAI calls have stopped. YOLO11 nano detects COCO's 80 categories, not arbitrary equipment. MobileNetV3 Small supplies pretrained crop features; normalized HSV histograms add color evidence. SciPy performs global one-to-one assignment with unmatched slots. No detections are fabricated.

## Real Photo Validation

See [capture instructions](test_images/README.md). Run each pair separately:

```sh
.venv/bin/python scripts/compare_scenes.py --before test_images/scene_01/before.jpg --after test_images/scene_01/after.jpg --output results/scene_01
.venv/bin/python scripts/compare_scenes.py --before test_images/scene_02/before.jpg --after test_images/scene_02/after.jpg --output results/scene_02
```

Each output contains `result.json`, internal `descriptors.json`, annotated photos and actual object crops. Thresholds are explicit in `backend/matching.py`. Matching scores are not calibrated confidence probabilities. Object IDs are scan-local, not yet persistent stable IDs.

Constraints: fixed viewpoint, similar lighting, visible objects. Movement means image-plane displacement, not 3D motion. Occlusion and detector misses can appear as removal/addition. Similar same-category objects can be ambiguous and are flagged for review. All unmatched objects are review-required. Do not interpret this as an inventory guarantee.

Phase 0 requires manual checking against real physical changes: changed scene detects the intended added/removed/moved items while retaining unchanged items, and a no-change control creates no false changes. Public-photo smoke tests and synthetic unit tests do not satisfy this gate. Test thresholds are provisional, not tuned to user photos.

## Product Gate

SQLite snapshots/events, FastAPI, a native SwiftUI scanner and a minimal local desktop dashboard now exist as an experimental shell. Real authentication, ARKit and RoomPlan are not implemented. Their availability does not certify vision accuracy. OpenAI failed with HTTP 429 `credit_balance_exhausted`; Luminal image input and the no-change double-image control succeeded, but other development pairs remain unreliable. See `results/luminal/REPORT.md`.

## Desktop Site Memory

Open http://127.0.0.1:8000/ on the Mac while the existing backend is running.
The dashboard shows account/site, current candidate memory, last-seen timestamps,
latest recorded changes and clickable real scan history with detection overlays.
No frontend dependencies, build step or separate server are required.
See `frontend/README.md` for startup and persistence details.

Existing SQLite scans/results are retained. Additive `registry_objects` and
`observations` tables preserve saved identity evidence, including missing objects.
NOT_OBSERVED is not REMOVED; uncertain matches remain provisional.
The real iPhone mouse-removal audit is saved at `results/real_iphone_audit/REPORT.md`.
This work does not change the V2 vision pipeline or its decision thresholds.

Selected baseline objects can now be explicitly enrolled from the same dashboard.
An additional conservative controlled-removal layer searches the whole rescan and
uses Luminal verification; ambiguous visibility remains NOT_OBSERVED.
See `CONTROLLED_REMOVAL.md` for the gates and measured real mouse result.
The native Mac wrapper is `macos/FieldDelta.xcodeproj`; see `macos/README.md`.

## Sources And Licensing

- YOLO11: https://docs.ultralytics.com/models/yolo11/
- MobileNetV3 Small: https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.mobilenet_v3_small.html
- Assignment: https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html

Ultralytics software/weights use AGPL-3.0 or a commercial enterprise license. Review licensing before proprietary commercial distribution. The public bus photo is used solely as a runtime smoke fixture, not as evidence of physical-change accuracy.
# Inspection Sessions

See [INSPECTION_SESSIONS.md](INSPECTION_SESSIONS.md) for the new-inspection flow,
preserved scan history, and the latest real-iPhone/cloud verification audit.
