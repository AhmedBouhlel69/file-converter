# Local Background Remover: Technical Specification Book

*Version 1.0 · 17 October 2026 · A fully offline, self-hosted alternative to cloud background-removal services*

## 1. Purpose, scope and key decisions

**Goal.** Build a tool that runs entirely on your own machine, takes an image, and returns the same image with a transparent background (RGBA), plus optional extras such as the mask, a replacement background, or a subject-cropped version.

**Core technical decision.** Use a pretrained *salient-object segmentation / matting* neural network executed through ONNX Runtime. Do not use YOLO: it predicts bounding boxes (or class-limited instance masks), whereas background removal needs a per-pixel foreground opacity for any kind of object, including hair, fur and semi-transparent edges. No model training is required for version 1.

**In scope (v1):** single and batch image processing, CLI, Python library, local REST API, model profiles, mask refinement, benchmarks, tests, packaging.

**Later phases:** desktop or web GUI, interactive click-to-select (SAM 2), video, fine-tuning on a custom domain.

**Out of scope:** cloud hosting, mobile apps, training a network from scratch.

**Success criteria** (design targets to verify on your own hardware and test set):

| Area | Target |
| --- | --- |
| Privacy | Zero network calls during inference, verified by a test run with networking disabled |
| Quality | Mean IoU ≥ 0.95 on your own 100-image test set; clean, soft hair edges on portraits |
| Speed | Fast profile under 1 s on an 8-core CPU; quality profile under 2 s on a mid-range GPU (12 MP image) |
| Memory | Under 4 GB RAM peak for a 24 MP image |
| Fidelity | Output has the same pixel dimensions, orientation and colour profile as the input |

## 2. Requirements

**Functional requirements**

| ID | Requirement |
| --- | --- |
| FR-01 | Read JPEG, PNG, WebP, BMP and TIFF; HEIC/HEIF through an optional extra |
| FR-02 | Write RGBA PNG or lossless WebP with a transparent background |
| FR-03 | Optional outputs: 8-bit mask, solid-colour background, custom background image, blurred background, crop to subject, drop shadow |
| FR-04 | Batch-process folders recursively, with parallelism control and skip-existing/resume |
| FR-05 | Model profiles: fast, balanced, quality, portrait |
| FR-06 | Refinement controls: threshold, edge shift, feather, small-blob cleanup, alpha matting |
| FR-07 | Interfaces: CLI, Python API, local REST API |
| FR-08 | Deterministic output for identical input and settings |
| FR-09 | Always output at the original resolution |

**Non-functional requirements**

| ID | Requirement |
| --- | --- |
| NFR-01 | Works fully offline once models are installed |
| NFR-02 | Runs on Windows, macOS (Intel and Apple Silicon) and Linux |
| NFR-03 | The CPU path always works; GPU acceleration is optional and auto-detected |
| NFR-04 | The default model has a licence that allows your intended use (see section 14) |
| NFR-05 | Every pipeline stage is a pure, unit-testable function |
| NFR-06 | Inputs are validated: size limits, decompression-bomb guard, corrupt-file handling |

## 3. Model strategy

**Why segmentation and matting.** Four task families exist. Object detection (YOLO) returns boxes. Instance segmentation (YOLO-seg, Mask R-CNN) returns masks for a fixed list of classes. Salient-object or dichotomous segmentation (U²-Net, IS-Net, BiRefNet) returns a foreground mask for arbitrary objects. Matting returns a soft alpha channel with the best edge quality. General background removal belongs to the last two.

**Candidate models.** Sizes and licences change between releases, so read each model card before adopting a model and record the result in a MODELS.md file.

| Model | Type | Native input | Approx. size | Licence (verify) | Best for |
| --- | --- | --- | --- | --- | --- |
| U²-Netp | Salient segmentation | 320×320 | \~5 MB | Apache-2.0 | Ultra-light CPU use, previews |
| U²-Net | Salient segmentation | 320×320 | \~170 MB | Apache-2.0 | Legacy baseline |
| IS-Net (DIS, general-use) | Dichotomous segmentation | 1024×1024 | \~170 MB | Apache-2.0 | Balanced default |
| BiRefNet (general) | Bilateral-reference segmentation | 1024×1024 | \~0.9 GB (fp32) | MIT | Best open-source quality, fine edges |
| BiRefNet lite | Same, smaller backbone | 1024×1024 | \~0.2 GB | MIT | Quality/speed compromise |
| RMBG-1.4 / 2.0 (BRIA) | Salient segmentation | 1024×1024 | \~0.18 GB / \~0.9 GB | Non-commercial unless licensed from BRIA | Personal and research use |
| MODNet | Portrait matting | \~512 reference | \~25 MB | Apache-2.0 | Real-time, people only |
| SAM 2 / MobileSAM | Promptable segmentation | 1024×1024 | 40 MB to \~0.9 GB by variant | Apache-2.0 | Click-to-select tools |

**Recommended profiles**

| Profile | Model | When it is the default |
| --- | --- | --- |
| fast | U²-Netp (320²) | Previews, weak CPUs |
| balanced | IS-Net general-use (1024²) | CPU-only machines |
| quality | BiRefNet general (1024²) | Machines with a GPU |
| portrait | BiRefNet portrait variant or MODNet | People-only workflows |
| noncommercial | RMBG-1.4 / 2.0 | Blocked unless the user explicitly opts in |

**Adding a model means adding a config entry, not code.** Every model-specific constant lives in a registry file such as this:

```yaml
name: birefnet-general
file: birefnet_general.onnx
sha256: <fill in after download>
input_size: [1024, 1024]
mean: [0.485, 0.456, 0.406]
std: [0.229, 0.224, 0.225]
output_index: 0              # which ONNX output holds the final mask
output_activation: sigmoid   # sigmoid | none
precision: fp32              # fp32 | fp16
licence: MIT
commercial_use: true
```

## 4. Architecture

The system is a linear pipeline of seven stages. Each stage takes arrays in and returns arrays out, with no hidden state.

```
input (path or bytes)
  -> 1 Loader        decode, validate, EXIF rotate, colour space, RGB uint8
  -> 2 Preprocess    resize to model size, normalise, NCHW float32
  -> 3 Inference     ONNX Runtime session (GPU if available, else CPU)
  -> 4 Postprocess   activation, resize to original size, clip -> mask 0..1
  -> 5 Refine        optional: threshold, cleanup, feather, matting
  -> 6 Compose       RGBA, solid colour, blur, custom background, crop
  -> 7 Export        PNG / WebP / mask file, metadata policy
```

**Module responsibilities**

- **loader**: decode and validate; returns an RGB uint8 array plus metadata (ICC profile, original mode, original size).
- **preprocess / postprocess**: the only places that know about model tensors; driven entirely by the model config.
- **engine**: owns the ONNX Runtime session, provider selection, warm-up and the GPU lock.
- **refine**: mask clean-up and matting; never touches pixel colour except through foreground estimation.
- **compose / export**: build the final image and write it atomically.
- **registry**: reads model configs, verifies SHA-256, enforces licence gating.
- **remover**: orchestrates the stages and records per-stage timings.

**Design rules**

1. Pure functions between stages; numpy arrays in, numpy arrays out.
2. One session per model per process, created lazily and reused.
3. No model constants in code; everything comes from the registry.
4. Every stage logs its duration at DEBUG level.
5. The inference path must not import any networking code.

## 5. Technology stack

| Layer | Choice | Notes |
| --- | --- | --- |
| Language | Python 3.11 or 3.12 | Type hints, mypy in CI |
| Inference | onnxruntime | Install exactly one variant: onnxruntime (CPU, and macOS with CoreML), onnxruntime-gpu (NVIDIA CUDA), onnxruntime-directml (Windows, any GPU). OpenVINO provider for Intel |
| Images | Pillow, opencv-python-headless, NumPy | Pillow for I/O and colour, OpenCV for resize and morphology |
| HEIC | pillow-heif | Optional extra |
| Matting | pymatting | Optional; CPU-heavy |
| CLI | Typer | Subcommands and help generated from type hints |
| API | FastAPI + Uvicorn | Local only by default |
| GUI (later) | PySide6, or a web front end served by FastAPI | Phase 3 |
| Quality | pytest, ruff, mypy | Run in CI |
| Packaging | pyproject.toml, uv or pip, PyInstaller, Docker | See section 15 |

**Hardware guidance.** CPU: 4 or more cores, 16 GB RAM recommended for the quality profile. GPU: plan for at least 6 GB of VRAM for BiRefNet at 1024² in fp32; fp16 roughly halves the need. Measure on your own machine rather than trusting any rule of thumb.

## 6. Environment setup

**6.1 Python environment**

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv/Scripts/Activate.ps1
python -m pip install -U pip

# Install exactly ONE onnxruntime variant:
pip install onnxruntime             # CPU, and macOS (CoreML provider included)
# pip install onnxruntime-gpu       # NVIDIA CUDA machines
# pip install onnxruntime-directml  # Windows with AMD, Intel or NVIDIA via DirectML

pip install numpy pillow opencv-python-headless typer fastapi 'uvicorn[standard]' pymatting pillow-heif platformdirs pytest
```

**6.2 Acquire models**

- **Option A (recommended for v1):** download ready-made ONNX files from the model authors or from the rembg release assets. Store them in the model cache directory, compute the SHA-256 of each file and write it into the registry.
- **Option B:** export from PyTorch yourself.

```python
import torch

model.eval()
dummy = torch.randn(1, 3, 1024, 1024)
torch.onnx.export(
    model, dummy, "model.onnx", opset_version=17, input_names=["input"], output_names=["output"]
)
```

BiRefNet uses deformable convolutions, which can make a self-export fiddly. Prefer the maintainers’ or rembg’s published ONNX files, and for any export run **a parity check**: feed the same 10 images to PyTorch and ONNX Runtime and require a maximum absolute difference below 1e-3 on the output mask.

**6.3 Smoke test**

```bash
python -c 'import onnxruntime as o; print(o.get_available_providers())'
```

The list must contain CPUExecutionProvider, and CUDAExecutionProvider, CoreMLExecutionProvider or DmlExecutionProvider if you expect GPU acceleration.

## 7. Pipeline specification

### 7.1 Loader

1. Set `Image.MAX_IMAGE_PIXELS` to a hard cap (default 120 million pixels) and reject larger files with a clear error.
2. Detect the real format from file content, not from the extension.
3. Apply `ImageOps.exif_transpose` before anything else, so pixels and mask share one orientation.
4. Normalise colour modes: P, L, LA, RGBA become RGB; CMYK becomes RGB (use the embedded ICC profile through ImageCms when present); 16-bit becomes 8-bit. Any input alpha is ignored for inference.
5. Keep the ICC profile bytes and the original size for export.
6. Animated inputs: first frame only in v1.

### 7.2 Preprocess

1. Resize the RGB array to the model’s `input_size` with bilinear interpolation (`cv2.INTER_LINEAR`). Stretch to the square; do not letterbox, because the reference models were trained and published that way. Mixing strategies silently degrades quality.
2. Convert to float32 and divide by 255.
3. Normalise as `(x - mean) / std` using the model config. Most models above use ImageNet statistics (mean 0.485, 0.456, 0.406; std 0.229, 0.224, 0.225). RMBG-1.4 uses mean 0.5 and std 1.0, and rembg’s U²-Net variants first divide by the image maximum. Always copy the exact recipe from the model card or reference code.
4. Transpose HWC to CHW and add a batch axis, giving shape 1×3×H×W.
5. Cast to float16 only if the ONNX file was exported in fp16.

### 7.3 Inference

1. Build the provider list in priority order, filtered by `ort.get_available_providers()`: CUDA, CoreML, DirectML, then CPU. CPU is always last as the fallback.
2. Session options: `graph_optimization_level = ORT_ENABLE_ALL`, `intra_op_num_threads` = physical core count (configurable), `inter_op_num_threads = 1`.
3. Create the session once per model per process and run two warm-up inferences on a dummy tensor at startup. The first call is much slower because of kernel selection and memory allocation.
4. Batch size is 1 in v1. Serialise GPU access with a lock or a single-worker queue.
5. Log the active provider at startup. If the user requested CUDA but received CPU, warn or fail, according to a `--strict-device` flag.

### 7.4 Postprocess

1. Select the output tensor using `output_index` from the config.
2. If `output_activation` is sigmoid, apply it. During development print the min and max of the raw output: values outside 0 to 1 mean the model returns logits.
3. Squeeze to H×W float32.
4. Optional min-max stretch (U²-Net style). Disable it for images that may contain no subject, otherwise noise gets amplified.
5. Resize to the original width and height with bicubic interpolation (`cv2.INTER_CUBIC`) or Lanczos, then clip to 0..1.
6. Keep float32 internally; quantise to uint8 only at export.

### 7.5 Refinement

| Step | Default | Parameter | Purpose |
| --- | --- | --- | --- |
| Hard threshold | off | threshold (0 to 1) | Binary mask; use only for graphics and logos, otherwise keep soft alpha |
| Edge shift | 0 px | edge\_shift (-5 to +5) | Negative values erode the mask 1 to 3 px to remove background halos |
| Blob cleanup | on | min\_blob\_ratio (0.001) | Remove isolated regions under 0.1 % of the image with `cv2.connectedComponentsWithStats`; fill small holes |
| Feather | 0 | feather\_sigma (0.5 to 2 px) | Gaussian blur applied to the edge band only |
| Guided filter | off | radius 8 to 16, eps 1e-4 to 1e-3 | Snaps the upsampled mask to real image edges at full resolution |
| Alpha matting | off | matting (bool) | Best result for hair and fur; recipe below |

**Alpha-matting recipe (pymatting)**

1. Build a trimap from the soft mask. Definite foreground is mask > 0.95 eroded by k px; definite background is mask < 0.05 dilated by k px; everything else is unknown. Use k = 10 to 25 px, scaled to image size.
2. Run `estimate_alpha_cf(image_float, trimap)` (closed-form matting) on a working copy of at most 4 MP, then upsample the alpha (see section 8). It is CPU-heavy and can take many seconds on large images.
3. Run `estimate_foreground_ml(image_float, alpha)` to recover clean foreground colours; this removes colour fringes left by the old background.
4. Use the returned foreground as the RGB of the output.

### 7.6 Compose

- **Default:** RGBA where RGB comes from the original (or the decontaminated foreground) and A = mask × 255.
- **Over a new background:** `out = alpha * F + (1 - alpha) * B`, computed in float32.
- **Options:** solid colour; background image with cover-fit (scale to fill, centre-crop); blurred copy of the original background (Gaussian, radius parameter); soft drop shadow (blur the alpha, offset it, opacity 0.3 to 0.5, composite under the subject); crop to subject (bounding box of alpha > 0.05 plus padding); pad to a square or fixed-aspect canvas.

### 7.7 Export

- **PNG:** `compress_level=6`, keep the ICC profile, strip EXIF and GPS by default for privacy (`--keep-metadata` to override).
- **WebP:** `lossless=True, method=4`.
- **Mask:** 8-bit single-channel PNG with the same dimensions as the input.
- **Names:** `{stem}_nobg.png` and `{stem}_mask.png`.
- **Safety:** write to a temporary file and rename atomically; never overwrite unless `--overwrite` is given.

## 8. High-resolution handling

The network sees a 1024×1024 (or 320×320) version of the image, so fine detail is lost on 12 to 50 MP photos. Three strategies, in increasing cost:

1. **Upsample and snap (default).** Predict the mask at model resolution, upsample it to full size, then snap it to real edges with a guided filter, using the full-resolution image as the guide. OpenCV’s `cv2.ximgproc.guidedFilter` lives in the opencv-contrib-python-headless package; otherwise implement the filter with box filters.
2. **Two-pass crop (quality).** Pass 1 predicts a coarse mask. Compute its bounding box plus a 10 % margin, crop the original to that box, run pass 2 on the crop, then paste the refined mask back. This greatly helps small subjects in large frames.
3. **Band matting.** Run closed-form matting only on the unknown band around the edge at full resolution, in overlapping tiles, instead of on the whole image.

Do not tile the neural network itself with small windows: these models rely on global context and tile seams show up in the mask.

**Memory guard.** Cap the working copy for matting at 4 MP, keep full-resolution RGB and alpha as uint8, free intermediate float arrays early, and reject or downscale inputs above the pixel cap.

## 9. Performance and optimisation

| Lever | Applies to | Effect and caveat |
| --- | --- | --- |
| fp16 model | GPU | Roughly half the memory and faster; compare masks against fp32 |
| INT8 dynamic quantisation | CPU | Smaller and faster; check edge quality, fine detail can degrade |
| Smaller model or input size | All | The biggest speed lever; test 768 or 512 inputs on your own set |
| Execution providers | All | CUDA, TensorRT, CoreML, DirectML, OpenVINO; benchmark, gains vary by model |
| IO binding | CUDA | Keeps tensors on the device and avoids copies |
| Process pool for batches | CPU | Keep processes × threads ≤ physical cores to avoid oversubscription |
| Avoid copies | All | Use `cv2.resize` on NumPy arrays directly; avoid PIL/NumPy round-trips in loops |
| Result cache | API | Key on SHA-256 of the input bytes plus the settings |

**Benchmark protocol.** Three warm-up runs, then 20 timed runs per image size (1, 12 and 24 MP) and per profile. Report median and p95 per stage (load, preprocess, inference, postprocess, refine, export), plus peak RAM and VRAM. Record CPU and GPU model, OS, ONNX Runtime version and active provider. Save results as JSON so commits can be compared.

**Design targets** (targets to validate, not measurements; replace them with your own numbers):

| Profile | Mid-range GPU | 8-core CPU |
| --- | --- | --- |
| fast | under 0.1 s | under 0.5 s |
| balanced | under 0.3 s | under 3 s |
| quality | under 1 s | under 15 s |

## 10. Interfaces

**10.1 Command line**

```
bgremove INPUT [INPUT...] -o OUTDIR [options]

  --model {fast,balanced,quality,portrait}   default: balanced
  --device {auto,cpu,cuda,coreml,dml}        default: auto
  --strict-device                            fail if the requested device is unavailable
  --format {png,webp}                        default: png
  --save-mask | --mask-only
  --bg-color '#RRGGBB' | --bg-image PATH | --bg-blur RADIUS
  --shadow
  --threshold FLOAT
  --edge-shift INT
  --feather FLOAT
  --matting | --no-matting
  --crop --padding INT
  --jobs INT                                 parallel workers
  --recursive  --skip-existing  --overwrite
  --keep-metadata
  --allow-noncommercial
  --verbose
```

Exit codes: 0 success, 1 partial failure in a batch, 2 invalid arguments, 3 model missing or hash mismatch, 4 unsupported or corrupt input. Subcommands: `bgremove models list|pull|verify`, `bgremove bench`, `bgremove serve`.

**10.2 Python API**

```python
from bgremove import Remover

remover = Remover(model="quality", device="auto")
result = remover.remove("photo.jpg", matting=True)  # path, bytes or PIL.Image
result.rgba.save("photo_nobg.png")  # PIL RGBA image
result.mask  # float32 array, H x W, 0..1
result.timings  # dict of per-stage seconds
```

**10.3 REST API (FastAPI)**

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/v1/remove` | POST | Multipart upload (file plus options); returns image bytes, or JSON with base64 on request |
| `/v1/models` | GET | Installed models, licences, active provider |
| `/v1/health` | GET | Liveness and readiness (model loaded) |

Rules: bind to 127.0.0.1 by default; max upload 25 MB plus the pixel cap from section 7.1; one inference at a time per GPU (semaphore); request timeout; no CORS unless configured; optional API-key header; structured errors with HTTP 400 (bad input), 413 (too large), 422 (bad options) and 503 (model not ready).

**10.4 GUI (phase 3).** Drag and drop, checkerboard preview, before/after slider, model dropdown, refinement sliders with live preview on a downscaled copy, batch queue and save-as. Phase 4 adds brush add/remove and click-to-select.

## 11. Later phases: interactive tools and video

**Interactive refinement.** Use SAM 2 (or MobileSAM on light machines). Run the image encoder once per image and cache the embedding, then run the small prompt decoder on every click or box; this keeps interaction fast. A lighter fallback is OpenCV GrabCut seeded by user scribbles (foreground and background brushes).

**Video.** Per-frame segmentation flickers. Option A: run the image model per frame and smooth alpha over time (exponential moving average, reset on scene cuts). Option B: use a recurrent video-matting model such as Robust Video Matting, which keeps temporal state; check its licence first, as it has been published under GPL-3.0. Pipeline: ffmpeg decodes frames over a pipe, the tool processes them, and ffmpeg encodes with alpha (ProRes 4444 or VP9 WebM). Mux the original audio back in.

## 12. Evaluation and quality assurance

**Metrics.** Segmentation: IoU, MAE, F-measure, boundary F-score. Matting: SAD, MSE, gradient and connectivity errors. Always add a human side-by-side review, because metrics miss halos and colour fringes.

**Test set (100 to 300 images from your real use).** Portraits with flyaway hair; products on white and on busy backgrounds; glass and transparent objects; fur and feathers; low-contrast subjects; cluttered scenes; small subject in a large frame; multiple subjects; text and logos; motion blur; extreme aspect ratios.

**Ground truth.** Create masks semi-manually with SAM 2 plus hand clean-up. For a sanity check you can also use public sets: DIS5K (dichotomous segmentation), DUTS (salient objects), AIM-500 and P3M-10K (portrait matting), Composition-1k (matting). Check each dataset’s licence.

**Automated tests**

- Output shape equals input shape, dtype is uint8, alpha stays within 0..255.
- An EXIF-rotated image produces a correctly oriented result.
- Grayscale, palette, CMYK, 16-bit, 1×1 px and very wide images do not crash.
- Corrupt, zero-byte and over-cap files produce clear errors.
- Determinism: two runs yield byte-identical output.
- Golden-image regression: mean absolute alpha difference against stored references stays below a small tolerance (for example 0.5 %).
- Offline test: run with the network blocked; it must pass.
- Provider test: the active provider is reported correctly.

**Release gate.** Block a release if IoU or boundary F-score on your test set drops by more than 1 point versus the previous release, or if any p95 timing regresses by more than 15 %.

## 13. Fine-tuning (only if needed)

Fine-tune only when a narrow domain (jewellery, car photos, product shots) fails consistently after you have tried a better model, the two-pass crop and matting.

1. **Data.** As a rule of thumb, 300 to 2,000 image-and-mask pairs are enough to adapt a pretrained model; training from scratch needs far more and is not recommended. Expand the set synthetically: cut out foregrounds with high-quality masks and composite them over diverse backgrounds with random scale, rotation, blur and colour jitter.
2. **Method.** Use the model’s official training repository (BiRefNet, DIS) instead of writing your own. Start from pretrained weights; train first with the backbone frozen, then unfreeze with a low learning rate (1e-5 to 1e-4, AdamW).
3. **Loss and augmentation.** BCE + IoU (+ SSIM) loss; horizontal flip, random scale and crop, colour jitter.
4. **Validation.** Hold out 10 to 15 % of the data, monitor MAE and boundary F-score, stop early.
5. **Release.** Export to ONNX, run the parity check (section 6.2), then the complete evaluation (section 12), including the general test set, to confirm that general behaviour did not regress.

## 14. Security, privacy and licensing

**Privacy**

- No telemetry, no analytics, no update checks.
- Models are downloaded only through the explicit `bgremove models pull` command, with SHA-256 verification. Setting `BGREMOVE_OFFLINE=1` blocks all network use.
- Metadata is stripped from outputs by default.

**Input and runtime safety**

- Enforce byte-size and pixel caps; protect against decompression bombs.
- Never load pickle or .pth files from untrusted sources; use ONNX or safetensors.
- Write only inside the chosen output directory and sanitise file names to prevent path traversal.
- The API binds to localhost by default; if you expose it, put it behind authentication and a reverse proxy.

**Licensing checklist** (this is not legal advice)

1. Choose a licence for your own code.
2. Record each model’s licence and commercial-use status in MODELS.md, and block non-commercial models unless the user passes `--allow-noncommercial`.
3. Record dataset licences if you fine-tune; trained weights may inherit restrictions.
4. Keep required attribution notices in a NOTICE file.
5. Re-check licences whenever you update a model version.

## 15. Packaging and distribution

- **Python package:** `pyproject.toml` with extras `[gpu]`, `[api]`, `[gui]`, `[heic]`, `[matting]` and a console script named `bgremove`.
- **Docker:** a CPU image based on `python:3.12-slim` and a GPU image based on an NVIDIA CUDA base with onnxruntime-gpu; models mounted as a read-only volume; run as a non-root user; health check on `/v1/health`.
- **Desktop build:** a PyInstaller one-folder build per OS; bundle the default model, or pull it on first run with checksum verification.
- **Model cache:** the `platformdirs` user cache directory, for example `~/.cache/bgremove/models` on Linux.
- **Versioning:** SemVer, a changelog and a pinned dependency lockfile.

## 16. Project structure

```
bgremove/
├─ pyproject.toml
├─ README.md
├─ MODELS.md                 # models, hashes, licences
├─ NOTICE
├─ src/bgremove/
│  ├─ __init__.py
│  ├─ config.py              # settings, env vars, paths
│  ├─ registry.py            # model configs, hash check, licence gate
│  ├─ loader.py
│  ├─ preprocess.py
│  ├─ engine.py              # ONNX Runtime session management
│  ├─ postprocess.py
│  ├─ refine.py              # cleanup, guided filter, matting
│  ├─ compose.py
│  ├─ export.py
│  ├─ remover.py             # orchestration and timings
│  ├─ cli.py
│  └─ api.py
├─ models/                   # git-ignored
├─ tests/
│  ├─ data/                  # small fixtures and golden images
│  └─ test_*.py
├─ benchmarks/
├─ docker/
└─ .github/workflows/ci.yml
```

## 17. Roadmap and acceptance criteria

| Phase | Scope | Done when |
| --- | --- | --- |
| 0. Spike (1 day) | Run the existing rembg CLI on 20 of your images with 3 models | You know your quality bar and have picked default models |
| 1. Core (about 1 week) | Loader to export, one model, CLI, PNG output, unit tests | FR-01, FR-02 and FR-09 pass; the offline test passes |
| 2. Quality | Registry and profiles, refinement, matting, batch mode, two-pass crop, benchmark and evaluation scripts | The release gate (section 12) is automated |
| 3. Interfaces | REST API, Docker, GUI | NFR-01 to NFR-06 verified on all three operating systems |
| 4. Advanced | SAM 2 interactive mode, video, fine-tuning | Per-feature acceptance tests pass |

## 18. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Mask inverted, or the whole image is kept | Wrong output index, or logits not passed through sigmoid | Print the raw min and max; check `output_index` |
| Mask misaligned or image rotated | EXIF orientation not applied before inference | Apply `exif_transpose` first (7.1) |
| Light or dark halo around the subject | Old background colour bleeding into edge pixels | Edge shift of -1 to -3, foreground estimation, matting |
| Hair looks blocky or binary | Thresholding, or a low-resolution mask | Keep soft alpha; guided filter; matting |
| Runs on CPU despite a GPU | Both onnxruntime and onnxruntime-gpu installed, or CUDA/cuDNN mismatch | Uninstall both, reinstall one; check `get_available_providers()` |
| GPU out of memory | Model too large for the VRAM | fp16 model, smaller model, or CPU fallback |
| First image is very slow | Session creation and kernel warm-up | Warm up at startup; keep the process alive |
| Output differs from PyTorch | Wrong normalisation or interpolation | Run the parity check; compare tensors stage by stage |
| Wrong colours in the output | ICC, CMYK or 16-bit input not handled | Follow the colour rules in 7.1 |
| Small subject lost or rough | Subject covers few pixels at model resolution | Two-pass crop (section 8) |

## 19. Reference implementation (core path)

A minimal working skeleton of stages 1 to 6. Adapt the constants to your model config, and check which output index and activation your model needs.

```python
import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps

MODEL = "models/isnet-general-use.onnx"  # example file; use your registry entry
SIZE = (1024, 1024)
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


def make_session(path):
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    wanted = [
        "CUDAExecutionProvider",
        "CoreMLExecutionProvider",
        "DmlExecutionProvider",
        "CPUExecutionProvider",
    ]
    avail = ort.get_available_providers()
    return ort.InferenceSession(path, so, providers=[p for p in wanted if p in avail])


def load(path):
    im = ImageOps.exif_transpose(Image.open(path))
    return im.convert("RGB")


def preprocess(im):
    x = cv2.resize(np.asarray(im), SIZE, interpolation=cv2.INTER_LINEAR)
    x = (x.astype(np.float32) / 255.0 - MEAN) / STD
    return x.transpose(2, 0, 1)[None]  # 1 x 3 x H x W


def predict_mask(sess, im):
    name = sess.get_inputs()[0].name
    raw = sess.run(None, {name: preprocess(im)})[0]  # pick the right output index
    m = raw.squeeze().astype(np.float32)
    if m.min() < 0.0 or m.max() > 1.0:  # logits -> probabilities
        m = 1.0 / (1.0 + np.exp(-np.clip(m, -50, 50)))
    m = (m - m.min()) / (m.max() - m.min() + 1e-8)  # optional min-max stretch
    m = cv2.resize(m, im.size, interpolation=cv2.INTER_CUBIC)  # im.size is (W, H)
    return np.clip(m, 0.0, 1.0)


def cut_out(path, out_path):
    sess = make_session(MODEL)  # in real code: create once, reuse
    im = load(path)
    alpha = (predict_mask(sess, im) * 255).round().astype(np.uint8)
    rgba = np.dstack([np.asarray(im), alpha])
    Image.fromarray(rgba).save(out_path, compress_level=6)


if __name__ == "__main__":
    cut_out("input.jpg", "output.png")
```

## 20. Master prompt for an AI coding assistant

Paste the block below into a coding assistant (Claude Code or similar) together with this document.

```
ROLE
You are a senior Python engineer building an offline background-removal tool.

OBJECTIVE
Implement the project described in the attached specification book,
phase by phase, starting with Phase 1 (core library + CLI).

HARD CONSTRAINTS
- Python 3.11+, type hints everywhere, ruff and mypy clean.
- Inference via ONNX Runtime only. No YOLO. No network access in the inference path.
- All model-specific constants (input size, mean, std, output index, activation)
  live in a registry file, never in code.
- Pipeline stages are pure functions (numpy in, numpy out), one module per stage
  as listed in section 16.
- Output keeps original resolution, orientation and ICC profile;
  metadata is stripped by default.
- Default models must be safe for commercial use; non-commercial models are gated
  behind --allow-noncommercial.

WORKFLOW
1. Restate the plan and list your assumptions before writing code.
2. Create the project skeleton and pyproject.toml.
3. Implement loader, preprocess, engine, postprocess, compose, export,
   remover and CLI.
4. After each module, write pytest tests covering the cases in section 12.
5. Add the benchmark script and save results as JSON.
6. Stop at the end of each phase and report: what was built, test results and
   open questions. Do not start the next phase without confirmation.

QUALITY GATES
- All automated tests from section 12 pass, including the offline test.
- The ONNX-versus-PyTorch parity check passes for every model added.
- Show before/after results for 5 of my test images.

WHEN UNSURE
Ask one concise question rather than guessing, especially about model
licences, output index, or the normalisation recipe.
```
