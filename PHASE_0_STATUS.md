# Phase 0 Status

Project created from scratch at `/Users/yiyao.ding/Desktop/比赛/fielddelta`.
AutoEvolve was not modified.

Implemented: real YOLO11 nano detection, pretrained MobileNetV3 Small crop embeddings, HSV color representation, label/appearance/spatial/size costs, one-to-one assignment with unmatched slots, ADDED/REMOVED/MOVED/UNCHANGED JSON, annotated images and object crops.

Measured local CPU smoke result:

- Official public bus photo: 5 actual detections (1 bus, 4 people).
- Identical-photo repeat: 5 UNCHANGED, 0 ADDED, 0 REMOVED, 0 MOVED.
- First detection plus crop descriptors: 0.226 seconds; model loading/download excluded.
- 8 matching-logic unit tests pass; these inputs are synthetic and do not validate detector accuracy.
- Dependencies pass `pip check`.

Evidence: `results/model_smoke/smoke.json`. This is runtime validation only, not physical-change validation. Weight downloads initially required network permission and a proper CA bundle; TLS verification remains enabled. Subsequent inference uses local cached weights.

Gate: **REAL_PHOTOS_TESTED_BASELINE_NOT_PASSED**.

V2 update: **FIELDDELTA V2 STILL NOT RELIABLE**. Separate V2 code adds SIFT/RANSAC registration, DINOv2 instance descriptors, Grounding DINO open-vocabulary comparison, tabletop ROI, explicit baseline registry confirmation, and UNKNOWN/NOT_OBSERVED. The confirmed unchanged pair has zero definitive change events but three unresolved proposals; false laptop moves persist in other camera-shift pairs. All 21 development comparisons are reported in `results/v2/REPORT.md`. Request a new six-photo validation set as described in `test_images/fresh_validation/README.md`; do not tune before reporting initial fresh results. No product UI was built.

Seven user HEIC photos (IMG_3372 through IMG_3378) have now been tested. All 21 pair comparisons are saved in `results/user_batch/evaluation.json`. Mean extraction latency is 0.328 seconds/photo. Laptop detection is stable (7/7), but silver-can detection is only 2/7 with inconsistent labels. The likely unchanged pair 3377/3378 produces four likely false additions; exact pair identities await user confirmation. See `results/user_batch/REPORT.md` for measured results and visual review. The initial requested capture instructions below remain historical guidance, not a claim that photos are still missing.

Required files:

- `test_images/scene_01/before.jpg`
- `test_images/scene_01/after.jpg`
- `test_images/scene_02/before.jpg`
- `test_images/scene_02/after.jpg`

Scene 01: keep a laptop, remove a cup, move a bottle, add a book. Fixed supported rear-camera position, unchanged zoom and lighting. Scene 02: two photos of a different arrangement with nothing moved. See `test_images/README.md` for capture details.

Do not mark Phase 0 passed until actual pairs are compared and checked against physical truth. No SQLite, dashboard or SwiftUI implementation yet; their directories are reserved for after this gate.
