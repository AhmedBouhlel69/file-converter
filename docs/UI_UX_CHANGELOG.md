# UI change log — 19 October 2026

**Delivered: WP0–WP1. The full redesign remains staged.**

- **WP0 / P2:** all five utility dialogs have explicit opaque dark surfaces and readable headings/labels. Checked/mixed/disabled checkboxes have visible marks and stable focus rings. Spinbox arrows have separate hit areas and inactive-limit states; stronger strokes address fractional scaling.
- **WP1 / P1–P2:** removed unsafe source-preservation and universal privacy promises, scoped OCR/password help, corrected PDF profile details, and described compressor unchanged-copy fallbacks and output growth. Convert stores actual output paths and shows supported-field checks, including unavailable/failed inspection. These are UI checks, not comprehensive sanitization.
- Conversion arguments, engine behavior, existing shortcuts and local processing are preserved. No heavy dependency, telemetry, network call or download was added.

| Deferred | Reason and remaining user impact |
|---|---|
| WP2 | Reusable inline tools need a coordinated worker/cancellation lifecycle; modal launch paths and synchronous tools remain. |
| WP3 | Queue/default/preset/inspector changes share state contracts with the busy-model hand-off; estimates and result-action redesign remain. |
| WP4 | Apply hygiene to the extracted forms; editable informational cells and inactive-field guidance remain. |
| WP5 | Preview-first layout, linked comparison and asynchronous readiness need stale-result/clipboard coverage; current background layout remains. |
| WP6 | Multi-select/history require coherent organizer state; full editing/profile redesign remains. |
| WP7 | Shared headers/nav must reflow with scalable text; minimum-width navigation clipping remains. |
| WP8 | Safe settings isolation, scalable QSS, full accessibility and native validation require their own patch; no passwords are persisted. |

Final combined app/background/training suite: **797 passed, 3 skipped** (174.57s). Windows symlink privileges caused the three skips; Office COM diagnostics occurred despite the passing run. Rendering tests: **23 passed at each of 100%, 125%, 150%, 200% offscreen scaling**. Truthful-copy tests cover 29 cases. The script creates **184 after captures**, including real conversions/fallback; running/failure layouts are labeled fixtures. Native DPI/high contrast, screen readers, larger system text and packaged builds remain unverified.

Engine hand-off: batch-wide output collision planning; metadata early-return/route coverage; original-copy fallbacks restoring metadata/dimensions; capability-list/router mismatches; model-level busy guards and stable job identities. These defects are documented, not silently fixed.

See [delivery details and package plans](UI_UX_DELIVERY.md), [old/new copy table](UI_COPY_AUDIT.md), [capture index](UI_UX_CAPTURE_INDEX.html), and the complete [WP0](ui-ux-patches/WP0.patch) / [WP1](ui-ux-patches/WP1.patch) patches. Apply patches in that order to the working-tree baseline; existing changes are excluded from the patches.
