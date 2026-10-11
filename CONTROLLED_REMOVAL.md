# Controlled Removal Demo

The original V2 detector prompts, registration thresholds, DINO encoder, Hungarian
matching and UNKNOWN / NOT_OBSERVED behavior remain unchanged. An optional target
prompt is used only for a second, whole-image detector search.

## Operator Flow

1. Capture/upload a baseline from the iPhone.
2. In the existing Mac/web dashboard, expand **Confirm Baseline**.
3. Select only the real objects to track; optionally rename them, then confirm.
   Unconfirmed detector proposals are not enrolled. Confirmation is stored in
   SQLite `registry_enrollments`; the existing registry remains the geometry/
   appearance source, with enrollment flags loaded from SQLite.
4. Upload a rescan. The Mac backend checks missing confirmed identities automatically.
5. Existing completed rescans can be reviewed with **Verify Missing Tracked Objects**.

## Acceptance Gates

All must pass: operator-confirmed identity; existing reliable registration; full
projected target box inside the frame; no strong or plausible DINO match across
ALL current detections (including outside ROI); completed second target-specific
search across the WHOLE AFTER image with no plausible detector proposals;
independent cloud verification of visible/unoccluded region, absence, and no
plausible relocation, with heuristic confidence >= 0.90.

Missing/unavailable/failed cloud verification remains NOT_OBSERVED because this
minimal implementation has no separate local occlusion-certification model.
No original threshold is relaxed. This intentionally favors abstention.
REMOVED means absent from the monitored visible region, not proof of departure
from an entire warehouse or physical destruction.

## Persistence

Original scan results are not rewritten during retrospective verification.
SQLite `removal_reviews` retains verification time, outcome and exact evidence.
Only accepted removal creates a REMOVED ChangeEvent (idempotent per scan/object).
API views merge accepted reviews into effective results and counts. Current memory
is updated only if the reviewed scan is still the object's latest assessment;
last-seen time is never advanced by an absence check. Pending reviews recover on
backend restart. Previously accepted removals remain removed until a new observation.

## Real Mouse Result

Replayed the existing real iPhone Loading Area pair after explicitly confirming
ONLY Mouse. This is retrospective verification, not a new capture or a claim that
enrollment preceded the original rescan.

- Baseline: `7eb90cb7-49cb-4da3-b475-9629bd8012f4`.
- Rescan: `da16a782-4a30-4114-b66b-ffbd4dc1bdbd`.
- Mouse registry ID: `cfb679ce-8b7e-5967-93a0-a1bc01d3b687`.
- No strong local match: maximum DINO similarity 0.319060.
- Whole-image mouse-only second search: zero detections; 3.605 seconds.
- Registration: 220/568 inliers = 0.387324; existing minimum remains 0.40.
- Luminal DeepSeek-V4.1-Flash verification: HTTP 200, 2.651 seconds,
  prompt/completion tokens 2554/119. Model says visible/unoccluded region,
  absent target, no plausible relocation, but confidence only 0.62.
- Outcome: **NOT_OBSERVED**. Alignment/coverage gate and cloud-confidence gate fail.
- Actual REMOVED events written for Loading Area: **0**.

Full measured evidence: `results/controlled_removal/real_mouse.json`.
Positive REMOVED acceptance/persistence is covered by explicitly synthetic unit
fixtures; it has NOT yet been demonstrated on a fresh physical-iPhone pair.
For the next controlled capture, retain the original framing and cover the target's
surrounding tabletop. Do not assume improved framing guarantees acceptance.
