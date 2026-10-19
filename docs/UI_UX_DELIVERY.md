# UI/UX delivery — 19 October 2026

This delivery implements WP0 and WP1. WP2–WP8 are explicitly deferred below, as permitted by the definition of done. The full redesign is **not** complete. Existing local changes were preserved; conversion, PDF, compression and background-removal engine behavior was not changed.

## READ: repository and baseline

- `launch_converter.py` selects GUI or CLI; `main.py` is a compatibility entry point.
- `image_converter/ui/main_window.py::ImageConverterMainWindow` owns the header, page stack, Convert composition, intake and job routing.
- `components.py::ConversionSettingsWidget` and `ImagePreviewWidget` own settings and inspection. The active Convert table is `queue_model.py::QueueTableModel` / `QueueTableView`; the older `components.QueueTableWidget` and `nav_rail.NavRailWidget` are not the active main composition.
- `image_tools_page.py::ImageToolsPage` and `pdf_tools_page.py::PdfToolsPage` are launch pages. `tool_dialogs.py` contains `MergeDialog`, `SplitDialog`, `OrganizePagesDialog`, `ImageCompressDialog`, and `CompressDialog`.
- `background_removal_page.py::BackgroundRemovalPage` / `CutoutPreview` already have asynchronous preview/copy paths; `worker.py::BatchConversionWorker` and `background_worker.py::BackgroundRemovalWorker` own the existing batch threads.
- `theme.py` owns QSS/tokens; `contrast.py` previously checked token pairs only. `dev_capture_states.py` was an incomplete capture script.
- Engines are in `image_converter/core/`; background model readiness already exists in `backgroundG/src/bgremove/readiness.py`.
- Both GUI reports and their linked screenshots exist. No blocking input was missing. The current working tree contained substantial pre-existing changes, including engine and UI changes, before this work.

Baseline verification: 39 focused UI tests passed. During WP0, the pre-existing app test set passed **420 tests in 157.60 seconds**. That full run printed recoverable Windows Office COM exception diagnostics; a pytest pass does not establish native Office reliability.

## WP0 — implemented: readable dialogs and control states

**P2, user impact:** dialog headings and labels are now readable without depending on the desktop palette or PNG viewer background. Checkboxes communicate checked and mixed states with visible marks. Spinboxes expose usable up/down controls, including inactive limits.

Ordered work:
1. Inspect the actual screenshot pixels and reproduce transparent dialog surfaces.
2. Resolve QSS cascade order and give each utility dialog an explicit surface/palette.
3. Add small local SVG marks/arrows and explicit normal, checked, mixed, disabled, focused and step-limit states.
4. Audit rendered label backgrounds, including a deliberately bad 2× contrast fixture.
5. Extend and run repeatable captures at both requested window sizes.

Files changed: `image_converter/ui/theme.py`, `contrast.py`, the five constructors/import in `tool_dialogs.py`, `dev_capture_states.py`, local SVG assets, and new `image_converter/tests/test_ui_rendering.py`. Complete applicable diff: [WP0.patch](ui-ux-patches/WP0.patch).

QSS rationale: place opaque top-level rules after transparent child rules; explicitly apply the dialog palette/stylesheet. Keep color, spacing and type tokens. Use a constant indicator border width so focus does not move text or clip a mark. Reserve separate right-hand spinbox button regions, and use `:off` as well as disabled states. No bitmap generation or new dependency is required.

Evidence correction: the supplied PNG backgrounds outside cards are transparent (`RGBA 0,0,0,0`), rather than painted white. Light text disappears when a viewer composites those pixels on white. This confirms an offscreen defect; it does not prove the same appearance occurred on the native Windows desktop. The fixed surfaces are opaque. Native compositor, Windows high contrast and screen-reader behavior remain unverified.

Tests cover actual title/subtitle/label contrast ≥4.5:1 under a light system palette, opaque backgrounds for all five dialogs, three checkbox states, disabled marks, stable focus geometry, radio dots, integer/double spinbox hit regions and step limits. The 2× negative control prevents an incorrect logical/physical coordinate conversion from silently passing the contrast check. The 125% check exposed faint antialiased double-spinbox arrows; spin-only SVG strokes were strengthened without lowering test thresholds. The final 23 rendering tests pass at each of 100%, 125%, 150% and 200% offscreen scaling.

## WP1 — implemented: evidence-based copy and output checks

**P1/P2, user impact:** output destinations no longer carry a false overwrite guarantee; metadata inspection distinguishes absent supported fields from unavailable or failed inspection. Successful conversions expose a check of the actual reported output rather than a blanket cleaning promise.

Ordered work:
1. Audit footer, inspector, settings, launch cards, OCR/password help and compression results against source behavior.
2. Introduce a UI-only metadata evidence adapter with found/not-found/unavailable/failed states.
3. Inspect successful outputs away from the GUI thread without changing engine arguments or result types.
4. Store and display output evidence, including partial coverage for multi-output routes.
5. Describe compressor original-copy fallbacks explicitly and verify the saved copy.

The full old/new/reason table and action vocabulary are in [UI_COPY_AUDIT.md](UI_COPY_AUDIT.md). Complete applicable diff, applied after WP0: [WP1.patch](ui-ux-patches/WP1.patch).

Files changed: `components.py::ImagePreviewWidget` / `ConversionSettingsWidget`; `main_window.py::ImageConverterMainWindow`; `worker.py::BatchConversionWorker`; `queue_model.py::QueueEntry` / `QueueTableModel`; both tool-page classes; compression dialog outcome copy; one background-page subtitle; new `metadata_evidence.py`; capture/result fixtures; UI regression tests. Engine functions and conversion configuration semantics remain unchanged. No new QSS tokens are required by WP1; keyboard-selectable result labels use the existing focus color and a reserved border.

Risk: post-output inspection adds local reads and cannot establish complete sanitization. It reports only supported fields and explicitly identifies unknown/failed checks. Convert checks run in its worker; tool-dialog work and checks remain synchronous until WP2. Where an engine returns one path for multiple output files, the UI labels its inspection coverage as partial. Existing privacy limitations remain in the hand-off below. Existing keyboard shortcuts are preserved; their known hidden-workspace routing remains deferred to WP2.

## WP2 — deferred: reusable embedded workspaces

**P2, remaining impact:** normal Image/PDF Tools still use modal launch paths; the five tool operations and organizer thumbnail rendering remain synchronous. Global commands/drop routing on those pages remain as documented in the GUI report.

Reason for staging: extraction changes all five job lifecycles and the existing synchronous dialog contracts. PDF services currently have no intra-operation progress/cancellation hooks. A worker can keep the UI responsive but cannot truthfully promise immediate cancellation. This needs a separate engine-adjacent patch with immutable inputs and an explicit cancellation contract, rather than being hidden inside palette/copy changes.

Exact targets: five dialog classes in `tool_dialogs.py`, `ImageToolsPage`, `PdfToolsPage`, main-window tool entry points, `_setup_shortcuts`, `dropEvent`, `_build_header`, and worker integration. Order: reusable content/widgets with compatibility wrappers → workers and boundary cancellation → in-page results → active intake/shortcuts → shared job indicator. Tests: existing output/error assertions using event-loop waits; active drop/shortcut routing; responsiveness; retained results; close/cancel safety. Main risk is worker lifetime and mutable UI state during jobs.

## WP3 — deferred: Convert workspace redesign

**P2/P3, remaining impact:** presets still need Custom/mixed handling; defaults, inspector replacement, table layout, rough estimates, row result actions and selectable error details need the requested redesign. WP1 output evidence is a prerequisite, not delivery of WP3.

Reason for staging: these changes share queue identity/selection contracts with the known busy-model defect and should be verified together. Replacing the inspector also intentionally invalidates an existing stacked-inspector test. No calibrated estimator was found; the planned UI must hide uncalibrated values rather than imply calibration.

Exact targets: `ConversionSettingsWidget` preset/context methods, `ImagePreviewWidget`, `QueueEntry`, `QueueTableModel`, `QueueTableView` and its delegates; main-window queue/settings/selection/completion methods. Order: type-aware defaults → presets/Custom → mixed defaults → persistent settings/inspector → table/Actual/result actions → error details. Tests: type defaults; manual preset invalidation; mixed batch behavior; selection preservation; measured-only sizes; output-path actions and error copying. Keep logical column identifiers stable where visual reordering suffices.

## WP4 — deferred: form/table hygiene

**P2/P3, remaining impact:** informational Merge/Image Compress cells remain editable; inactive Split/Fit/Padding fields still need dependent disabling, hints and full-path treatment.

Reason for staging: apply these changes to the reusable controls extracted in WP2, instead of making and then replacing a second form implementation. The one-row Image Compress appearance is caused by vertical crowding despite an existing stretch factor; an extra stretch alone would not resolve it.

Exact targets: `MergeDialog` table construction/refresh, `ImageCompressDialog` table/options, `SplitDialog` mode/range controls, `ConversionSettingsWidget`, `BackgroundRemovalPage`. Order: read-only flags → path elision/tooltips → enablement with retained values → range-count validation using existing parser → flexible file lists. Tests: no editing, full tooltips, mode changes preserve values, valid/invalid ranges and minimum-height layout.

## WP5 — deferred: background layout, readiness and comparison

**P2/P3, remaining impact:** previews still share height with settings; advanced controls lack the requested explanation/reset; there is no synchronized zoom/pan, preview backdrop selector, per-profile readiness display or thumbnail queue. Copy feedback still shares the status area.

Reason for staging: this is a self-contained interaction redesign with asynchronous readiness/thumbnail generation. It needs stale-result and clipboard regressions covered before replacing the existing working page. Preview backdrop settings must remain separate from output background settings.

Exact targets: `BackgroundRemovalPage._build_ui`, `_toggle_advanced`, `_update_model_hint`, intake/selection/copy/status methods, `CutoutPreview`. Order: full-height settings drawer/splitter → help/reset/buddies → linked Fit-relative zoom/pan → preview-only backdrops → asynchronous local readiness/thumbnails → Copy toast. Reuse `resolve_model_directory` separately per profile and `check_models` off-thread; do not download/load inference models for readiness. Tests: minimum-size layout, unchanged engine defaults, relative transform synchronization, stale responses and full-resolution alpha copying.

## WP6 — deferred: organizer and compression presentation

**P2/P3, remaining impact:** organizer still needs multi-select, cached larger thumbnails, size control, undo/redo, contextual actions and dirty/discard handling. WP1 corrects false profile metrics and “already optimal” claims; that does not deliver the wider profile/organizer redesign.

Reason for staging: current organizer mutations rebuild thumbnails and rely on one current row. Multi-selection/history must replace that state model coherently to avoid saving a different page order from the one shown. Drag ordering will remain absent until the complete reorder/save behavior is tested.

Exact targets: `OrganizePagesDialog` loading/rendering/mutation/save methods and `CompressDialog` profile construction. Order: document state/dirty tracking → undo stack → multi-select mutations → cached scalable thumbnails → shortcuts/context actions → outcome-first profiles. Tests: undo/redo restores order/rotation/deletion; discard switching PDFs; multi-page moves; selection preservation; existing save/error behavior.

## WP7 — deferred: shared chrome and typography

**P3, remaining impact:** page headers, selected navigation treatment, badge prominence, decorative cyan and nesting remain outside this patch. The badge explanation may be corrected by WP1 copy work.

Reason for staging: shared header reflow must be designed together with WP8 text scaling; simply enlarging fixed-pixel QSS would overflow the existing header at minimum width. Avoid changing the same page compositions before WP2/WP5 extraction.

Exact targets: main-window `_build_header` / `_set_app_mode`, all four page-header builders, `theme.py`, shared header helper to be introduced. Order: one header pattern → nav selection/badge → reduce nesting/decorative cyan → reflow and type rules. Tests: selected state, contrast and both widths with enlarged text. Do not modify legacy `nav_rail.py` to fix the actual header.

## WP8 — deferred: accessibility, scaling and safe preferences

**P2/P3, remaining impact:** comprehensive field buddies/names/tab paths, Ctrl+1…4, visible shortcut reference, text preference, QSettings/reset and native assistive-technology checks are not complete.

Reason for staging: persistence must use an explicit safe allowlist because current conversion options include passwords. Tests currently assume fresh Convert state, so a settings store must be isolated in tests before persistence is enabled. Fixed-pixel theme rules and custom preview painting also need coordinated high-contrast/scaling work.

Exact targets: main-window initialization, `_setup_shortcuts`, `_setup_tab_order`, `closeEvent`, field builders across pages/dialogs, `CutoutPreview`, theme generation. Order: accessible fields/tab paths → page shortcuts/reference → scalable theme/header → injected QSettings with safe allowlist → reset → native validation. Tests: isolated INI restoration, invalid settings, no persisted passwords, accepted-close geometry, reset without queue loss, scaling and keyboard routes. History remains optional and deferred.

## Reproduce and review captures

Run from the repository root:

```powershell
.\venv\Scripts\python.exe -m image_converter.ui.dev_capture_states --output scratch/ui-ux-after/1380x860 --width 1380 --height 860
.\venv\Scripts\python.exe -m image_converter.ui.dev_capture_states --output scratch/ui-ux-after/1120x700 --width 1120 --height 700
# Repeat with QT_SCALE_FACTOR=1.25, 1.5 or 2 in separate processes/directories.
```

The script captures all four current pages, four PDF selections, all five dialogs, checkbox/stepper states, and Convert empty/single-type/mixed/selected/running/completed/partial-failure states. Completed sizes come from a real PNG→WebP, PDF→TXT, DOCX→TXT, XLSX→CSV sample batch. A real same-format compression fallback demonstrates retained author metadata and the new warning. Running and failure states are deterministic layout fixtures; the manifest states that distinction. It fixes the old script's Image Tools capture mislabeled as PDF Tools.

Before references: existing `scratch/ui-report/01…14` plus `scratch/ui-ux-before/{1380x860,1120x700}`. The older baseline script used simulated completion metrics; those images are historical layout references, not conversion evidence. After references: `scratch/ui-ux-after/{1380x860,1120x700}` and corresponding `ui-ux-after-scale-125`, `-150`, `-200` folders. Each configuration has 23 captures and a manifest, for 184 after captures. [Capture index](UI_UX_CAPTURE_INDEX.html) links every image and before/after pairs. Deferred feature states cannot be captured as implemented states.

## Engine hand-off — deliberately unchanged

| Severity | Required fix and source evidence | User impact / required acceptance |
|---|---|---|
| P1 | Batch-wide output collision planning; main-window planner checks only the current source/destination pair and the image writer uses `os.replace`. | One queued output can replace another input or existing file. Reserve all inputs and planned/multi-file outputs; establish and test a collision policy before restoring safety claims. |
| P1 | Metadata early return and route omissions in `core/conversion/engine.py`; same-format removal returns before resize/quality, while several cross-format routes return before removal. | Requested transformations/cleaning can be skipped. Test combined settings and report route-specific results. |
| P1 | Image compression original-copy fallback in `tool_dialogs.py`; PDF fallback in `core/pdf/tools.py`. | Copying the original can restore metadata and undo requested image transforms. Preserve this existing behavior here, describe it honestly, and separately change the pipeline with explicit semantic-transform tests. |
| P2 | Capability-list mismatches: UI offers PDF→PPTX, Word→PPTX and PPTX→DOCX routes that engine branches reject. | Users can select jobs that cannot run. Introduce one tested authoritative capability source; do not fabricate a registry implementation. |
| P2 | Busy queue model guard and stable job identities; target editors and context removal can bypass toolbar restrictions. | Running row indices/settings can change. Guard mutations at the model and snapshot stable task identities; test every intake/removal/edit route. |

## Executed verification

```powershell
.\venv\Scripts\python.exe -m pytest image_converter/tests backgroundG/tests training/tests -q -rs
# Rendering checks were repeated in fresh processes with QT_SCALE_FACTOR=1, 1.25, 1.5, 2:
.\venv\Scripts\python.exe -m pytest image_converter/tests/test_ui_rendering.py -q
```

- Final combined suite: **797 passed, 3 skipped in 174.57 seconds**, exit code 0. The three skips are existing symlink safety tests: Windows refused symlink creation with WinError 1314. [Full log](../scratch/ui-ux-final-tests.log).
- Rendering/state checks: **23 passed at each of four scale factors** after the final arrow repair; test thresholds were not weakened.
- New truthful-copy checks: **29 cases**; the focused rendering/copy/dialog/model selection set passed 70 tests before final full-suite verification.
- Captures: **184 PNGs** validated for expected logical size × DPR and opaque top-left pixels; all eight capture processes exited successfully. Real sample conversions and actual fallback results are distinguished from layout fixtures in manifests.
- Runtime used: Python 3.14.2, PySide6 6.11.2, pytest 9.1.1 in the existing `venv`. Qt UI checks use the offscreen platform. Office tests emitted recoverable native COM exception diagnostics despite the passing pytest result.

The complete patches contain the changes made here, excluding pre-existing working-tree edits. WP0 applies to that baseline; WP1 applies after WP0. Capture PNGs/logs remain in `scratch/`; their review index is a generated local artifact.

## Verification limits

Offscreen captures, explicit palettes, rendered contrast and widget tests are evidence for the states actually exercised. They do not certify screen readers, native Windows DPI/monitor transitions, Windows high contrast, larger system text or every conversion route. The current minimum-width header still clips navigation labels; that is visible in captures and remains in WP7/WP8. Background result/inference captures from the prior report remain historical references; this capture script does not run background models. The packaged executable was not rebuilt. Its existing spec includes the entire assets directory, including the new SVGs. No telemetry, network calls, model downloads or new heavy dependency were added by these changes.
