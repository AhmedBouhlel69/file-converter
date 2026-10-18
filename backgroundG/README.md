# Local background remover

An offline ONNX background remover with a Python API and CLI. Phase 2 adds model
installation, refinement, recursive batches, composition, benchmarks and release
comparison. REST and GUI interfaces are reserved for Phase 3.

## Try it in this workspace

The verified `fast` model is installed locally. Run from the project folder:

```powershell
.\.venv\Scripts\bgremove photo.jpg -o output --model fast
.\.venv\Scripts\bgremove --help
.\.venv\Scripts\bgremove remove --help
```

Five public U-2-Net examples were processed offline. Open
`artifacts/demo/comparison.png` for a before/after sheet or `artifacts/demo/output`
for the actual RGBA PNGs and masks. These samples are a functional smoke check,
not the user's own acceptance set or measured quality evidence. Their source and
usage notes are in `artifacts/demo/SOURCE.md`; they are excluded from source control.

## Install elsewhere

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\bgremove models list
.\.venv\Scripts\bgremove models pull fast
.\.venv\Scripts\bgremove models verify fast
```

Only the explicit `models pull` command downloads files. Inference never downloads
weights, contacts servers or sends images anywhere. `BGREMOVE_OFFLINE=1` blocks
model downloads. Model files are checked against a registered SHA-256 before use.

Available profiles: `fast` (4.57 MB U2netp), `balanced` (178.65 MB IS-Net; default),
`quality` and `portrait` (972.67 MB BiRefNet each). Larger weights are registered
but have not been downloaded or tested here. See [MODELS.md](MODELS.md) for the
exact exports, licences, hashes, normalization and validation limits. To use the
default, install it explicitly with `bgremove models pull balanced` first.

The cache is chosen by platformdirs; override with `BGREMOVE_MODEL_DIR` or
`--model-dir`. Use `--registry path.json` for a custom registry. Its input sizes
are `[width, height]`. Custom non-commercial or unverified profiles require
`--allow-noncommercial`; a missing checksum always blocks usage.

## Batch processing and refinement

```powershell
bgremove photos -o cutouts --model fast --recursive --jobs 2 --device cpu --save-mask --skip-existing
bgremove photo.jpg -o output --model fast --two-pass --edge-shift -1 --feather 0.8 --guided-radius 8
bgremove photo.jpg -o output --model fast --bg-color '#ffffff' --shadow --crop --padding 20 --aspect 1
bgremove photo.jpg -o output --model fast --format webp --bg-image background.jpg
```

Use the environment's `bgremove` path or activate `.venv` for these examples.
Folders preserve relative subdirectories. Conflicting output names fail before
processing; use separate output folders for unrelated input roots with the same
relative names. Resume checks every requested file: an existing image can be kept
while a missing mask is created. Existing files require `--skip-existing` or
`--overwrite`. CPU parallelism uses processes, with jobs × threads limited to
physical cores. GPU processing uses one worker and serializes session access.

Soft alpha is retained by default. Small-component/hole cleanup defaults to
`--min-blob-ratio 0.001`; set it to 0 to disable. Threshold, feather, edge shift,
guided filtering, and two-pass crop are opt-in. Two-pass mode predicts a subject
box with a 10% margin, reruns inference on that crop, then restores the full-size
mask. Small subjects can still be missed by the initial prediction.

`--bg-color`, `--bg-image`, and `--bg-blur` are mutually exclusive. `--aspect 1`
pads to a square. Default image and mask dimensions match the oriented input;
explicit `--crop` and `--aspect` change the image canvas, while saved masks always
keep input dimensions. Input alpha is ignored for inference. ICC is preserved;
EXIF/GPS is stripped unless `--keep-metadata` is supplied. RGB input files keep
their original RGB colour space; CMYK with an ICC profile is converted to sRGB.

PNG is the default output; WebP is lossless. `--save-mask` writes an 8-bit PNG;
`--mask-only` skips the composed image. Output publication is atomic and protects
existing files. It requires hard-link support for the no-overwrite path.

For optional alpha matting:

```powershell
.\.venv\Scripts\python -m pip install -e ".[matting]"
bgremove photo.jpg -o output --model fast --matting
```

Matting works on at most 4 MP and estimates clean foreground colour before
upsampling. It is CPU-heavy and needs confident foreground/background seeds.
Its estimators were mocked in automated tests because the extra is not installed
in this workspace; real solver validation is still outstanding.

## Python API

```python
from bgremove import ComposeOptions, RefineOptions, Remover

remover = Remover(model="fast", device="cpu")
result = remover.remove(
    "photo.jpg",
    refinement=RefineOptions(edge_shift=-1, feather_sigma=0.8),
    composition=ComposeOptions(crop=True, padding=20),
    two_pass=True,
)
result.save("photo_nobg.png")
result.save_mask("photo_mask.png")
print(result.provider, result.timings)
```

`result.rgba` is a Pillow RGBA image; `result.mask` is full-resolution float32
alpha in [0,1]. Use `Result.save` for metadata policy and overwrite protection.
`remove(..., matting=True)` is shorthand for enabling matting in refinement.

## Quality and performance

```powershell
bgremove bench photo.jpg -o timings.json --model fast --device cpu
bgremove evaluate manifest.json -o candidate.json --benchmark timings.json
bgremove gate baseline.json candidate.json --output gate.json
```

Benchmark defaults are three warmups and 20 timed runs at 1, 12 and 24 MP, with
per-stage median/p95, actual provider and sampled process RSS. VRAM is recorded
as unavailable. A full CPU run is saved in `artifacts/benchmarks/fast-cpu.json`.
See [benchmarks/README.md](benchmarks/README.md) for the ground-truth manifest,
metrics and comparable baseline requirements. The gate fails if IoU or boundary
F-score drops more than one point, or any stage p95 regresses by over 15%; it
also rejects incomplete or incompatible reports. A manual GitHub Actions workflow
runs the same gate against supplied repository reports.

## Development and acceptance status

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy src
```

`requirements-dev.lock` records the installed Windows/Python 3.14 development
packages. It is an environment snapshot, not a cross-platform resolver lock.
CI targets Python 3.11 and 3.12 on Windows, Linux and macOS; only this local
Windows run has been executed here.

Phase 2 implementation is present. Release acceptance still needs the user's
100-image labelled dataset, actual PyTorch/ONNX parity per export, validation of
the larger profiles and optional matting solver, GPU/platform measurements and
OS-level network isolation. The socket-blocked test and public example smoke
check do not replace those checks. No quality target or release readiness is
claimed from synthetic fixtures.
