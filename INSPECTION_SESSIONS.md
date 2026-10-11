# Inspection Sessions and Real Scan Audit

## Product flow

The site is permanent; each inspection has its own baseline, registry file,
confirmation selections, comparison lineage, and current-state projection.
New inspections are created atomically with their baseline upload, not when the
camera is opened. Cancelling a capture therefore does not create an empty session.

iPhone: Demo Warehouse -> Loading Area -> Start New Inspection -> Capture New
Baseline -> Upload. On the Mac, select only the intended baseline objects under
Confirm Baseline. Remove the mouse, then return to the iPhone inspection options
and choose Continue Current Inspection -> Scan Again -> Upload.

The physical-device build succeeds with the existing Personal Team. The phone
was unavailable to device tools during verification, so this update still needs
to be installed using Xcode Run while NEO-X max is connected and unlocked.

## Persistence and APIs

- `inspection_sessions`: id, site_id, created_at, baseline_scan_id, active, legacy.
- `scans.session_id`: fixed at upload, including queued scans.
- `GET /sites/{id}/sessions`: history groups, newest first, numbered per site.
- `GET /sites/{id}/state`: active session only for latest scan, registry, and memory.
- `POST /sites/{id}/scan`: original multipart fields plus `new_inspection=true`
  for a new baseline and `session_id` to reject stale inspection selections.
- Continuing waits for the current session baseline and any pending scan.
- Processing compares only with earlier completed scans from the same session.
- A queued old-session scan retains its original session even after a new one starts.
- Old-session details/removal reviews load that session's registry, not the active one.
- Registry files for new sessions live at `data/sites/{site}/sessions/{id}/registry.json`.
- Historic scans are assigned a legacy session without rewriting their original
  result, scan type, or previous-scan links. No inferred session split by time gap.

`object_results` is shared by the phone and desktop. Confirmed objects without a
strong appearance match are displayed as POSSIBLY_MISSING / Needs review when
the existing controlled-removal evidence abstains. This presentation does not
create a REMOVED ChangeEvent or an invented confidence score. Final event counts
remain the measured decision counts; possibly-missing names are a review overlay.

## Real iPhone scans, October 11 (New York time)

- 17:21:38: `296681c9-a96d-44af-ab36-cfea1a4f27a0` was originally compared
  with the 16:40:33 scan, instead of being a fresh baseline.
- 17:22:04: `2b08d64e-a7b3-4822-aad3-b4e821b50921` compared with 17:21:38.
- Both uploads and local processing succeeded. Both original records contain
  `Cloud verification failed: ValidationError`.
- The original service discarded the exception's `cloud_metadata`. No raw
  failed response or validation field details were saved. The precise original
  offending field, malformed/missing/enum classification, and HTTP status cannot
  be recovered reliably. These must not be guessed from later responses.
- The old wrapper creates ValidationError only during strict Comparison parsing,
  after an SDK response with finish_reason=stop. This is evidence of an output
  validation failure rather than the ordinary transport-error path, but is not
  a substitute for the missing original HTTP/response record.

## Cloud replay and narrow parser changes

Actual replays sent the images together and retained the original local context
and registration evidence. The original 17:21 comparison replay parsed with HTTP
200 in 6.435 s. The final 17:21 -> 17:22 replay parsed with HTTP 200 in 7.194 s,
using 5,692 prompt and 1,233 completion tokens (6,925 total). No normalization was
needed on either of these successful responses. Successful retries therefore do
not demonstrate which original formatting error occurred.

The normalization layer handles only a whole JSON code fence, ID-only wrappers
in decision arrays, and exact named x1/y1/x2/y2 coordinates. It does not add
required fields, infer IDs, change decisions, repair malformed JSON, or accept
conflicting categories/out-of-range geometry. Strict semantic validation remains.
Future errors persist sanitized raw model output, HTTP status, token usage, and
precise Pydantic field errors in `results/product_scans/{id}/cloud_error.json`.

Replay responses and parsed evidence: `results/session_audit/first_cloud_parsed.json`
and `results/session_audit/cloud_parsed.json`. The final replay is also persisted
in the additive `cloud_reviews` table; original `scans.result_json` is retained.
Desktop and phone APIs expose the newer review with its review timestamp.

The final hybrid decision remains Added 0, Removed 0, Moved 0, Unchanged 0,
Uncertain 11. Mouse is prominently POSSIBLY_MISSING / Needs review. The model
also hallucinated a mouse elsewhere and confused mouse/pen identity in one
response. Schema validity does not imply visual correctness. No permanent
REMOVED event was accepted.

The original confirmed mouse's absence review measured max local DINO similarity
0.341, but the targeted detector proposed a very broad laptop-region "mouse"
(DINO 0.023) and the independent absence verifier confidence was 0.70, below the
existing 0.90 requirement. Those existing vetoes remain unchanged.

## Verification

34 unique backend tests pass, including manual new baseline, same-session links,
old history/restart preservation, stale client rejection, pending baseline safety,
late old-session processing, presentation-only missing flags, and strict parser
normalization/rejection. JavaScript syntax passes. Signed iOS device build passes.
The real Mac wrapper loads session-grouped history and the mouse warning from
the same backend/SQLite. Real phone capture/install testing is pending device
reconnection, not reported as completed.

No detector, DINO, registration, matching, or removal thresholds changed.
