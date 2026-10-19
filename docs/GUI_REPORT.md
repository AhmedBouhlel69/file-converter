# Universal File Converter — full GUI report

Reviewed on **19 October 2026, Africa/Tunis**. This is a dedicated review of the current desktop interface: every page, its visible controls, the five tool dialogs, state changes, keyboard interaction and practical usability. It complements the [technical report](TECHNICAL_REPORT.md).

After this GUI review, model diagnostics continued in the
[model readiness and verification guide](BACKGROUND_MODELS.md). That continuation
adds source diagnostic commands without changing the GUI controls reviewed here.

The later [resource optimization](RUNTIME_OPTIMIZATION.md) updates this snapshot:
the background hint now explains two CPU threads and model release after a batch;
Convert and Remove Background jobs cannot overlap; normal conversion defaults to
two workers. The rest of the page/control review below describes the original
reviewed state. See the [training workflow](TRAINING_AND_OPTIMIZATION.md) for
separate model development, outside the desktop runtime.

The report uses the current UI source, the existing automated UI checks, and captured application states. Screenshots are from Qt's offscreen rendering. The completed background-removal screenshots show an actual Fast-model job and successful image-copy action; several other captures demonstrate layout with sample data. Those distinctions matter: a well-rendered screen does not prove that every conversion behind it succeeds.

## Overall assessment

The GUI has a coherent dark visual system and a clear division into four workspaces. **Remove Background is the strongest complete workflow**: images, before/after views, settings, processing feedback, saved output and copying are all on one page. **Convert is the most capable workspace**, but its changing right-hand panel, mixed-file settings and output promises need more precise behavior. **Image Tools and PDF Tools are clear launch pages**, although they put another navigation step between the user and the working controls.

The main improvements should address behavior before decoration. General conversion still has output-collision defects despite the footer saying originals are protected. Busy-state restrictions can be bypassed through some queue actions. PDF and image utility dialogs run substantial work on the GUI thread, so their apparently simple workflows can stop responding. Several offered formats and document options exceed what the engine currently implements. These are concrete findings; preferences about card size, spacing and direct access are design judgments and are identified separately below.

| Area | Current assessment | Most useful next improvement |
| --- | --- | --- |
| Navigation | Four clearly named pages; exclusive selected state | Make shortcuts act on the visible workspace and show running jobs across pages. |
| Visual hierarchy | Consistent cards, headings, color and primary actions | Reduce large empty areas on tool launch pages and keep working controls closer to their introduction. |
| Convert | Efficient mixed batch table with row overrides and inspector | Protect the queue while busy, unify the actual conversion capability list, and make output planning visible. |
| Image Tools | Simple batch compressor with useful defaults | Move compression into a worker and honor every selected transformation consistently. |
| PDF Tools | Four focused workflows with understandable controls | Add responsive processing, usable progress and cancellation to the dialogs. |
| Remove Background | Integrated comparison, model settings, save and copy | Show model readiness/free-memory information and explain advanced edge controls. |
| Accessibility | Strong audited text contrast, visible focus, some explicit names | Complete labels and focus order; test a screen reader, keyboard-only use and Windows scaling. |
| Continuity | Queues and settings survive page switches within the window | Save preferences/window geometry and provide a recoverable job history. |

## 1. Window, visual system and shared controls

### Window and layout

The title bar says **Universal File Converter**. The window starts at **1380 × 860** and has a **1120 × 700 minimum**. It contains a horizontal header and one active workspace below it. There is no visible sidebar, menu bar, preferences screen or application-wide history page in this implementation. The legacy navigation-rail and statistics widgets are not displayed.

The interface is built with native **PySide6 / Qt Widgets**, rather than HTML. Its layout uses splitters, stretchable areas and scrollable panels. It does not switch to a compact, single-column layout on small screens. The minimum window size is therefore a real constraint, especially on a small display with Windows scaling enabled. The supplied minimum-size background-removal capture shows both previews, Copy image and the footer; advanced controls remain available by scrolling. That capture does not establish usability at every DPI or text-size setting.

### Color, typography and visual meaning

| Element | Current implementation | GUI implication |
| --- | --- | --- |
| App background | Very dark navy, `#07111F` | Distinguishes the window from its raised cards. |
| Cards / input surfaces | `#0D1B2E` and `#13243A` | Creates a consistent hierarchy for queue, settings, preview and tool cards. |
| Main text / supporting text | `#F4F8FF` / `#B8C7D9` | Supporting copy remains readable without competing with titles. |
| Primary action | Violet, `#6654E8` | Used for conversion, tool execution and background removal. |
| Focus | Cyan, `#67DFFF` | Visible focus treatment exists for buttons, fields, tables, lists and tabs. |
| Success / warning / error | Mint / amber / pink | Text such as Done, Warning and Failed also conveys meaning, so the main statuses are not color alone. |
| Type | Segoe UI with Arial fallback; page title 24 px, section 16 px, body 13 px, secondary 12 px, eyebrow 11 px | A consistent desktop scale, but several supporting labels are relatively small. There is no in-app text-size control. |
| Shape and spacing | Shared 6/10/14 px radii and 4–32 px spacing tokens | Most new views feel related. Some older modal labels and punctuation remain less consistent. |

The local token contrast audit passed during this review: primary text ranges from **14.70:1 to 17.78:1**, secondary text from **9.10:1 to 11.01:1**, white on the primary action is **5.25:1**, and the tested border on the app background is **3.03:1**. This checks specific token pairs, not every disabled, selected, hover, error or custom-painted state. It is not a complete accessibility certification.

### Header, element by element

| Visible element | Purpose and behavior |
| --- | --- |
| App icon | 40 px brand image when the asset exists; has an accessible name. It is not a navigation button. |
| `LOCAL FILE WORKSPACE` | Small uppercase brand eyebrow. |
| `Universal File Converter` | Main application name. |
| `Convert` | Opens the batch conversion workspace; selected at startup. |
| `Image Tools` | Opens the image-compressor launch page. |
| `PDF Tools` | Opens the PDF tool selector and launch cards. |
| `Remove Background` | Opens the dedicated cutout workspace. |
| Selected navigation treatment | The four buttons are checkable and mutually exclusive. Their checked appearance identifies the current page. Switching pages retains in-memory queue/settings state. |
| `Add files` | Visible only on Convert. Opens a multiselect file picker. Its tooltip advertises Ctrl+O. It is the emphasized header action when the queue is empty. |
| `Add folder` | Visible only on Convert. Opens a folder picker and scans recursively. Its tooltip advertises Ctrl+Shift+O. |
| `● ON-DEVICE · NO UPLOADS` | Persistent informational badge, not a button. The local-processing claim is consistent with these workflows. This does not mean models are already installed on every deployment. |

The mode buttons remain available during conversion or removal. This lets the
user look elsewhere while a job runs, but there is no shared job indicator in
the header. The later resource update prevents Convert and Remove Background
batches from overlapping. Convert's action is disabled during background removal,
and its footer explains the active job; background removal reports when it must
wait for a conversion. Navigation retains in-memory queues.

### Drag and drop

Dragging file URLs over the window while the relevant workspace is idle shows a full-window overlay: **Drop to add files**, followed by **Folders are scanned recursively. Unsupported files are ignored.** On Remove Background, the drop goes into its image queue and the app stays on that page. On the other pages, a successful drop adds to the general queue and switches to Convert. This means dropping files while on Image Tools or PDF Tools does not directly populate the active tool dialog.

The ordinary file/folder discovery path filters supported extensions. The generic queue itself accepts existing paths, and the file picker's **All Files** option can admit an unsupported file before the engine rejects it. Input acceptance and the overlay's wording should be unified. Recursive folder enumeration happens synchronously and can interrupt interaction for a large tree.

### Keyboard and focus

| Key | Current behavior and scope |
| --- | --- |
| Ctrl+O | On Remove Background, opens its image picker. On the other pages, opens the general conversion picker and adds to Convert. |
| Ctrl+Shift+O | On Remove Background, picks a folder for images. Otherwise picks a folder for the general queue. |
| Ctrl+Return | Starts background removal when its page is active. Otherwise starts the ordinary conversion queue, including when Image Tools or PDF Tools is visible. |
| Escape | Requests cancellation for the active background page or, on the other pages, the ordinary conversion worker. Tool dialogs also have their own Cancel actions. |
| Delete | Scoped to the general queue or background image list and removes selected entries. It is not a window-wide file-deletion shortcut; Delete in an output-path field edits that field. |
| Enter / Space on a failed Convert row | Requests retry for that row. The Failed status cell is also clickable. |
| Ctrl+C in the background image list or Result preview | Copies the selected successful cutout. It is enabled only when a usable result is available. |
| Ctrl+C in a text field | Retains normal text-copy behavior. |
| Tab / Shift+Tab | Standard Qt traversal. Main navigation → add actions → queue actions → queue → settings → primary footer action has an explicit order. Detailed traversal inside every page/dialog still needs a keyboard-only audit. |

The hidden-queue Ctrl+Return/Escape behavior is source-confirmed and potentially surprising. A command should normally operate on the visible workspace, or explicitly navigate to the job it starts or cancels.

## 2. Convert page

The page has a large **Conversion queue** on the left and a narrower **Conversion setup / File inspector** area on the right. A bottom action dock spans the page. The horizontal splitter can resize the two areas, but neither is collapsible. The right panel is constrained to **340–420 px**, and its contents scroll vertically without a horizontal scrollbar.

![Convert with mixed queue and batch settings](../scratch/ui-report/02-convert-batch-settings.png)

### A. Empty queue

| Element | Behavior |
| --- | --- |
| `Conversion queue` | Persistent section heading. |
| `0 FILES` | Count badge; becomes singular `1 FILE` or the corresponding plural. |
| `Remove` | Disabled without a selection. Tooltip explains Delete. |
| `Clear queue` | Disabled without entries. Uses the danger treatment. |
| `DROP ZONE` / upload icon | Visually anchors the empty-state action area. |
| `Drop files or folders anywhere in this area` | Main instruction. The window handles the real drop route in this composition. |
| Supporting formats line | Images, PDFs, documents, spreadsheets, presentations and text. |
| `Choose files` / `Choose folder` | Picker alternatives for users who do not drag files. |
| `Convert 0 files` | Disabled primary footer button; there is no work to start. |

The empty state explains how to begin without requiring the user to understand formats first. The header picker buttons duplicate the empty-state pickers, which is reasonable here because both are clear entry points.

### B. Populated queue, element by element

| Element | Display and interaction |
| --- | --- |
| Count badge | Counts queue entries, rather than selected entries or completed jobs. |
| `Drop more files anywhere in the window` | Compact reminder replaces the large empty-state invitation. |
| `+ Add more` | Reopens the general file picker. |
| `Remove` | Removes selected queue entries, leaving source files on disk. The toolbar disables it while conversion is running. |
| `Clear queue` | Removes the entire queue and resets the inspector/footer presentation. Does not delete input or generated files. |
| Removal toast / `Undo` | Describes the last Remove or Clear operation and restores those entries and their targets. It is a single remembered removal operation, not a general undo/redo history. |
| Row selection | Whole-row selection, including Ctrl/Shift multiselect. The current row controls the inspector. |
| Duplicate intake | Resolved paths are compared case-insensitively; the same path is not added twice. |
| Scrolling and row size | 58 px rows, alternating backgrounds, no grid or row-number header. Vertical scrolling is available; the horizontal scrollbar is disabled. |

The queue's five columns are:

| Column | Meaning and states |
| --- | --- |
| `Status` | Queued, Converting, Done, Warning, Failed or Cancelled. Each has a textual label and a colored marker. Converting adds a small row progress bar. Failed is drawn as **Failed · Retry**. Hovering a row exposes its path and error/warning details. |
| `Preview` | Asynchronously loaded image/PDF thumbnail; a generic FILE tile when a visual thumbnail is unavailable. |
| `File` | Filename plus supporting information such as dimensions, pages or rows. Long filenames are elided in the middle; secondary details are elided at the end. Full paths remain in tooltips. Metadata details appear after asynchronous analysis; pending rows still show type/size. |
| `Convert to` | Editable per-file target selector. A purple border/background marks an override relative to the current batch default. These are actual row-specific formats, not decorative format badges. |
| `Est. size` | Approximate pre-conversion size with `~`, or actual output size after success. A dash means unavailable. The header stays Est. size after actual results replace estimates. |

Estimates use format ratios and the quality slider, rather than encoding or inspecting the eventual rendered pages. They do not account comprehensively for resizing, page count, OCR or all encoder settings. A sample PDF→JPG estimate in the layout capture is very small; it must not be interpreted as a measured prediction. **Estimated output** needs either a stronger estimator or wording that makes its rough nature harder to miss.

### C. Row context menu

Right-clicking a row selects it when it was not already selected. The menu combines single-file actions with selection-dependent tools:

| Menu item | When present / what it does |
| --- | --- |
| `Open file location` | Opens the clicked input's parent folder. |
| `Copy full path` | Copies the clicked input path as text. It does not copy pixels or the result file. |
| `Inspect file` | Shows the clicked input in the right inspector. |
| `Retry conversion` | Present when the clicked row is Failed. |
| `Split PDF…`, `Organize pages…`, `Compress PDF…` | Present for a single selected PDF; opens the corresponding dialog with that PDF. |
| `Compress N image(s)…` | Present when supported general image inputs are selected; sends just those images to the compressor. |
| `Remove background from N image(s)…` | Present for selected images supported by the narrower background-removal input set; switches to that page and adds them. |
| `Merge N selected file(s)…` | Opens Merge with the selection. The menu can offer it with one entry; the dialog later requires at least two. Unsupported types can reach the merge dialog and are rejected during processing. |
| `Remove from queue` | Direct queue removal. This route currently bypasses the main window's conversion-busy guard. |

Context-menu removal does not use the main toolbar's remembered undo operation. That is an inconsistency: two visually similar removal actions have different recovery behavior.

### D. Conversion setup: shared behavior

The title is **Conversion setup**, followed by **These defaults apply to the batch. Each queue row can override the format.** There are four tabs, but their visibility changes with the queue:

- **Format** and **Metadata** remain available.
- **Resize** appears only when the queue contains image inputs.
- **Documents** appears when the queue contains document/data inputs.

Selecting a file replaces this entire settings view with the inspector. **← Back to batch settings** clears selection and returns to setup. This is compact, but changing a batch option after inspecting a file takes an extra explicit step. The source does not expose a simultaneous inspector and settings view.

#### Format tab

| Control | Default, values and effect |
| --- | --- |
| `Intent preset` | Three mutually exclusive buttons. None is explicitly selected at construction. Presets change target preference and quality; they do not configure every tab. |
| `Email-friendly` | Chooses the first available target among JPG, WEBP, PDF and sets quality to **65**. |
| `Web-optimized` | Prefers WEBP, then JPG, then HTML; sets quality to **80**. |
| `Archive quality` | Prefers PNG, then TIFF, then PDF; sets quality to **100**. |
| `Format` selector | Initially prefers **JPG**, then adapts to formats common to the current queue. Non-selectable category headings group Images, Documents, Spreadsheets, Presentations, Text & data and Utilities. |
| Mixed queue format | When there is no common target, the selector displays the raw identifier **PER_FILE** under Mixed queue. Supporting text explains that every row retains its compatible target. The identifier should be replaced by a normal label such as Per file. |
| Format summary | Short explanation of the selected target, including lossless transparency for PNG and no transparency for JPG. Unknown descriptions fall back to Convert compatible queue items to FORMAT. |
| `Quality` slider | **1–100**, default **90**, with a live percentage badge. Visible for JPG/JPEG, WEBP and HEIC/HEIF targets. |
| `Estimated output` | Approximate total tied to the queue's estimate calculation. Shown beside quality when that group is visible. |
| `Lossless (WEBP)` | Initially unchecked; shown only for WEBP. |
| `Destination` → `Same folder as original` | Default. Each input uses its own parent folder. A batch can therefore create output in several locations. |
| `Custom folder:` | Enables the folder text field and Browse. An empty field still resolves to the original-folder behavior. |
| `Select output folder...` / `Browse` | Editable path plus folder picker. Both are disabled until Custom folder is selected. |

Preset buttons are not a complete representation of current settings: manual changes do not automatically change the checked preset into a custom state. A selected preset can therefore remain highlighted after its effective settings have been edited.

#### Resize tab

| Control | Default, range and conditions |
| --- | --- |
| `Resize / Scale (Images)` | Group visible for image targets. Its whole tab is still gated by image inputs. |
| Resize mode | **Original Size (100%)** initially; alternatives: **Percentage Scale**, **Custom Dimensions (W × H)** and **Fit within Max Bounds**. |
| `Scale Percentage:` | Visible only in Percentage Scale; **5–500%**, stored initial value **50%**. |
| `Width:` / `Height:` | Visible for Custom Dimensions and Fit within Max Bounds; **1–10,000 px** each, initially **1920 × 1080**. |
| `Keep Aspect Ratio` | Checked initially; appears with custom/max-bound dimensions. Fit-box downscales within bounds. |
| `Render DPI:` | **50–600 DPI**, default **150**. Its row is visible for image/PDF targets. PDF-only inputs hide the Resize tab containing it, making this relevant document-render setting inaccessible in that case. |
| `Alpha Background:` / `Choose color` | White initially. Visible for JPG/JPEG/BMP targets. Opens a color picker; a selected color changes the button to **Background #RRGGBB**. Applies when flattening transparency. |

#### Documents tab

| Control | Default and behavior |
| --- | --- |
| `Sheet Name:` | Blank, with **First / Active sheet** placeholder. Visible for CSV, XLSX, PDF, JSON and HTML targets. It is a text field rather than a detected-sheet dropdown. |
| `Document OCR & Decryption` | Group title. |
| `Enable OCR Text Fallback` | Unchecked initially. Tooltip mentions scanned PDF/image conversion to text/DOCX. The PDF→DOCX implementation does not provide the advertised OCR fallback through this flag. |
| `Password:` | Blank masked field, placeholder **Encrypted PDF / Word...**. No reveal control or password-state indicator. Supported PDF routes can use it; the app does not implement general encrypted-Word decryption. |

OCR language is not exposed. The core default is English. The screen also has no dependency readiness check for Tesseract or Microsoft Office before the user starts a route requiring them.

#### Metadata tab

| Control | Default and interaction |
| --- | --- |
| `Metadata Cleaning & Sanitization` | Group title. |
| `Strip all metadata from output` | Unchecked initially. Its tooltip makes broad claims about author data, device/GPS tags and timestamps across all formats. Actual cleaning is selective and format-dependent. |
| `Preserve EXIF Metadata (Images)` | Checked initially. Checking Strip disables and unchecks this; unchecking Strip re-enables **and rechecks** it, rather than restoring an earlier manual preference. |
| `Auto-orient Photos (EXIF)` | Checked initially. Independent orientation preference. |
| Privacy help | **Privacy mode removes author information, revision history, device details, and GPS tags.** This needs wording tied to supported metadata fields and formats. |

The GUI's privacy wording is stronger than the evidence. It should describe supported properties being removed, avoid promising complete sanitization, and report what was actually changed.

### E. File inspector

![Convert file inspector](../scratch/ui-report/03-convert-file-inspector.png)

| Element | What it presents |
| --- | --- |
| `← Back to batch settings` | Returns to settings and clears selection. |
| `File inspector` | Heading plus instruction to select a queue item to preview and review metadata. |
| Preview area | At least 200 px high. Images are thumbnailed; PDF shows only the first page. There are no page-navigation, zoom or pan controls here. |
| Document/data summary | Word: paragraphs/tables/word count; CSV: rows/columns/first headers; Excel: sheet names and row/column counts; PowerPoint: title/slide count; ODT/RTF/TXT: text statistics. These are summaries, not rendered document-page previews. |
| `Name` | Wrapped input filename. |
| `Details` | Image dimensions or document/data counts. |
| `Type` | Detected/declared format and image mode/alpha where available. Legacy DOC/XLS paths share labels naming DOCX/XLSX. |
| `Size` | Input file size, not generated output. |
| `Metadata` | Has metadata plus the first warning, or **Clean (no tracking tags)**. That clean label means the current detector found no supported metadata; it does not establish absence of every identifying field or sensitive document content. |
| `Open folder` | Opens the input's directory. Enabled when a valid file is selected. |
| `Copy path` | Copies the input path as plain text. No image copying on this inspector. |
| Failure view | **Preview unavailable:** with a shortened exception, and basic extension information. |

Queue thumbnails are analyzed in a pool, but detailed inspector parsing/rendering happens synchronously when a row is selected. Large files can pause the GUI even before conversion begins.

### F. Bottom dock and conversion states

| State | Text and controls |
| --- | --- |
| Empty / ready | `0 files · 0 B → —` and **Your originals are never overwritten.** Convert is disabled until entries exist. |
| Ready with files | Input count/size → rough output estimate. Primary action becomes **Convert N files**. |
| Running | Progress bar, **Converting X of N files · P%**, and **Cancel stops after the current file finishes.** The primary button becomes **Cancel conversion** with danger styling. Header add actions, toolbar queue actions and settings disable. |
| Cancellation requested | Button becomes **Cancelling…**, disabled. Text says cancellation occurs after the current file. Current native/Office work cannot be forcibly interrupted. |
| Completed | Shows converted totals and actual reported byte totals, elapsed time, **Open folder**, and **Convert more**. The queue remains. The main Convert button can run it again. |
| Partially failed | Shows converted/failed counts and **Select a failed status to retry.** Per-file details are primarily in tooltips. |
| Cancelled | Marks unfinished rows Cancelled; reports that completed outputs were kept. |

**Open folder** opens one remembered output directory, which may not cover a batch using each input's own folder. **Convert more** opens the picker; it does not clear completed entries. Close during an active normal/background job requests cancellation and keeps the window open, explaining that it must be closed again when the worker finishes.

Two claims need correction before release. The existing output planner avoids writing directly to a task's own input, but does not protect every other queued input or existing destination. The technical review reproduced a source-file collision. The **originals are never overwritten** and **originals were not changed** messages therefore overstate actual protection. Also, toolbar disabling does not prevent target-cell edits, direct context-menu removal or all shortcut intake while busy; row-index result mapping can become unreliable when the queue changes.

## 3. Image Tools page and Compress Images dialog

### Image Tools launch page

![Image Tools launch page](../scratch/ui-report/04-image-tools.png)

| Element | Exact copy / function |
| --- | --- |
| Eyebrow / title | **IMAGE WORKSPACE** / **Image tools**. |
| Subtitle | **Compress image batches with quality, format, resize, and metadata controls.** |
| Centered card | Maximum width 720 px; label **COMPRESS**, heading **Reduce image file size**. |
| Description | Smaller copies with WebP/JPEG/PNG optimization, optional resizing and metadata removal. |
| Feature lines | **Batch image inputs**, **Quality and max-size controls**, **Originals stay untouched**. |
| `Open image compressor` | One primary action; opens the modal compressor, prefilled from selected images in Convert, or all general-queue images when none are selected. |

This page is easy to understand. Its card stretches vertically, leaving substantial space between the short introduction and bottom launch button. That is a design choice, not a defect. Putting the compressor directly here would reduce a step and make more of the space useful; retaining a launch hub makes more sense if several image tools will be added.

### Compress Images dialog

Window title and heading: **Compress Images**. Starts at **680 × 540**, minimum **560 × 430**. Subtitle: **Create smaller image copies while keeping the originals unchanged.**

| Element | Default / behavior |
| --- | --- |
| File table | Columns **File**, **Type**, **Size**. Extended row selection. Inputs include JPG/JPEG, PNG, HEIC/HEIF, WEBP, BMP, TIFF, GIF and ICO. Resolved duplicate paths are ignored. Its information cells are currently editable, but edits do not change the stored input paths; they should be read-only. |
| `Add images` | Opens the supported-image picker. |
| `Remove` | Removes selected rows from this dialog only. |
| `Clear` | Empties its list. |
| `Output format:` | **WEBP** default; alternatives **JPG**, **PNG**, **Keep original format**. |
| `Quality:` | Slider **1–100**, initial **75%** with a live badge. The control remains available for PNG, although PNG uses lossless encoding rather than JPEG-style quality. |
| `Fit within` | Checked initially. Bounds are **64–20,000 px**, initially **1920 px wide × 1920 px tall**. The numeric fields do not disable when this is unchecked; unchecked values are ignored. |
| `Strip metadata from compressed copies` | Checked initially. |
| `Output folder:` | Blank means **Same folder as each image**. Browse selects a folder. |
| Output naming | Creates `_compressed` copies and numbered alternatives when a target exists. |
| Result banner | Initially blank. Later reports completed totals or failure, with semantic success/warning/error color. |
| Bottom status | Selected image count plus combined input size. |
| `Cancel` | Dismisses the idle dialog. Processing itself is synchronous, so this is not a responsive stop button during a compression job. |
| `Compress Images` | Remains enabled before adding files; clicking with none shows **No Images**. Runs the whole list, then reports successes, failures and byte savings. |
| Completion message | Offers to open the last output folder. Partial failure includes up to five errors; total failure shows up to eight. A successful/partially successful dialog closes after the message. |

[Open compressor screenshot](../scratch/ui-report/14-compress-images-dialog.png).

The compressor needs behavioral fixes. Same-format metadata cleaning currently returns early in the shared engine, bypassing requested resize/quality. If a same-format output is larger than its input, the dialog copies the original back to the destination, which can undo metadata removal or transformations. The GUI can therefore report success even when selected changes did not survive. Both behaviors were established in the technical review; the controls should not imply guaranteed changes until corrected.

## 4. PDF Tools page and its four dialogs

### PDF Tools launch page

The page says **PDF WORKSPACE** / **PDF tools**. Its subtitle includes **Your existing PDF engine and output behavior stay unchanged.** That implementation-oriented sentence is not useful product guidance; replace it with a practical explanation of local PDF tasks.

Four mutually exclusive controls select **Merge**, **Split**, **Organize** or **Compress**. Merge is selected first. Selecting one changes the explanatory card; it does not start processing or open the dialog. Each card has one primary launch button.

| Selected tool | Heading / feature lines / launch button |
| --- | --- |
| Merge | **Combine files into one PDF**; PDF and image inputs, Drag-friendly ordering, One combined output; **Open merge workspace**. |
| Split | **Split a PDF with precision**; Single pages, Every N pages, Custom ranges; **Open split workspace**. |
| Organize | **Rebuild page order visually**; Page thumbnails, Reorder and rotate, Non-destructive save; **Open page organizer**. |
| Compress | **Reduce PDF file size**; Three compression profiles, Original stays untouched, Clear savings report; **Open compression workspace**. |

Like Image Tools, the cards use generous space and put the action at the bottom. The actual merge/organize code uses move buttons; it does not configure drag reordering. **Drag-friendly ordering** should be removed or the feature implemented and verified. The dialogs prefill from selected/all Convert entries: merge gets selected/all paths, while single-PDF tools choose a selected PDF or the first PDF in the main queue.

[Merge page](../scratch/ui-report/05-pdf-tools-merge.png) · [Split page](../scratch/ui-report/06-pdf-tools-split.png) · [Organize page](../scratch/ui-report/06-pdf-tools-organize.png) · [Compress page](../scratch/ui-report/06-pdf-tools-compress.png).

### A. Merge Files to PDF

Window: **Merge Files to PDF**, **650 × 520**, minimum **500 × 400**. Heading: **Merge Files into a Single PDF**. Subtitle explains reordering PDFs/images into one document.

| Element | Behavior |
| --- | --- |
| File table | **File / Type / Size**; single row selection. Order from top to bottom is merge order. Information cells are currently editable, but changing their text does not change the stored input paths; this is misleading and should be read-only. |
| `Add files` | Picker defaults to PDFs and common images, with an All Files option. The intake can list other files; conversion validation happens later. |
| `▲ Move Up` / `▼ Move Down` | Moves the current file by one position and retains selection. Boundary clicks do nothing. No drag reorder is configured. |
| `Remove` / `Clear` | Removes current entry or all entries. No undo. |
| `Output PDF:` | Editable path; initial placeholder **Select destination file...**. Adding the first file supplies `merged_document.pdf` in its folder when the field is blank. |
| `Browse...` | Save-PDF picker. |
| File count | `N file(s) selected`; total pages/output estimate are not shown. |
| `Cancel` | Dismisses the dialog while idle. |
| `Merge to PDF` | Enabled before setup is complete. Fewer than two files triggers **Not Enough Files**; missing destination triggers **Missing Output**. |
| Success / failure | **Merge Successful** includes output path and Open/OK. **Merge Failed** includes the exception. Success closes the dialog. |

[Merge dialog screenshot](../scratch/ui-report/10-merge-dialog.png).

### B. Split PDF

Window: **Split PDF**, **520 × 420**. Heading: **Split PDF Document**. Subtitle explains single pages, chunks and ranges.

| Element | Default / behavior |
| --- | --- |
| File card | **No PDF file selected**, **Choose PDF...**, and **Pages: - • Size: -**. Selecting a valid PDF fills name/count/size and sets destination to its parent folder. |
| `Split every page into a separate PDF` | Selected initially. |
| `Split every N pages:` | Radio plus number **2–500**, default **2**. |
| `Custom page ranges (e.g. 1-2, 3-5, 8):` | Radio plus text field, placeholder **e.g. 1-3, 5, 7-end**. |
| Inactive mode fields | N and range fields remain editable even when their radios are inactive. Only the selected mode is used. Disabling inactive fields would make this clearer. |
| `Output Folder:` / `Browse...` | Editable destination plus existing-folder picker. |
| `Cancel` / `Split PDF` | Cancel dismisses. Split validates a source, destination and nonempty custom ranges when required. |
| Feedback | Invalid source shows **Invalid PDF**. Missing fields show warnings; invalid ranges or execution failures show **Split Failed**. **Split Complete** reports generated-file count and destination and offers Open/OK. |

The range parser validates page bounds, but the GUI does not preview exactly how many files/pages will be generated before submission.

[Split dialog screenshot](../scratch/ui-report/11-split-dialog.png).

### C. Reorganize PDF Pages

Window and heading: **Reorganize PDF Pages**, **780 × 560**. Subtitle: **Reorder, rotate, duplicate, or remove pages.**

![PDF page organizer](../scratch/ui-report/12-organize-dialog.png)

| Element | Behavior |
| --- | --- |
| `Choose PDF...` | Loads a document and replaces the staged page list. No explicit unsaved-change warning is implemented before switching documents. |
| Thumbnail grid | Icon mode, **100 × 140** icon size and 12 px spacing. Single current-page interaction. Source pages are rendered at 48 DPI. |
| Page labels | Show new page number, original source page number, and rotation if changed. This helps track reordered/duplicated pages. |
| `Move Left` / `Move Right` | Move current page one position. The grid reflows; these are logical previous/next operations even when rows wrap. |
| `Rotate 90°` | Adds 90° clockwise, wrapping at 360°. |
| `Duplicate` | Inserts a copy immediately after the current page and selects it. |
| `Delete` | Removes the page from the staged output, not the original PDF. Deleting the final remaining page shows **Cannot Delete**. |
| Page count | Shows staged page total. |
| `Cancel` | Dismisses without saving staged changes. |
| `Save Reorganized PDF...` | Opens a save picker, initially `<name>_organized.pdf`; writes only on save. |
| Feedback | No file/pages shows **No Pages**; save errors show **Save Failed**. **Saved Successfully** gives the path and Open/OK, then closes. |

No undo/redo, multiselect page operations, full-page inspection, drag reorder or zoom control is implemented. All thumbnails are regenerated after each operation, which compounds responsiveness costs on large PDFs. Those are useful future improvements; the existing staged editing model itself is understandable.

### D. Compress PDF

Window: **Compress PDF**, **500 × 360**. Heading: **Compress PDF File**. Subtitle: **Reduce file size using image resampling and stream deflation.**

| Element | Default / behavior |
| --- | --- |
| File card | **No PDF selected**, size dash, **Choose PDF...**. A valid selection shows filename and byte size. |
| Balanced profile | **Balanced (Recommended) — 150 DPI, 75% quality, stream deflation**, selected initially. |
| Maximum profile | **Maximum Compression — 100 DPI, 55% quality, smallest file size**. A best-effort profile, not a guarantee that every PDF will become smaller. |
| Lossless profile | **Lossless — Deflate streams and remove xrefs without altering images**. |
| Result banner | Initially blank; later success or no-reduction note. |
| `Cancel` | Dismisses while idle. |
| `Compress PDF` | Requires a source; then opens a save picker initially suggesting `<name>_compressed.pdf`. No per-image preview or predicted savings. |
| Success | Reports original/compressed sizes and percentage saved; offers output folder. |
| No improvement | Explicit **No Reduction Achieved** message; explains the original was already optimal and copied to the chosen output. |
| Error | **Compression Failed** with a reason. |

[PDF compressor screenshot](../scratch/ui-report/13-compress-pdf-dialog.png).

### Shared PDF-dialog interaction limits

All four dialogs perform their core operation synchronously on the UI thread. The organizer also loads/renders all thumbnails synchronously. They have no implemented job progress, elapsed/remaining time, responsive cancellation or retryable per-file result list. The Cancel buttons are ordinary dialog dismissal controls while idle; they should not be presented as equivalent to the main conversion worker's cooperative cancellation.

Most source-selection and output errors use modal warnings, followed by a separate success modal and then dialog closure. This makes outcomes explicit, but prevents quickly repeating a tool with a small adjustment. Keeping a completed result summary in the workspace would improve iterative use.

## 5. Remove Background page

This page is the dedicated image studio requested for backgroundG. It has a queue at left, two comparison cards at upper right, scrollable settings below them, and a persistent footer. The horizontal splitter starts around **340 / 940 px** and is not collapsible.

![Actual Fast-model result after Copy image](../scratch/background-gui-smoke/background-page.png)

### A. Heading and image intake

| Element | Behavior |
| --- | --- |
| `IMAGE STUDIO` / `Background removal` | Eyebrow and page title. |
| Subtitle | **Create clean cutouts locally. Drop JPEG, PNG, WebP, BMP, or TIFF images here.** |
| `Image queue` / image count | Separate queue from Convert, singular/plural count. |
| `Add images` | Supported-image multiselect picker. |
| `Use conversion queue` | Imports selected Convert entries, or all entries when there is no selection; unsupported types are skipped and duplicates ignored. Does not move/delete them from Convert. |
| Image list | Extended selection, filename plus state. The current row controls the comparison and Copy action. |
| `Remove selected` / `Clear` | Edits this queue only, preserving files and saved outputs on disk. Both remain enabled when empty and do nothing without applicable entries; busy state disables them. No removal undo is provided. |
| Limit hint | **Up to 25 MiB and 120 megapixels per image. Originals stay untouched.** The adapter enforces limits and no-clobber output publication. |
| Supported inputs | JPEG, PNG, WebP, BMP, TIFF. Animated/multipage input is rejected. HEIC/GIF/ICO are outside this tool's accepted set even when Convert supports them. |
| Skipped-file feedback | **Some files were skipped. Use JPEG, PNG, WebP, BMP, or TIFF.** It does not list every skipped item/reason. |

Adding input uses resolved unique paths and initially selects the first image. Queue text is **Queued**, **Done · PNG/WEBP**, **Failed** or **Cancelled**. Successful tooltips show the saved output; failed tooltips expose the reason. The current file does not receive a separate visible Loading/Converting state while inference is active, so the footer is the main activity indicator.

### B. Original and Result previews

| Element | Behavior |
| --- | --- |
| `ORIGINAL` | Current input. Empty instruction: **Select an image to preview**. |
| `RESULT` | Current source's latest successful saved output. Empty instruction: **Your cutout will appear here**. |
| Loading state | **Loading preview…** while the image reader works in the thread pool. |
| Transparency | Checkerboard is drawn behind image pixels, making transparent areas visible. It is presentation only and is not copied/exported. |
| Scaling | Aspect ratio preserved inside the card. Preview decoding is bounded to 1200 × 900; full saved/copy resolution is separate. |
| Selection changes | Old asynchronous preview results are ignored, preventing a slow previous selection from replacing the current one. |
| Rerun | Clears the previous result mapping/preview before work starts, so a failed rerun does not present an old cutout as a new success. Saved previous files remain on disk. |
| Preview failure | Falls back to its placeholder; there is no separate detailed preview-error panel. |

There is no zoom/pan, draggable before/after divider or pixel inspection. The fixed side-by-side comparison is effective for an overall cutout check; detailed hair/edge validation would benefit from synchronized zoom as a later enhancement.

### C. Basic processing settings

| Control | Default / behavior |
| --- | --- |
| `Model` | **Fast** initially; **Balanced**, **Quality**, **Portrait** alternatives. All four files are installed and hash-verified in this environment. The GUI itself does not show installation/verification readiness per profile. |
| Fast / Balanced hint | **Efficient local processing: 2 CPU threads. The model is released after each batch. Fast uses the least RAM.** |
| Quality / Portrait hint | **Quality and Portrait require at least 8 GiB of free RAM. Choose Fast or Balanced when memory is limited.** This is the app's startup policy, not a guarantee of successful processing. |
| `Output` | **PNG** default; **WEBP** alternative. PNG supports transparency; WebP export is lossless. |
| `Save to` | Blank means **Same folder as each source image**. Editable path plus **Browse…**. |
| `Also save mask` | Unchecked; additionally saves a grayscale alpha mask. |
| `Keep EXIF metadata` | Unchecked; requests metadata retention when supported. This default is different from Convert's checked Preserve EXIF option. |
| Output naming | `_nobg` plus numeric disambiguation when needed; optional matching `_mask.png`. The adapter protects originals, existing targets and planned batch outputs. |
| `Show advanced settings` | Unchecked/collapsed initially. Expands additional controls and changes its label to **Hide advanced settings**. |

The model requirement is static explanatory text; the GUI does not show live available memory, an installed-model manager, a GPU/device selector, expected loading time or a model download action. A missing/invalid model is reported when processing starts. Fast and Balanced have completed real-image checks; successful Quality/Portrait inference is not established on this machine. A Quality-selected screenshot with the RAM hint is not a successful Quality job.

### D. Advanced settings, element by element

| Control | Default / range / effect |
| --- | --- |
| `Feather` | **0.00**, range **0–20**, step **0.2**. Softens mask edges. No units/help tooltip explains its visual effect. |
| `Edge shift` | **0**, integer range **−5 to +5**. Shrinks or expands the mask edge. The direction and sensible uses are not explained beside the field. |
| `Two-pass refinement` | Unchecked. Performs an additional refinement pass; increases processing work. |
| `Crop to subject` | Unchecked. Crops export to the detected subject. |
| Padding | **0 px**, range **0–2000 px**; adjacent to Crop to subject. Remains editable even when crop is off, although it is then not useful. A separate Padding label would improve association. |
| `Background` | Blank, placeholder **Transparent (or #ffffff)**. Text color entry rather than a picker; invalid color is reported before the worker starts. |
| `Model folder` | Blank, placeholder **Automatic: local, bundled, or cache**. Explicit folder overrides automatic model resolution. |
| Model-folder `Browse…` | Opens installed-model folder picker. It does not download a missing model. |
| Scroll area | Keeps advanced options reachable at minimum window size. Long paths scroll inside their editable field rather than fully fitting onscreen. |

Advanced settings need short explanations and a reset-to-defaults action. The page currently assumes the user understands feathering, edge shift and two-pass refinement. This is a usability recommendation, not a processing failure.

[Advanced-control layout](../scratch/ui-report/08-background-advanced.png) · [Actual completed result at minimum size](../scratch/background-gui-smoke/background-page-minimum.png) · [Quality RAM hint before processing](../scratch/background-gui-smoke/quality-memory-requirement.png).

### E. Footer, progress, errors and cancellation

| State / action | Current behavior |
| --- | --- |
| Initial | **Add images to get started**; Remove background disabled, Open output folder disabled, Cancel hidden. |
| Ready | **N images ready · Transparent PNG or lossless WebP**; Remove background enabled. |
| `Remove background` | Validates options and plans destinations, clears current result mappings, starts a background worker. |
| Loading/inference | **Loading model and removing backgrounds…** with an indeterminate bar at first. Queue add/remove/clear and settings disable; selection can still change, allowing a completed result to be inspected/copied while later images are processing. |
| Per-file progress | Bar becomes completed-image count, with **Processed X of N images**. No percentage inside model loading or a single inference is claimed. |
| Success/partial failure | **Complete · X saved · Y failed**, with the first failure appended to the status. Individual failure details remain in list tooltips. |
| `Cancel` | Appears only during work. Requests cancellation, disables itself and says **Cancelling after the current image finishes…**. Warmup/current inference can take time to return. |
| Cancelled | **Cancelled · X saved · Y failed**; unprocessed entries become Cancelled. Completed files stay on disk. |
| `Open output folder` | Enables after a successful output and opens the last successful directory. It may remain useful for the last run even after clearing the queue. |
| Window close during work | Requests cancellation and ignores the close. The message asks the user to close again after completion. |

The status line is useful but combines many roles: readiness, model activity, failure, copy progress and copy success. A copy action on an already finished item during a batch can temporarily replace the job message. Separate job status and transient clipboard feedback would make concurrent activity clearer.

### F. Copy image and paste

| Element | Current behavior |
| --- | --- |
| `Copy image` button | Beside RESULT. Disabled before a successful selected output exists. Tooltip says full-size cutout including transparency, with Ctrl+C. |
| Result context menu | Right-click RESULT → **Copy image**. |
| Ctrl+C | Works while the background image list or Result preview has focus. Copies the current row's successful result, not all selected images. |
| Preparation | Button becomes **Copying…**, disabled; status says **Preparing the full-size image for copying…**. Decode/PNG preparation is off the GUI thread. |
| Success | **Copied image. Paste with Ctrl+V.** Clipboard changes only after explicit successful copying. |
| Failure | **Could not copy image.** plus cause. Missing/replaced/unreadable output is not copied. Stale results after selection/rerun changes are discarded. |
| Payload | Actual saved full-resolution PNG/WebP decoded to pixels, PNG representation with alpha, native image, Windows PNG representation and a saved-file reference for file-manager paste. It does not copy the preview/checkerboard. |
| Paste destinations | Image-aware editors may accept pixels; Explorer-like folders can accept the file reference. Plain-text fields cannot display an image. File-reference pastes require the saved file to remain available. |
| Transparency limitation | Destination software chooses a clipboard format. Older apps choosing legacy DIB can discard alpha and expose hidden RGB/background. A PNG-aware paste destination or opening the saved PNG preserves the intended transparency path. |

The feature provides a useful direct workflow: **select a Done image → Copy image → switch to the destination → Ctrl+V**. Universal identical paste behavior cannot be guaranteed by this GUI because the receiving program decides what it accepts.

## 6. Cross-page behavior and usability findings

### Responsiveness

The main conversion and background-removal processing use workers. Queue analysis, background previews and full-resolution copy preparation also run outside the GUI thread. These are sound choices. Synchronous folder scanning, detailed inspector parsing, PDF thumbnail loading and all five utility-dialog operations remain the main reasons the application can appear frozen. A progress animation cannot fix blocking code by itself; the work must be moved off the GUI thread.

Cancellation is cooperative, not immediate process termination. That is expressed in the normal/background footer messages, but the utility dialogs do not provide equivalent running controls. The interface should consistently separate **Cancel remaining work**, **Stop requested** and **Close dialog**.

### Accessibility and keyboard use

Good foundations include visible focus rings, explicit names for major queues/previews, textual status labels, normal Qt controls and a deliberate main-window tab order. The contrast audit covers useful high-frequency pairs.

Remaining source-level gaps include labels without explicit buddies/accessible names for many advanced fields, no consistent keyboard shortcut for changing workspaces, no visible shortcut reference, and custom-painted preview/status content that needs a screen-reader test. The generic Result preview's accessible name remains its placeholder text rather than a descriptive summary of the selected result. Keyboard operation of the context menu and every tool action should be verified with assistive technology. None of these observations proves that a screen reader fails; that test has not been completed.

High-DPI, larger Windows text, high-contrast mode, color-vision variations and keyboard-only operation on a small display remain validation gaps. The fixed minimum and small secondary text warrant specific 125/150/200% scaling checks. No in-app theme or language selection is implemented; the visible UI is English.

### Persistence and continuity

There is no implemented settings/session persistence, conversion history, crash recovery, saved queue, favorites or remembered window geometry through QSettings. Navigation retains state only within the running window. Closing and reopening starts a new in-memory workspace. Output files remain on disk, but the GUI does not restore them into a result gallery. An explicit Reset settings action is also absent.

### Feedback and trustworthy wording

The interface generally names actions clearly and shows success/failure explicitly. Its biggest wording problems are promises stronger than behavior: **originals are never overwritten**, **Strip all metadata**, **Clean (no tracking tags)**, unsupported document targets, and OCR/decryption options that do not apply to all implied routes. These should be fixed along with their underlying behavior.

Per-file failure reasons are often in hover tooltips. A selectable error/details panel would help users copy a cause, locate a file and understand a partial batch without hunting. The main completed queue also lacks a per-result **Open output / Copy output path** action; its Open folder is shared and source inspection still focuses on inputs.

## 7. Prioritized GUI findings and recommended changes

**P1** means fix before general release because data integrity or a major user promise is affected. **P2** means significant usability/correctness work. **P3** means polish or a useful later enhancement. “Confirmed” refers to source inspection or the technical review's scratch reproductions; “design judgment” is an assessment rather than a measured failure.

| ID / priority | Finding and evidence type | Recommended change / acceptance condition |
| --- | --- | --- |
| GUI-01 · P1 | **Output safety promise exceeds actual conversion planning. Confirmed, reproduced in the technical review.** A batch output can overwrite another queued input or an existing destination. | Reserve every input/planned output, make collisions explicit, default to unique names, then retain an originals-protected message only after that guarantee holds. |
| GUI-02 · P1 | **Requested image transformations can be discarded. Confirmed/reproduced.** Metadata-cleaning early return and compressor original-copy fallback can bypass resize/quality/cleaning. | Apply transformations in a consistent pipeline. Do not fall back to original content when the user requested a semantic change; report no size saving separately. |
| GUI-03 · P2 | **Busy queue can still mutate. Source-confirmed.** Target editors, direct context removal and shortcut intake do not share the toolbar lock. | Enforce one model-level busy guard, use stable task identities, and verify every input route during a running batch. |
| GUI-04 · P2 | **Tool dialogs can block the window. Source-confirmed.** All five core operations and organizer rendering are synchronous. | Use workers, immutable job inputs, progress, cooperative cancellation and visible completion state. The window should remain interactive during a large fixture. |
| GUI-05 · P2 | **Capability/options do not consistently match engine support. Confirmed.** PDF→PPTX, Word→PPTX, PPTX→DOCX and implied OCR/decryption routes mislead. | Drive menus and field availability from the same tested capability registry; identify required local tools before submission. |
| GUI-06 · P2 | **Privacy labels overstate cleaning. Confirmed.** Broad strip/clean messages do not mean complete sanitization. | Name supported properties, show actual cleaning results, and avoid all/clean guarantees that cannot be demonstrated. |
| GUI-07 · P2 | **PDF-only rendering hides Render DPI. Source-confirmed.** Resize tab is gated by image inputs. | Show document-render settings by source/target capability, independently from image resize controls. |
| GUI-08 · P2 | **Global commands can act on a hidden queue. Source-confirmed.** Ctrl+Return/Escape on Image/PDF Tools route to Convert; separate workers may run together. | Scope commands to the visible workspace and add a shared running-job indicator/resource policy. |
| GUI-09 · P2 | **Estimates can look authoritative without enough input. Source-confirmed; design impact inferred.** Fixed ratios do not model render/page/transform cost. | Mark as rough, hide unsupported estimates or add calibrated estimators. Distinguish Actual size in completed rows. |
| GUI-10 · P2 | **Model readiness is implicit. Source-confirmed.** Picker lists profiles but does not show installed/verified/free-memory status or explain startup delay. | Add readiness states and a compact model/device panel. Preserve the clear 8 GiB large-model explanation until a verified resource policy replaces it. |
| GUI-11 · P2 | **Accessibility/scaling evidence is incomplete. Validation gap.** Token contrast is tested; assistive technology, full focus paths and DPI are not. | Name/associate every input, expose result summaries and test NVDA plus keyboard-only and 125/150/200% Windows scaling. |
| GUI-12 · P3 | **Mixed state and preset labels need refinement. Confirmed.** Raw PER_FILE and presets that stay checked after manual edits. | Use Per file / Custom settings labels and synchronize the visible preset state with actual values. |
| GUI-13 · P3 | **Tool launch cards add a step and consume large space. Design judgment.** Clear but sparse pages lead to modal workspaces. | Prefer direct embedded workspaces, or keep a compact hub when several tools justify it. |
| GUI-14 · P3 | **Inactive option fields remain editable. Source-confirmed.** Split N/ranges, image Fit within bounds and background crop padding. | Disable inactive fields and add brief inline guidance while retaining stored values. |
| GUI-15 · P3 | **Removal recovery and output navigation vary. Source-confirmed.** Context removal lacks toolbar Undo; background queue has no undo; folder actions point to a single remembered location. | Use consistent undo for queue edits and attach Open/Copy path actions to each successful output. |
| GUI-16 · P3 | **Organizer has no undo or unsaved-change prompt. Source-confirmed.** Opening another PDF replaces staged work. | Add undo/redo, discard confirmation when needed, and cached/lazy thumbnails for larger documents. |
| GUI-17 · P3 | **No persistence or job history. Source-confirmed.** Preferences, geometry and queues are memory-only. | Persist safe preferences/geometry first, then add recoverable history without storing passwords. |
| GUI-18 · P3 | **Advanced background controls assume technical knowledge. Design judgment.** Feather/shift/two-pass/padding lack contextual explanations. | Add examples/tooltips, a labeled Padding control, Reset defaults and later synchronized edge zoom. |
| GUI-19 · P2 | **Informational file cells accept misleading edits. Reproduced with a tiny disposable image, without conversion.** Merge/compressor File/Type/Size cells are editable, while processing still uses the unchanged internal paths. | Make information cells read-only. If renaming is desired, implement it as an explicit output-name action with matching behavior. |

A practical sequence is: **protect outputs and honor transformations → lock busy state and align capabilities → make all tools responsive → improve accessibility, model readiness and results → refine spacing and convenience**. This order improves trust and usability before adding more surface area.

## 8. Screenshot index and evidence boundaries

All links below point to local capture artifacts. The linked PNGs are useful for reviewing composition and visible states; they are not independent proof that every backing format/tool was exercised. Some offscreen modal backgrounds appear black/transparent; this alone is not evidence of a native Windows rendering defect.

| Capture | What it establishes |
| --- | --- |
| [Convert empty](../scratch/ui-report/01-convert-empty.png) | Empty queue, pickers, disabled conversion state. |
| [Convert batch settings](../scratch/ui-report/02-convert-batch-settings.png) | Populated/mixed queue, settings hierarchy, raw PER_FILE presentation. |
| [Convert file inspector](../scratch/ui-report/03-convert-file-inspector.png) | Right-panel replacement and input inspection layout. |
| [Image Tools page](../scratch/ui-report/04-image-tools.png) | Compression launch card and its spacing. |
| [PDF Merge page](../scratch/ui-report/05-pdf-tools-merge.png) | Default PDF launch card. |
| [PDF Split page](../scratch/ui-report/06-pdf-tools-split.png) | Split launch-card content. |
| [PDF Organize page](../scratch/ui-report/06-pdf-tools-organize.png) | Organize launch-card content. |
| [PDF Compress page](../scratch/ui-report/06-pdf-tools-compress.png) | Compression launch-card content. |
| [Merge dialog](../scratch/ui-report/10-merge-dialog.png) | Ordering/output controls; layout capture. |
| [Split dialog](../scratch/ui-report/11-split-dialog.png) | Mode/range/output controls; layout capture. |
| [Organizer dialog](../scratch/ui-report/12-organize-dialog.png) | Page thumbnails and staging actions. |
| [PDF compressor dialog](../scratch/ui-report/13-compress-pdf-dialog.png) | Three profiles and action arrangement. |
| [Image compressor dialog](../scratch/ui-report/14-compress-images-dialog.png) | Batch/format/quality/resize/metadata controls. |
| [Actual Fast result + Copy](../scratch/background-gui-smoke/background-page.png) | Real completed background removal and asserted Copy image success. |
| [Actual Fast result at minimum size](../scratch/background-gui-smoke/background-page-minimum.png) | Result, Copy button and footer at the 1120 × 700 minimum. |
| [Quality memory hint](../scratch/background-gui-smoke/quality-memory-requirement.png) | Quality selected with the 8 GiB hint before processing; not successful Quality inference. |
| [Background advanced settings](../scratch/ui-report/08-background-advanced.png) | Static advanced-control layout with an earlier real output assigned for inspection; Queued text is not a completed-job claim. |

## 9. Verification and source references

The earlier focused application run passed **140 tests** with one deselected; it included page navigation, empty/inspector transitions, multi-selection, tool error presentation, background job lifecycle and clipboard cases, alongside core/CLI checks. The background library separately passed **240 tests, 3 skipped**. These counts are not GUI-only test counts. The full Office-dependent application suite was not established green. Native Windows clipboard evidence covers full-resolution PNG/alpha and file references; individual destination apps still need interoperability testing.

This GUI-report pass added source/control cross-checking and reran the small token contrast audit. It did not rerun Office conversions or heavy model inference. Uncompleted validation includes full screen-reader navigation, every scaling setting, every destination app's paste behavior, all large-file interaction paths, successful Quality/Portrait inference on this machine, and a complete usability study with users.

Primary source map:

- [Window, header, navigation, shortcuts and conversion lifecycle](../image_converter/ui/main_window.py)
- [Queue model, delegates, row editing and context menu](../image_converter/ui/queue_model.py)
- [Drop zone, conversion settings and file inspector](../image_converter/ui/components.py)
- [Image Tools launch page](../image_converter/ui/image_tools_page.py)
- [PDF Tools selector/cards](../image_converter/ui/pdf_tools_page.py)
- [All five tool dialogs](../image_converter/ui/tool_dialogs.py)
- [Background-removal workspace, preview and copy states](../image_converter/ui/background_removal_page.py)
- [Full-resolution clipboard preparation](../image_converter/ui/image_clipboard.py)
- [Theme tokens and focus styling](../image_converter/ui/theme.py), [contrast audit](../image_converter/ui/contrast.py)
- [UI redesign checks](../image_converter/tests/test_ui_redesign.py), [background page checks](../image_converter/tests/test_background_page.py), [clipboard checks](../image_converter/tests/test_background_clipboard.py), [tool-dialog checks](../image_converter/tests/test_tool_dialogs.py)

The recommended next GUI milestone is a trustworthy, responsive workflow across all four pages: predictable output planning, controls that accurately match capabilities, consistent cancellation, clear per-output results and verified keyboard/scaling behavior. The existing visual system is a workable foundation for that milestone.
