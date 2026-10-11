import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results'/'v2'
scans={p.parent.name:json.loads(p.read_text()) for p in sorted(OUT.glob('IMG_*/scan.json'))}
baseline=json.loads((ROOT/'results'/'user_batch'/'summary.json').read_text())['scans']
evaluation=json.loads((OUT/'evaluation.json').read_text())
registrations=json.loads((OUT/'registration.json').read_text())
previews=json.loads((OUT/'registry_preview.json').read_text())['scans']
roi_regs=json.loads((OUT/'roi_registration.json').read_text())

lines=['# FieldDelta V2 Development Report','',
       '**FIELDDELTA V2 STILL NOT RELIABLE**','',
       'All seven images are DEVELOPMENT data. User-confirmed truth: 3377/3378 have no physical changes; 3376 has significant camera translation; black earbud case and white mouse are distinct objects. Other exact actions remain visual interpretations, not retrospectively edited truth.',
       '', '## Implementation', '',
       'Separate V2 modules implement SIFT/RANSAC homography, AFTER-to-BEFORE coordinates, geometric quality gates, DINOv2-small crop embeddings, soft semantic scoring, Hungarian matching, a declared tabletop ROI, stable provisional registry IDs with explicit operator confirmation, and UNKNOWN/NOT_OBSERVED states. V1 modules and raw evidence remain intact.',
       '', '## Detector Comparison: Every Photo', '',
       'Grounding DINO tiny used one fixed broad 16-term prompt list and fixed 0.25 detection/text thresholds on every photo. No per-photo wording or threshold edits. Duplicate proposals with IoU >0.65 are merged; incomplete/part boxes still survive. Numbers below count retained raw proposals, NOT true physical objects.',
       '', '| Photo | V1 proposals | V2 proposals | V1 silver can | V2 silver can | Visual review |',
       '| --- | ---: | ---: | --- | --- | --- |']
notes={
 'IMG_3372':('missed','can drink .74','Can, clear bottle and snack packages recovered; earbud case has duplicate boxes; chairs mislabeled computer outside ROI.'),
 'IMG_3373':('cup .42','drink .76','Can and packages recovered; earbud case proposals include overlarge/duplicate boxes.'),
 'IMG_3374':('bottle .67','drink .75','Large black fabric detected as fabric clothing .42. A strap is falsely labeled earbud case; genuine case visibility is uncertain.'),
 'IMG_3375':('missed','can drink .70','Real white mouse detected .87; earbud-case proposals are erroneous large laptop/table regions.'),
 'IMG_3376':('missed','drink .54','Silver and green cans separately detected; real white mouse .86. Earbud-case proposals are erroneous large regions.'),
 'IMG_3377':('missed','can drink .63','White mouse .86 and black earbud case .40 have separate real boxes. Border fragments and a false cup remain.'),
 'IMG_3378':('missed','can drink .67','White mouse .88 and black earbud case .41 have separate real boxes. False cup and partial bottle proposals remain.')}
for name,scan in scans.items():
    old,new,note=notes[name]
    lines.append(f'| {name} | {len(baseline[name]["objects"])} | {len(scan["objects"])} | {old} | {new} | {note} |')
lines+=['', 'Silver-can region coverage improves from 2/7 to 7/7. This is manual visual review of a specific visible target, NOT full open-world recall or precision. Both detectors find the laptop 7/7. The added black fabric in 3374 is found by V2 and missed by V1. Grounding DINO improves coverage but still hallucinates object categories/parts; raw results cannot serve as inventory.',
        '', 'Selection: Grounding DINO tiny plus DINOv2-small for this development prototype because it installs and runs locally with substantially improved target coverage. Only this one open-vocabulary detector was benchmarked; no claim it beats all alternatives. All model weights are cached, inference explicitly offline, remote code disabled and safetensors used.',
        '', '## Registration: Every Pair', '',
        'Metrics are internal geometric fit diagnostics on images capped at 1600 pixels, not externally measured registration accuracy. Confidence requires >=30 inliers, >=40% inlier ratio, median <2.5px, p90 <4px, >=4 occupied grid cells, and plausible mapped frame geometry. A single homography assumes an approximately planar scene.',
        '', '| Pair | Matches | Inliers | Inlier ratio | Median / p90 error px | Pair geometry gate |',
        '| --- | ---: | ---: | ---: | --- | --- |']
for key,r in registrations.items():
    lines.append(f'| {key.replace("IMG_", "").replace("__", " -> ")} | {r["matches"]} | {r["inliers"]} | {100*r["inlier_ratio"]:.1f}% | {r["median_reprojection_px"]:.3f} / {r["p90_reprojection_px"]:.3f} | {"PASS" if r["reliable"] else "UNCERTAIN"} |')
lines+=['',f'{sum(r["reliable"] for r in registrations.values())}/21 pair transforms pass the global geometry gate. Transferring the declared ROI from 3377 additionally fails for 3375 and 3376; these paths return REGISTRATION_UNCERTAIN / RESCAN_RECOMMENDED rather than trusting that ROI alignment.',
        '', '## All Pair Outputs', '',
        'ADDED/REMOVED are not automatically emitted from unmatched detections in this V2. New proposals require confirmation; absence remains NOT_OBSERVED. Therefore zero ADDED/REMOVED is not evidence of correct change-detection sensitivity.',
        '', '| Pair | Added | Removed | Moved | Unchanged | Unknown | Not observed |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for pair in evaluation['pairs']:
    c=pair['counts']
    lines.append(f'| {pair["before"].replace("IMG_", "")} -> {pair["after"].replace("IMG_", "")} | '+ ' | '.join(str(c[k]) for k in ['ADDED','REMOVED','MOVED','UNCHANGED','UNKNOWN','NOT_OBSERVED'])+' |')
lines+=['', '## Confirmed No-Change Control: 3377 -> 3378', '',
        'V1: 4 false additions, 0 moves, 0 removals, 6 unchanged detections.',
        'V2: 0 MOVED, 0 REMOVED, 0 ADDED, 8 matched UNCHANGED proposals, 1 UNKNOWN, 2 NOT_OBSERVED. The eight are detector proposals and include a false cup, not eight verified physical objects. Core laptop, silver can, white mouse and black earbud case correctly match as separate unchanged objects. The three uncertain proposals mean the complete inventory is not cleanly resolved.',
        'Residual displacement: laptop .00103, silver can .00020, white mouse .00033, black earbud case .00373 (normalized image coordinates). White mouse and earbud case use different one-to-one assignments, not a collapsed class identity.',
        '', '## Camera-Shift Cases', '',
        '3375 -> 3376: pair fit has 571 matches, 285 inliers (49.9%), median .508px, p90 .988px. However baseline-ROI transfer is uncertain, so final laptop/mouse states are UNKNOWN, not confidently UNCHANGED. Zero MOVED here is safe abstention, not a full correction success.',
        'Residual motion still exists: white mouse raw .2057 -> residual .0667; laptop correction improves, but multiple scene planes/parallax prevent a globally trustworthy physical-motion decision.',
        'Crucially, other 3376 pairs still report likely false laptop moves: 3372 -> 3376 residual .0582, 3373 -> 3376 .0680, 3374 -> 3376 .0787. A low SIFT/RANSAC fit error can coexist with wrong object-plane compensation. This directly fails the camera-shift development target. No threshold was raised to hide those failures.',
        '', '## Silver-Can Identity And Registry', '',
        '3372 -> 3373: can drink -> drink still matches despite semantic mismatch, DINO cosine .785, residual .3085, classified MOVED. 3373 -> 3374: same instance cosine .940, residual .0067, UNCHANGED.',
        'The persistent baseline registry at 3377 has stable provisional UUIDs, reference crops/embeddings, names, semantic suggestions, last position and last-seen observation timestamp. All entries remain unconfirmed. Explicit operator confirmation is implemented separately; no human confirmation has been fabricated.',
        'The silver-can baseline candidate preview across all seven scans:', '',
        '| Scan | Stable provisional ID | State | Matched candidate | Visual similarity |',
        '| --- | --- | --- | --- | --- |']
for name,p in previews.items():
    event=next(e for e in p['events'] if e.get('before_id')=='candidate_003')
    sim=event.get('evidence',{}).get('visual_similarity')
    lines.append(f'| {name} | {event["object_id"]} | {event["type"]} | {event.get("after_id")} | {sim:.3f} |' if sim is not None else
                 f'| {name} | {event["object_id"]} | {event["type"]} | None | unavailable |')
lines+=['', 'The baseline identity is not recovered in 3372 and remains uncertain in 3375/3376. Therefore cross-view/site-wide identity continuity is NOT solved merely by 7/7 detection coverage.',
        '', '## Earbud Case, Mouse And Fabric', '',
        'In 3377/3378, white mouse and black earbud case are distinct regions and independently match: DINO cosine .965 and .922 respectively. This test succeeds. Across other frames, case proposals are missing, overlarge or on a strap, so identity continuity across all seven does not pass.',
        '3374 black fabric region is directly detected (.42), but inconsistent proposals/occlusion and absence handling prevent a validated automatic ADDED/REMOVED story. Unmatched registry objects remain NOT_OBSERVED; outside aligned field of view is distinguished from insufficient visual evidence. Occlusion vs actual removal is not yet inferred robustly.',
        '', '## Latency', '',
        '| Photo | Grounding DINO sec | DINOv2 crops sec | Total extraction sec |',
        '| --- | ---: | ---: | ---: |']
for name,scan in scans.items():
    d,e=scan['latency_seconds'],scan['embedding_seconds']
    lines.append(f'| {name} | {d:.3f} | {e:.3f} | {d+e:.3f} |')
det=statistics.mean(s['latency_seconds'] for s in scans.values())
emb=statistics.mean(s['embedding_seconds'] for s in scans.values())
reg=statistics.mean(r['latency_seconds'] for r in registrations.values())
lines+=['',f'CPU extraction mean {det+emb:.3f}s/photo ({det:.3f}s detector + {emb:.3f}s crop embeddings); registration mean {reg:.3f}s/pair. Weights initialization/download, phone upload and UI are excluded. V1 extraction mean .328s/photo; resolutions/models/thread settings differ, so this is observed workflow latency rather than a controlled model-only benchmark.',
        '', '## Remaining Blockers And Decision', '',
        '1. Global homography does not reliably compensate for multiple planes; false laptop moves persist in camera-shift pairs.',
        '2. Open-world coverage is better, but spurious/duplicate/part proposals prevent dependable automatic enrollment.',
        '3. Silver-can and earbud-case identity continuity remains incomplete across all seven views.',
        '4. ADDED/REMOVED need explicit enrollment/absence evidence; this prototype cannot automatically establish both from one pair.',
        '5. The real registry is awaiting user selection. No test evidence is counted as user-confirmed enrollment.',
        '', '19 unit tests pass, including compensated motion, poor-registration abstention, soft semantic labels, one-to-one same-label identities, stable registry IDs, confirmation isolation, and preservation of last seen on UNKNOWN/NOT_OBSERVED. Unit tests are not visual accuracy evidence.',
        '', 'V2 is an architectural improvement, not a passed Phase 0. Stop development now and collect fresh photos; no UI or SwiftUI has been built. The next run must report untouched initial results before tuning. Existing seven images are never called holdout.',
        '', '**FIELDDELTA V2 STILL NOT RELIABLE**']
(OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(f'Report: {OUT / "REPORT.md"}')
