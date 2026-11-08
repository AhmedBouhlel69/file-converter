# Audit — November 2026

Scope: the whole repository, with the most time on background removal (`backgroundG` engine, the
Remove Background page, and its CLI). Method: read the code paths end to end, ran both test suites,
ran pyflakes/mypy over the app, rendered real images through the Fast and Balanced models, and
measured the changes below rather than only reading them.

## What was run, and what was not

- Linux sandbox, Python 3.12, your pinned versions (PyMuPDF 1.28.2, PySide6 6.11.2) for the final runs.
- Engine suite: 296 tests before, **313 after**, all passing.
- App suite: 31 tests fail both before and after, all for the same reason — they need real
  Microsoft Word/Excel/PowerPoint through COM. There are no other failures and no new ones.
- Real-model runs used the **Fast** and **Balanced** files (hashes verified). **Quality** and
  **Portrait** were not run: BiRefNet runs out of memory in the sandbox just as it does on your 16 GB machine.
- The GUI was exercised with Qt's offscreen platform. The real Windows clipboard (Snipping Tool,
  browsers, Explorer "copy") was **not** tested here. See "Please check on Windows" below.

## Fixed

| # | Finding | Evidence | Fix |
|---|---|---|---|
| 1 | Cutouts kept the removed background in the RGB channels of transparent pixels. Dropping the alpha channel (some editors, converters, upload forms) reveals it. | On the horse sample 344,457 of 344,457 transparent pixels still held picture colours. | `decontaminate` / **Clean edges** blanks them; 7,844 remain (a 2-pixel ring of estimated *subject* colour that stops black fringes in naive scalers). |
| 2 | Halo of the old background on soft edges. | Synthetic matte with known truth: mean edge colour error 84 → 17 (of 255). | Blur-fusion foreground estimation, striped so memory stays low (24 MP ≈ 5.5 s). |
| 3 | **TXT → HTML conversion always failed** (`NameError: html`). | Reproduced, then fixed. | `import html`; regression test. |
| 4 | Image → DOCX with unreadable DPI metadata raised `NameError: img_p` while trying to log a warning. | Pyflakes F821; regression test forces the path. | Use `in_p`. |
| 5 | Outputs could not be written to FAT/exFAT drives, some network shares and cloud-sync folders: publication used hard links only. | Simulated with a failing `os.link`. | Falls back to exclusive-create + copy; never overwrites; rollback still removes only its own files. |
| 6 | Every `Remover(...)` re-hashed the whole model file (up to ~1 GB for BiRefNet). | Read the code; test counts hash reads. | Verification cached per process for an unchanged file (size + mtime). |
| 7 | `Tuple` used but not imported in `core/pdf/tools.py`. | Pyflakes F821 (harmless at run time because of `from __future__ import annotations`). | Imported. |

## Added

- **Paste an image**: Ctrl+V or *Paste image* on the Remove Background page; also drag a picture in
  from a browser. Accepts a bitmap (screenshots, "copy image"), copied image files, or a pasted file path.
  Bitmaps are saved as PNG (alpha kept) in a private scratch folder, deleted when you remove them, clear
  the queue or quit, and purged after two days if a crash left any behind. Cutouts of pasted images go
  to *Pictures\Background Removed* unless you pick a folder. On the Convert pages Ctrl+V queues copied
  files, or saves a pasted picture to *Pictures\Pasted Images*.
- **Auto model**: Balanced if installed, else Fast; never the 8 GiB-RAM profiles. Falls back if the best file fails to load.
- **Clean edges** (default on), **High accuracy** (mirror-image averaging, ~2× time), **Copy result when done**, colour picker, `--bg-model auto`, `--bg-accurate`, `--bg-no-clean-edges`.
- Engine API: `RefineOptions(decontaminate, levels_low, levels_high)`, `estimate_foreground`, `Remover.remove(tta=True)`.
- Hardening found while writing paste: Qt returns `None` for an empty or locked clipboard; handled.

## Tried and rejected

- **BiRefNet-lite** (224 MB, MIT) as a better mid-size model: killed for lack of memory at 8 GB. Not added.
- **Colour-match cleanup** to remove background seen through spokes/handles: on the bike it cut real
  parts of the gear cassette and missed the target patch. Removed rather than shipped.
- **Two-pass** on the bike left *more* beige in the rear wheel than single-pass (one image; not a general claim).

## Known limits of the engine

Segmentation, not matting: background visible through thin gaps (bike spokes) can survive, and hair or
fur edges are only as good as the model's soft mask. High accuracy helped the bike visibly but not fully.
Clean edges cannot recover colours that genuinely are the background seen through a semi-transparent mane.

## Open — recommended, not changed

1. **Unpinned dependencies.** `PyMuPDF>=1.24` resolves to 2.1 on a fresh install; with it (and the latest PySide6 6.12) 8 table-extraction and 2 spin-box tests failed. Add upper bounds or a lock file.
2. **`import fitz`** is deprecated (FutureWarning); 9 files. Switch to `import pymupdf`.
3. The 31 Office-dependent tests fail instead of skipping on machines without Office; mark them so CI stays green.
4. 105 unused imports (81 auto-fixable with `ruff --fix`).
5. `os.startfile` (9 call sites) is Windows-only; `QDesktopServices.openUrl` is portable.
6. The model session is released after every batch, so each paste-and-remove reloads it (Balanced ≈ 1 s). An idle keep-alive (e.g. 60 s) would help repeated single pastes; it trades against your stated memory policy, so it is your call.
7. Quality/Portrait are unusable at 16 GB. Options to evaluate on your machine: fp16 or quantised exports, a smaller input size, or ORT memory tuning.
8. `scratch/` holds ~540 MB of build output (an executable and its work folder). It is git-ignored but inflates backups.

## Please check on Windows

Copy a screenshot with **Win+Shift+S**, open Remove Background and press **Ctrl+V**; do the same with
"Copy image" from a browser and with files copied in Explorer. Then remove the background and paste the
cutout into another app. `scratch/clipboard-smoke.py` shows how you smoke-tested copy-out before.


---

# Pass 2, step 1: conversion accuracy

Method: 160 real conversions over a corpus of awkward but common inputs (semicolon CSV
in Windows-1252, UTF-16 text, 16-bit PNG, CMYK JPEG, animated GIF, multi-page TIFF,
HEIC, Word with lists/merged cells/picture, scanned PDF). Every fix below has a test in
`image_converter/tests/test_conversion_fidelity.py` (32 tests).

| Defect | Fix |
|---|---|
| Semicolon CSVs were split on the decimal comma, destroying data | Delimiter detection (`, ; tab |`), decimal commas, encoding detection |
| `0612345678` became `612345678.0`; whole numbers printed as `1.0` | Columns become numbers only when nothing is lost; integers stay integers |
| CSV text such as `=HYPERLINK(...)` became a live formula in XLSX | Written as text |
| Non-UTF-8 text lost accents (`Résumé` → `Rsum`) or became garbage (UTF-16); TXT→DOCX crashed | Shared detector in `core/text_io.py` |
| Arabic/Chinese were black boxes in TXT→PDF and CSV→PDF; indentation and blank lines dropped | PDFs laid out with PyMuPDF Story (shaping, right-to-left, built-in fallback fonts) |
| CSV→PDF silently stopped at 1,000 rows | Up to 20,000 rows, with a note if more |
| TXT→RTF wrote raw UTF-8 that Word shows as `RÃ©sumÃ©` | `\uN?` escapes |
| TXT→PPTX dropped every line after the 9th of a section | Continues on extra slides |
| Excel→CSV/JSON: `1.0`, `2024-01-05 00:00:00`; only the first sheet | Real cell types; other sheets saved as `name - Sheet.csv` |
| Excel→PDF failed without Excel | Falls back to a table PDF and says so |
| 16-bit PNG/TIFF converted to an all-white image | Proper 16→8-bit scaling (PNG/TIFF keep 16-bit) |
| PNG→GIF turned transparency black; CMYK/16-bit→GIF crashed | Dithered palette with a transparent index |
| Animated GIF/WebP kept one frame; multi-page TIFF→PDF kept one page | All frames/pages kept; a note when the target holds one image |
| Colour profiles dropped (camera/iPhone colours shift); CMYK converted naively | Profiles kept where the format allows, else converted to sRGB; CMYK via its profile |
| Word→TXT/HTML moved tables to the end, duplicated merged cells, lost lists/bold/links/pictures | Reading-order walker `core/documents/docx_render.py` |
| PDF→TXT split bullets from their text; scanned PDF→TXT reported "corrupt output" | Markers rejoined; scanned PDFs OCR'd automatically, or a clear message |
| HEIC→TXT failed; empty OCR said "corrupt output"; Tesseract in Program Files not found | Image normalised for OCR; "No text was found"; installer path and `TESSERACT_CMD` checked |
| Unpinned dependencies | Upper bounds in `requirements.txt` |

Suite: 495 passed; the remaining 29 failures are the same Office-COM tests as before
(2 earlier failures, Excel→PDF, now pass through the fallback).


# Pass 2, step 2: UI and usability

Tests: `image_converter/tests/test_usability.py` (12 tests).

| Problem | Change |
|---|---|
| Converting replaced existing files silently ("Existing destination files may be replaced") | Never overwrites: `name (2).ext`; also unique within a batch, for multi-page image exports and extra Excel sheets |
| A mixed queue (photo + Word + CSV + PDF) defaulted every row to TXT | "Best for each file": photo→PNG/JPG, Word→PDF, CSV→XLSX, PDF→DOCX; a single-kind queue starts on its natural target unless you chose one |
| Word→PowerPoint and PowerPoint→Word were offered but always failed | Removed |
| PDF→PowerPoint was offered but always failed | Implemented: one slide per page, page text in speaker notes |
| Image compressor froze the window on big batches | Runs in the background with a progress bar, a per-file Result column and Stop |
| Compressor result text squeezed the file list to one row | Short summary; details in the tooltip and the summary dialog |
| Rotated phone photos showed sideways thumbnails and swapped dimensions | EXIF-aware thumbnails, preview and size |
| Files dropped on PDF Tools / Image Tools went to the Convert queue | Open the selected tool with those files |
| `os.startfile` in tool dialogs (Windows-only) | `QDesktopServices.openUrl` |

Suite: 507 passed; the 29 remaining failures are the Office-COM tests that need Word/Excel/PowerPoint.


# Pass 2, step 3: tool results and fallbacks

Tests: `image_converter/tests/test_tools_and_fallbacks.py` (11 tests; 3 run only where LibreOffice is installed).

| Change | Measured / detail |
|---|---|
| **Bug:** Image compressor with "Keep original format" + "Remove metadata" (the default) only stripped metadata: quality and resize were ignored | Now re-encodes. A 418 KB JPEG went from 412 KB (−1%) to 45 KB (−89%) with the dialog's settings; JPEG comments, XMP and IPTC are also removed when stripping |
| PNG output: images with ≤256 colours are stored as a lossless palette | Logo 1.9 KB → 0.9 KB, pixel-identical |
| Compressor option "Smaller PNGs" (on by default): dithered 256-colour palette | App screenshot 125 KB → 44 KB (−65%), mean error 0.05/255 |
| LibreOffice fallback when Microsoft Office is missing: Word/ODT/RTF ↔ PDF/DOCX/ODT/RTF, PowerPoint→PDF, Excel→PDF (layout kept) | Found on PATH, in Program Files, or via `LIBREOFFICE_PATH`; runs with a private profile so an open LibreOffice does not block it; 180 s timeout. Error messages now mention LibreOffice when neither suite is installed |
| PDF Tools → **Protect**: add an AES-256 password (optional print/copy limits) or save an unlocked copy | The original file is never modified |
| PDF Tools → **Page numbers**: 6 positions, 4 formats, start number, skip cover | Numbers read upright on rotated pages |

Suite: 518 passed; the 29 remaining failures are the Office-COM tests that need Word/Excel/PowerPoint.
Tests disable LibreOffice unless marked `libreoffice`, so results don't depend on whether it is installed.
