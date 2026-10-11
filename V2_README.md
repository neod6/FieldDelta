# FieldDelta Phase 0 V2

Development-only feasibility pipeline. V1 code and raw results are preserved. No frontend, SwiftUI, cloud or Luminal work.

## Run

```sh
cd /Users/yiyao.ding/Desktop/比赛/fielddelta
.venv/bin/python -m pip install -r requirements-v2.txt
.venv/bin/python scripts/prepare_v2_models.py
.venv/bin/python scripts/evaluate_v2.py --registration-only
.venv/bin/python scripts/evaluate_v2.py
.venv/bin/python -m unittest discover -s tests -v
```

Model preparation needs network access once. Evaluation explicitly runs offline. Grounding DINO tiny and DINOv2 small use safetensors without remote code. Inference is local CPU, four torch threads, image limit 1600 pixels. One fixed broad prompt list is used on all seven development photos. Model boxes are proposals, not authoritative objects.

## Components

- `backend/v2/registration.py`: SIFT, ratio matching, RANSAC homography, matches/inliers/errors/spatial support, AFTER-to-BEFORE coordinates. Poor registration requests rescan and suppresses confident movement. Homography cannot guarantee correction of parallax across table, screen and background planes.
- `backend/v2/models.py`: open-vocabulary detection, duplicate-box suppression, DINOv2 crop embeddings, color features. Raw semantic suggestions remain available. NMS does not eliminate all overlapping/part-object false proposals.
- `backend/v2/tracking.py`: Hungarian one-to-one instance matching, soft semantic penalty, registered displacement, visual/size/aspect/color features, UNKNOWN and NOT_OBSERVED. New objects are enrollment proposals rather than immediately accepted ADDED events. Missing objects are NOT_OBSERVED rather than unsupported REMOVED events.
- `data/v2/site.json`: manual tabletop ROI in IMG_3377 coordinates, declared once, warped for other photos. Low-confidence ROI transfer also requests rescan. No per-photo cherry-picked inventory filters.

## Registry Workflow

`results/v2/registry_proposal.json` stores deterministic stable IDs, names, reference crops/embeddings, semantic suggestions, positions and observation timestamps. Entries are unconfirmed, including possible false detector proposals. The diagnostic registry preview uses provisional IDs; it is not a user-confirmed registry.

An operator must inspect crops, then supply a JSON mapping actual candidate IDs to chosen display names. `scripts/confirm_v2_registry.py --registry ... --names ... --output ...` performs this isolated confirmation step. `observe_registry` re-identifies enrolled identities and maintains stable IDs, recent reference crops/embeddings, last-seen state and position; UNKNOWN does not erase last-seen data. Registry persistence uses JSON for Phase 0 only, not the future product database.

Absence or a new detection alone cannot establish physical removal/addition. Automated REMOVED and ADDED are deliberately not yet emitted. This is a real functional limitation, not a successful zero-false-positive detection score. No-change results must report coverage and uncertainty as well as the four original event counts.

## Fresh Validation

All seven current images are DEVELOPMENT ONLY. Freeze the V2 source and settings before running new images. The initial runner refuses to overwrite an output directory:

```sh
.venv/bin/python scripts/compare_v2_scenes.py --before test_images/fresh_validation/unchanged/before.jpg --after test_images/fresh_validation/unchanged/after.jpg --roi 0 0.28 1 1 --output results/v2_validation/unchanged_initial
```

The example ROI must be replaced by the actual inspection rectangle declared on the new baseline before evaluating predictions. Do not adjust thresholds/prompts based on the new validation set before reporting initial results.

Needed fresh pairs: no-object-change control, camera-only translation with unchanged objects, and real moved/added/removed objects at a fixed camera position. Include laptop, silver can, black earbud case and white mouse as distinct visible objects; test black fabric too. Use a new arrangement and leave objects visible. Record exact physical actions. JPEG is currently the tested path; supplied HEIC can be converted with macOS image services without changing originals.

Sources: [Grounding DINO](https://huggingface.co/docs/transformers/v4.55.4/en/model_doc/grounding-dino), [DINOv2](https://huggingface.co/facebook/dinov2-small). Review model licensing before commercial distribution. No licensing clearance is claimed by this prototype.
