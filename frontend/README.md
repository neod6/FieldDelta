# FieldDelta Desktop

Local-only, buildless management dashboard served by the existing FastAPI backend.
Open http://127.0.0.1:8000/ on the Mac. No additional dependencies or frontend API keys.

Start the existing backend from the project root:

```sh
.venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

The dashboard reads real SQLite records and saved local/cloud evidence. It never runs
vision or uploads synthetic scans. Polling refreshes processing and scan history.
The phone remains the capture/upload client.

## Recording Layout

The header remains outside both independent scroll regions. The inspection timeline
scrolls inside the sidebar; all main content scrolls inside the workspace. The page
itself is constrained to the viewport. Active inspection, prioritized change results,
and up to six current object summaries are visible first. Remaining candidates and
all raw IDs, confidence components, matching records, and cloud JSON stay available
under expandable sections. Detection overlays are off by default.

The current state always describes the active inspection. Selecting a historic scan
changes Scan Detail only, with that scan's inspection number clearly displayed.
Historical selection and expanded session groups survive automatic refresh.
The Mac WKWebView wrapper and browser use these same HTML/CSS/JS files.

Verified at 1440x810 and 1280x720 with real saved scans, without browser zoom.
Main scroll, sidebar scroll, fixed header, old-session selection, and evidence expansion
were checked through the browser. The real FieldDelta.app was reloaded and confirmed
to display the same dashboard. Four presentation tests pass:

```sh
node --test tests/test_dashboard.cjs
```

No backend, model, threshold, schema, session behavior, or iPhone changes are part of
this UI update. During verification two genuine iPhone uploads created a new session;
the prior records remain unchanged except for the old session becoming inactive.

`registry_objects` retains prior detector IDs, status, detector confidence, last seen
timestamp and scan. `observations` records per-scan detection and uncertainty evidence.
These are additive projections of existing results; old results and counts are unchanged.
Enrollment metadata is current registry state, not a historical confirmation snapshot.
Absent detections do not become REMOVED. Previously uncertain identity assignments remain
provisional; this is not a production inventory or a newly improved identity tracker.

The server has demo-only authentication and HTTP. Keep it on a trusted demonstration
network; it is not suitable for public deployment. Production requires HTTPS and real
access control. All processing and keys stay on the Mac.
## Persistent Identity And Product View

Default Product View uses enrolled registry identities and accepted fusion decisions,
not a new confidence cutoff. Raw AI mode preserves the stored detector labels,
boxes and scores, including ignored proposals. Counts continue to be measured
pipeline totals; uncertainty counts may include raw observations hidden in Product View.

Baseline Memory Review includes thumbnails and explicit selection, Rename and
Ignore/Restore. No automatic enrollment. Renames are stored in SQLite
`object_corrections`, keyed by site and stable registry ID, with the original AI
label, operator source and timestamp. Confirming baseline names persists the same
correction. Ignoring a confirmed tracked identity is rejected. Changes do not
rewrite historical scans, detector output, observations or change events.

The iPhone already displays the backend `object_results[].label`; it receives
corrected product names on its next result fetch without a client rebuild.
Existing results cached on the phone need a new fetch; desktop polling is live.
This is persistent site memory, not model-weight fine-tuning. An unresolved
identity or an object outside the existing ROI remains Needs Review. Renaming
does not make the visual match more certain.
