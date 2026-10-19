# WP1 — truthful UI copy and output evidence

The UI now describes supported operations and measured outputs. Conversion, compression, PDF and background-removal engine functions and configuration values are unchanged. Metadata evidence is a read-only UI check after a successful conversion, not a sanitation guarantee.

## Changed claims

| Severity / user impact | Old string | New string | Reason / source evidence |
| --- | --- | --- | --- |
| Low — avoid an unverified quality implication | Create clean cutouts locally. | Create cutouts locally. | Keep the local-processing statement without promising cutout quality. |
| High — an existing original or output can be replaced | Your originals are never overwritten. | Output: same folder as each source. Existing destination files may be replaced. / Output: [chosen folder]. Existing destination files may be replaced. | `ImageConverterMainWindow.start_conversion` only avoids the current source path; the engine permits replacing other existing destinations. Batch-wide collision planning remains a hand-off item. |
| High — completion does not verify source preservation | Completed in … Your originals were not changed. | Completed in … Select a row to review its output metadata check. | Completion only verifies the produced file and its size. No source hash or batch collision verification exists. |
| High — absence and inability to inspect were confused | Clean (no tracking tags) | No supported metadata found / Metadata inspection unavailable / Metadata could not be inspected | The existing reader defaults `has_metadata` to false for unsupported formats and after some read failures. The UI adapter checks support, dependency flags, failures, PDF access and ODT XML validity before interpreting a negative result. |
| High — metadata presence now has evidence | Has metadata | N supported metadata fields found | Report the names/count actually returned by the existing reader; avoid classifying every field as a tracking tag. |
| High — universal removal was unverified | Strip all metadata from output | Remove supported metadata | Removal coverage varies by format and route. |
| High — tooltip overstated supported coverage | Strip all personal identifiable information, author properties, camera/device tags, GPS coordinates, and timestamps across all formats. | Request removal of supported metadata, such as author, GPS and timestamps, where the format and conversion route allow. Review the output check after processing. | Some document routes return before stripping; same-format routes take a metadata-only path. These engine behaviors are preserved. |
| High — revision/content privacy was not verified | Privacy mode removes author information, revision history, device details, and GPS tags. | Removal varies by format and conversion route. Some metadata may remain. Some same-format routes apply metadata removal without quality or resize changes. Document content and revision history are not comprehensively inspected. Output checks report supported fields found after processing. | Core-property/EXIF removal is not comprehensive revision-history or content sanitation. |
| Medium — metadata preservation is route-dependent | Preserve EXIF Metadata (Images) | Keep supported EXIF metadata | Only supported EXIF data are passed to applicable image encoders. Tooltip explicitly excludes preserving every field. |
| Medium — developer jargon suggested an unsupported capability | Metadata Cleaning & Sanitization | Metadata removal | One action verb; no sanitization guarantee. |
| High — OCR scope differed from the routes | Enable OCR Text Fallback; Use OCR fallback when converting scanned PDFs or images to text/DOCX | Recognize scanned PDF text (OCR); Use OCR fallback for PDF to TXT or DOCX when text is missing. Image to TXT always uses OCR; image to DOCX embeds the image. OCR requires a local Tesseract installation. | PDF TXT/DOCX consume `enable_ocr`; image TXT always runs OCR; image DOCX embeds a picture. |
| High — Word password capability was implied | Document OCR & Decryption; Encrypted PDF / Word… | PDF text recognition and password; Password for supported PDF routes | Word conversion routes do not receive the password field. Tooltip names the actual PDF scope. |
| Medium — image DOCX is not recognized text | Editable Microsoft Word document output. | Word document output. Image inputs are embedded as pictures, without text recognition. | Image→DOCX builds a Word file containing the image. |
| Medium — the UI list is not an authoritative capability registry | Formats valid for every file in the queue. | Output choices for this queue. Availability depends on the conversion route and installed tools. | Known list/router mismatches remain a hand-off item; choices and configuration semantics are unchanged. |
| Medium — known unsupported PPTX routes | Convert compatible queue items to PPTX. | PowerPoint output. Some advertised input routes are unavailable and may report unsupported. | PDF→PPTX and Word→PPTX are listed in the UI but explicitly rejected by the engine. |
| Low — compression varies | Modern image output with excellent compression. | WebP image output. File size varies by content and quality. | A smaller output is not assured. |
| Medium — Merge lacks drag reordering | Drag-friendly ordering | Move files up or down | Merge uses the working Up/Down buttons. |
| Medium — save destination can replace an input | Non-destructive save; Original stays untouched | Choose an output PDF | Organizer and PDF compression allow a user-selected destination and do not verify a separate unchanged original. |
| Low — developer wording | Choose a focused workflow. Your existing PDF engine and output behavior stay unchanged. | Merge, split, organize or compress PDFs on this device. | Describe user outcomes. |
| Medium — savings depend on content | Reduce PDF file size; Choose a balanced, maximum, or lossless profile and see the achieved reduction. | Try a smaller PDF; Choose a compression profile and see the measured result. Savings vary by PDF. | Compression may return an unchanged copy. |
| Low — clarify measured evidence | Clear savings report | Measured savings report | The reported sizes come from compression results. |
| Medium — image output may be larger | Reduce image file size; Create smaller image copies with WebP, JPEG, PNG optimization, optional resizing, and metadata removal. | Try smaller image copies; Choose WebP, JPEG or PNG output with quality, resize and supported metadata controls. Savings and applied settings vary by image and conversion route. | Cross-format output can grow; same-format metadata routes can skip quality/resize. |
| Medium — avoid a blanket original guarantee | Originals stay untouched | Numbered output names when a file exists | Describes `ImageCompressDialog._destination_for` behavior directly. |
| Medium — no guaranteed reduction | Create smaller image copies while keeping the originals unchanged. | Try smaller image copies. Savings and applied settings vary by image and conversion route. | Reports attempts rather than a guaranteed outcome. |
| High — fallback can restore metadata and dimensions | Strip metadata from compressed copies | Remove supported metadata, with a tooltip explaining same-format limitations and unchanged-copy fallback | Existing fallback copies the original after conversion when its same-format result is larger. |
| High — fallback was not surfaced | N compressed … (% saved) | N outputs saved … (% smaller / % larger); N unchanged copies saved because compression produced larger files. Original metadata and dimensions may remain. | The UI retains the existing fallback and reports it explicitly. Supported metadata are inspected after the fallback. |
| Medium — aggregate growth was hidden | 0.0% saved for a larger output | [actual percentage] larger | Use the measured signed byte difference. |
| Medium — unverified PDF mechanism/numbers | Reduce file size using image resampling and stream deflation. | Try a smaller PDF. Savings and visible changes depend on its content. | Plain outcome language. |
| High — parameters did not match execution | Balanced (Recommended) — 150 DPI, 75% quality, stream deflation | Balanced (recommended): reduce image size and quality | Secondary tooltip states the actual 1200-pixel maximum dimension / JPEG quality 65 and warns visible changes are possible. |
| High — minimum size was not guaranteed | Maximum Compression — 100 DPI, 55% quality, smallest file size | Stronger compression: more visible changes possible | Secondary tooltip states actual 800-pixel maximum dimension / JPEG quality 40, transparency removal, and no smaller-result guarantee. |
| Medium — technical term overstated scope | Lossless — Deflate streams and remove xrefs without altering images | Keep image quality: try document compression | Secondary tooltip describes document compression/font subsetting without re-encoding page images. No guarantee about other document properties. |
| High — an unsuccessful attempt does not prove optimality | No reduction was achieved (original was already optimal at …). Original file preserved. | No reduction was achieved with this profile (…). An unchanged copy was saved. | `compress_pdf` returned its original-copy fallback; no optimum was calculated. |
| Medium — conversion runs concurrently | Cancel stops after the current file finishes.; Cancelling after the current file… | Cancellation skips work that has not started. Running files finish first.; Cancelling after running files finish… | Batch conversion uses concurrent workers. |
| Medium — tools are not globally guarded | One processing job runs at a time to reduce resource use. | Conversion waits until background removal finishes. | Only the Convert/background-removal pair has this guard. |
| Low — accessible upload wording contradicted local use | Upload files | Add local files | The control adds local paths; it does not upload. |
| Low — unsupported is not the only no-add condition | Those files are already in the queue or are unsupported. | No new files were added. Check the selected paths and queue for duplicates. | Missing paths can also result in no additions. |

## New measured-result states

- Successful outputs receive `Output check: No supported metadata found`, a supported-field count, `Metadata inspection unavailable`, or `Metadata could not be inspected`.
- The queue retains the actual output path, evidence and field names; selecting its source row exposes a selectable result label. A footer summarizes the checks without calling unknown results clean.
- Conversion routes returning only the first image output explicitly say only that first file was checked. The UI does not claim to inspect additional outputs that the engine does not enumerate.
- The Image Compress completion summary reports post-fallback metadata checks for the first five outputs and explicitly counts additional checks not shown. It does not claim unshown outputs were cleaned.
- Metadata evidence covers the existing reader's supported fields only. It is not verification of comprehensive sanitization, document-content privacy, source preservation or all embedded metadata. ODT preflight deliberately matches the reader's UTF-8 decoding; unreadable encodings are reported as failed. Adapter warning contexts are serialized so concurrent inspector/worker checks do not consume each other's warning states.

## Retained claims and evidence

- **On-device / no uploads:** desktop processing paths use local engine/model calls. A tooltip explains that these tools process files on this device. No network or telemetry calls were added.
- **Background-removal originals stay untouched:** its existing `plan_tasks` reserves input/existing/planned paths and publishes new output paths. This stronger planner is not shared by Convert.
- **Background-removal lossless WebP:** `backgroundG/src/bgremove/export.py` passes `lossless=True` for WebP export.
- **25 MiB / 120 megapixel background-removal input limits:** those are existing constants/validation limits, not inferred performance promises.
- **PNG lossless format / WebP lossless option:** these describe encoding choices, not preservation of the input's dimensions or metadata.
- Profile names and model descriptions describe intentions; model availability/readiness redesign remains WP5.

## Vocabulary and styling

Use **Remove** for supported metadata and selected queue items; use **Clear queue** for clearing the batch; use **Copy path**, **Open folder**, **Choose**, **Save**, **Run** and **Cancel** for their existing actions. Engine identifiers and filename suffixes such as `strip_metadata` and `_clean` are unchanged.

The only new QSS is a token-based cyan focus border around the keyboard-selectable output-evidence and image-compression-result labels. Their transparent borders reserve space before focus, preserving layout. Existing dialog surfaces, typography and contrast tokens remain in force.

## Verification scope

`image_converter/tests/test_truthful_copy.py` covers supported/unsupported/failed inspections; missing optional readers; encrypted PDF access; malformed ODT metadata and corrupt EXIF warnings; informational GPS warnings; source versus output evidence; unchanged existing worker signal APIs; first-output-only evidence; source-preservation copy; OCR/password scope; original-copy fallback; larger cross-format output; and correct secondary PDF parameters. Existing dialog expectations intentionally change from “Original file preserved” to the measured fallback wording.

Engine fixes required outside this UI package: batch-wide output collisions; metadata early returns and cross-format coverage; original-copy fallbacks restoring metadata/dimensions; capability-list/router mismatches; model-level busy guards. WP2–WP8 architecture/state changes are staged separately.
