# Background model optimization and training workflow

Prepared 19 October 2026, Africa/Tunis. The user confirmed that no training dataset
is available yet and requested preparation of the workflow.

The runtime optimization work and this training workflow solve different parts of
the resource problem. Runtime policies can reduce allocations, concurrency and
retained memory immediately. Further training can improve a small model for the
photos the app actually handles. Fine-tuning the same architecture does not itself
make its tensors or intermediate activations smaller.

**No weights have been retrained in this work.** There is no reviewed training
dataset or original trainable checkpoint in the application workspace. The four
installed files are inference ONNX artifacts. This directory adds an opt-in,
resource-guarded U2NETP development workflow without adding PyTorch to the app.

## What each technique changes

| Technique | Intended effect | Quality validation needed | Current status |
|---|---|---|---|
| Thread limits, sequential work, session lifetime, selected-output inference | Less CPU pressure and memory retained by the runtime | Output equivalence and real-image checks | See the runtime changes and measurements in `BACKGROUND_MODELS.md` |
| Reduced input resolution | Smaller intermediate tensors, usually faster inference | Fine detail, hair and transparent edges may degrade | Only use profiles that explicitly support the shape; do not resize a fixed ONNX graph blindly |
| INT8/FP16 conversion | Smaller weights and potentially smaller/faster operations | Operator/provider compatibility plus a representative held-out dataset | An experiment until it passes quality and memory gates; file size alone proves neither |
| U2NETP fine-tuning | Adapt the existing Fast architecture to target photos | Independent subject-group test split | Implemented as an optional workflow; not run |
| Distillation into U2NETP | Transfer some stronger-model behavior to a much smaller student | Human-reviewed labels plus independent ground truth | Future extension; teacher predictions are not accepted as ground truth automatically |
| Full BiRefNet fine-tuning | Adapt a high-capacity model | The same release tests, with much larger training resources | Not prepared for this 16 GB laptop; it does not meet the lightweight goal |

U2NETP is the small variant provided by the original project, which supplies
trainable `.pth` checkpoints and a PyTorch training example. The workflow below
loads its architecture from an explicit local upstream checkout and its weights
from an explicit local checkpoint. [Original project](https://github.com/xuebinqin/U-2-Net),
[training example](https://github.com/xuebinqin/U-2-Net/blob/ac7e1c817ecab7c7dff5ce6b1abba61cd213ff29/u2net_train.py).

The BiRefNet authors report much larger training-memory requirements than the
installed laptop can supply. Their GPU measurements also do not establish this
app's CPU memory usage. Choosing the small architecture and testing it locally is
the practical direction here. [Official BiRefNet repository](https://github.com/ZhengPeng7/BiRefNet).

## Dataset contract

Create a dataset folder under `training/data/` with this layout:

```text
training/data/my-collection/
  pairs.json
  images/001.jpg
  images/002.jpg
  masks/001.png
  masks/002.png
  ...
```

Copy `training/manifest.example.json` to `pairs.json` and replace its entries.
The example references missing files intentionally; it is a schema example, not
a supplied dataset. At least three independent groups are needed to exercise the
pipeline. Three groups are far too few to establish useful model quality.

Each source requires a separate, aligned grayscale alpha mask: black background,
white foreground, intermediate values for partial transparency. Accepted masks
are 8-bit grayscale, 16-bit grayscale, or float alpha in `[0, 1]`. RGB/RGBA masks
are rejected to avoid interpreting white RGB pixels as foreground when the real
annotation is in an alpha channel. Extract that channel deliberately before
preparing the manifest. Images and masks must have equal dimensions after EXIF
orientation, contain one frame, and be at most 24 million pixels each.

Each sample has a unique `id` and a `group`. Use the same group for the same
person, object, photo burst, capture session, or derivative crops that must remain
together. Exact decoded-image duplicates across different groups are rejected.
The validator cannot recognize different photos of the same person; correct
grouping is an annotation responsibility.

The provenance object records the source collection, training/distribution rights,
annotation process, and the explicit `human-reviewed` ground-truth attestation.
This is a recorded declaration, not automatic proof of label quality or rights.
Review hair, fingers, glasses, fine product edges, holes, transparent material,
dark subjects and low-contrast backgrounds. Keep all generated cutouts and raw
teacher/Fast predictions outside the reviewed ground-truth collection until a
person has checked and corrected them. Test masks must be independently reviewed.

No personal images are uploaded. Dataset and checkpoint directories are ignored
by Git. Keep the source files unchanged after preparation: their SHA-256 checks
are verified again before training and evaluation.

## Prepare and validate without PyTorch

Run from the repository root. This command works with the current app environment
and performs no inference or training:

```powershell
.\venv\Scripts\python.exe -m training.dataset training/data/my-collection/pairs.json --output training/data/my-collection/prepared.json
```

The output uses deterministic subject/capture-group splits: approximately 70%
training, 15% validation and 15% test **by groups**, with at least one group in
each split. Sample proportions can differ when group sizes differ. `--seed`,
`--validation` and `--test` are explicit options. Input ordering does not alter
the split. The prepared schema is version 2: its fingerprint binds source/mask
hashes, IDs/groups, actual train/validation/test membership, seed, split policy
and provenance. A content-only fingerprint is stored separately. Loading a prepared
file verifies its deterministic policy against actual group membership; swapping
whole split lists, editing the policy or reusing a different seed is detected.
Older prepared files must be generated again rather than accepted as equivalent.
Source files are not modified and existing prepared output is never
overwritten. All-foreground/background masks produce visible warnings for review.

The test split is excluded from optimizer updates and checkpoint selection.
Validation at 320 pixels selects the best candidate checkpoint. Final testing
uses original-size images and the production Fast preprocessing/postprocessing.

## Separate development environment

Use a dedicated Python 3.11 or 3.12 installation; do not install the training stack
into the application's `venv`. These commands are setup instructions and were
not executed during the optimization work:

```powershell
py -3.11 -m venv training/.venv
.\training\.venv\Scripts\python.exe -m pip install -r training/requirements.txt
```

Install a compatible PyTorch 2.6-or-later build into that environment using the
[official PyTorch selector](https://pytorch.org/get-started/locally/). Choose
Windows/Pip/CPU for the default CPU workflow, or the correct CUDA build only when
GPU training is intended. Only `torch` is needed by these scripts; the original
project's old full requirements list is not used. CUDA selection for training
does not install a GPU provider into the desktop app. After the first successful
end-to-end run, record the exact environment with `pip freeze` beside its run
reports before repeating or distributing results.

Obtain the original architecture explicitly:

```powershell
git clone https://github.com/xuebinqin/U-2-Net.git training/upstream/U-2-Net
git -C training/upstream/U-2-Net checkout ac7e1c817ecab7c7dff5ce6b1abba61cd213ff29
```

Obtain the upstream **U2NETP** `.pth` state dictionary from the links in the
[original README](https://github.com/xuebinqin/U-2-Net#usage-for-salient-object-detection)
and place it at `training/checkpoints/u2netp.pth`. Verify its provenance and rights;
the tools do not download a checkpoint or convert the installed ONNX file back
to a trainable model. The upstream source commit and file cleanliness are checked,
and source/checkpoint hashes are recorded in each report. Weights load with
`weights_only=True`; there is no fallback to loading arbitrary pickled model
objects. [PyTorch serialization guidance](https://docs.pytorch.org/docs/stable/notes/serialization.html).

## Guarded fine-tuning

```powershell
.\training\.venv\Scripts\python.exe -m training.finetune_u2netp --dataset training/data/my-collection/prepared.json --upstream training/upstream/U-2-Net --checkpoint training/checkpoints/u2netp.pth --output training/runs/portrait-pilot
```

Defaults deliberately start small: CPU, two compute threads, batch size one,
zero data-loader workers, 320x320 inputs, four-step gradient accumulation, learning
rate `0.00001`, at most five epochs/500 samples, and early stopping after two
non-improving validation epochs. Each image is decoded when used; the dataset is
not preloaded into RAM. Horizontal flips are applied to image and mask together.
The seven supervised U2NETP probability outputs use averaged binary cross-entropy.
Gradients are clipped and short accumulation windows are normalized correctly.

The parent process samples the owned worker tree every 100 ms and stops it at
2.5 GiB tree RSS, less than 1.5 GiB system memory remaining, or 30 minutes. These
are observed thresholds, not OS-enforced allocation caps; a short spike between
samples can be missed. The guard kills only its own worker tree. It writes
`resource_report.json` and `worker.log`; interruption leaves an incomplete run,
not an automatically accepted model. The best state dictionary is saved atomically
as `best.pth`. Epoch logs and provenance go into `history.json` and
`training_report.json`. The completed report binds the best checkpoint SHA-256
to the exact prepared fingerprint and individual split fingerprints. New output
directories are required.

Guard thresholds can be set with `--max-rss-gib`, `--min-free-gib` and
`--timeout-seconds`; increase them only after reviewing local resource evidence.
CPU time is bounded by thread and duration limits rather than a CPU-percentage
cap. `--device cuda` explicitly selects CUDA and limits PyTorch's allocator to
half the GPU memory; there is no automatic fallback or promise it will fit the
RTX 3050. Larger runs belong on appropriate development hardware, outside the app.

## Export and verify a candidate

```powershell
.\training\.venv\Scripts\python.exe -m training.export_u2netp --upstream training/upstream/U-2-Net --checkpoint training/runs/portrait-pilot/best.pth --training-report training/runs/portrait-pilot/training_report.json --output training/runs/portrait-export
```

The exporter uses the existing architecture's fused mask only, fixed
`1x3x320x320` FP32 input and opset 17. It checks the ONNX graph and compares
PyTorch/ONNX CPU outputs on three seeded random tensors with `1e-4` absolute and
relative tolerances. Random-tensor agreement checks export correctness; it does
not establish photo quality. Export runs under the same resource guard and emits
`candidate.onnx`, a separate `registry.json`, a copy of `training_report.json`,
and `export_report.json`. A completed training report matching the checkpoint is
required before PyTorch is loaded. The export report preserves the split lineage
and binds the training-report, checkpoint and ONNX hashes together.
[PyTorch ONNX API](https://docs.pytorch.org/docs/stable/onnx.html).

The candidate registry retains Fast's RGB/max-value normalization and min/max
mask postprocessing. Its rights remain marked unverified until the upstream
checkpoint and dataset terms have been checked. This is a development artifact;
the production registry and installed model cache are untouched.

## Independent test evaluation

Evaluate the installed Fast baseline and exported candidate separately with the
same interpreter, subject-group test split, two CPU threads and refinement
settings. These commands require no PyTorch and can use the application venv:

```powershell
.\venv\Scripts\python.exe -m training.evaluate_candidate --dataset training/data/my-collection/prepared.json --output training/runs/test-baseline
.\venv\Scripts\python.exe -m training.evaluate_candidate --dataset training/data/my-collection/prepared.json --registry training/runs/portrait-export/registry.json --export-report training/runs/portrait-export/export_report.json --models-dir training/runs/portrait-export --output training/runs/test-candidate
.\venv\Scripts\python.exe -m bgremove.cli gate training/runs/test-baseline/evaluation_report.json training/runs/test-candidate/evaluation_report.json --output training/runs/gate.json
```

Candidate evaluation requires the export report and its copied training report.
Before importing the model runtime, it checks the candidate hash and exact
prepared/split lineage. A candidate trained with a different split or seed is
refused, even if every source image is identical. The upstream installed baseline
has no local training lineage; its evaluation report records that explicitly.
This is reproducibility and accidental-leakage protection, not cryptographic
proof that a manually falsified training report describes a real training run.

The evaluator generates original-size masks, a prediction/ground-truth manifest,
IoU, MAE, F1, boundary F-score and alpha-error metrics, plus per-stage median/p95
pipeline timings. The existing backend gate rejects more than a one-percentage-
point IoU/boundary drop or a 15% p95 regression and rejects mismatched coverage.
It is a regression gate; passing it does not prove improvement.

Require these additional promotion conditions before changing a bundled profile:

1. A separate, representative test collection with enough independent subjects;
   a suggested first release target is at least 100 held-out photos spanning
   portraits and non-portraits, chosen before viewing candidate test results.
2. Visual review of edge/alpha failure cases and per-category metrics; the small
   model must improve the intended use case without unacceptable general regressions.
3. Candidate `resource_report.json` peak tree RSS below the chosen app memory
   budget and no higher than its matched baseline. Repeat cold/warm runs and
   large-photo runs; one held-out pass is insufficient to estimate worst-case RAM.
4. Successful export checks, source preservation, full-resolution alpha copying,
   frozen-executable inference, and the focused app/backend test suites.
5. Recorded dataset/checkpoint rights, exact training environment, source commit,
   checkpoint/ONNX hashes, test split and before/after reports. Register a new
   immutable candidate artifact, retaining the original for rollback.

If no candidate satisfies the chosen memory and quality budget, retain Fast and
continue data/model work. Do not silently substitute a weaker model while showing
the Quality or Portrait name.

## Distillation next

For a later student experiment, run a stronger teacher offline on development
hardware, store its soft predictions separately, and combine them with corrected
human annotations during student training. Keep subject grouping and independent
test masks unchanged. Teacher predictions can be a training signal; they cannot
establish the student's ground-truth accuracy. The current scripts implement
supervised U2NETP fine-tuning only, so there is no hidden large teacher session or
distillation loss in their training loop.

## Verification completed here

- 32 dataset/tooling tests passed, including deterministic group splits, duplicate
  pixel leakage, path containment, shape/mask errors, changed files and refused
  output overwrites, entire train/test split swaps, seed changes, policy edits,
  checkpoint/report mismatches and candidate evaluation refused before model imports.
- All training scripts compile; help commands work. A subprocess test confirms
  importing fine-tuning/export/evaluation entry points does not import PyTorch.
- Tests use synthetic fixtures exclusively to exercise validation. They do not
  measure segmentation accuracy and are not supplied as a training dataset.
- Real training, checkpoint loading, ONNX export and held-out evaluation are
  pending a reviewed dataset, a trusted `.pth` checkpoint and a separately
  provisioned training environment. No training-quality or RAM-improvement claim
  follows from these tooling checks.
