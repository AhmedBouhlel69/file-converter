# Background model readiness and verification

Updated 19 October 2026, Africa/Tunis. This continues the model work after the
[full GUI report](GUI_REPORT.html). Installation, startup readiness and successful
inference are separate states.

The later [runtime optimization report](RUNTIME_OPTIMIZATION.md) records the
adopted lower-memory session policy and before/after measurements. The
[training workflow](TRAINING_AND_OPTIMIZATION.md) is prepared separately; no
weights have been retrained without a reviewed dataset.

## Current results

| Profile | Local file verification | Real-image inference evidence |
| --- | --- | --- |
| Fast / U²-NetP | Size and pinned SHA-256 pass | Passed previously in GUI/frozen app; passed again through the new guarded runner. |
| Balanced / IS-Net | Size and pinned SHA-256 pass | Also passed the optimized CPU check at about 702 MiB peak owned-tree RSS; exported pixels exactly matched the earlier reference. |
| Quality / BiRefNet general | Size and pinned SHA-256 pass | Still resource-blocked; successful inference is unverified. |
| Portrait / BiRefNet portrait | Size and pinned SHA-256 pass | Still resource-blocked; successful inference is unverified. |

All four registered files are installed, totaling 2,128,556,701 bytes (about
1.98 GiB). There are no further registered profiles waiting to be downloaded.
The remaining work is successful Quality/Portrait inference under sufficient
resources. During this continuation, approximately 3.6 GiB RAM was free on the
15.42 GiB system. Available RAM changes with other running applications.

The app requires at least **8 GiB available physical RAM** before initializing
registered CPU models of 500,000,000 bytes or larger. Quality and Portrait meet
that size condition. This is an app startup policy, not an upstream hardware
minimum, a memory reservation or a guarantee that every inference will finish.
The installed ONNX runtime exposes CPU/Azure providers; the app uses CPU.

## Check readiness without loading a model

Run from the repository root in PowerShell:

```powershell
.\venv\Scripts\bgremove.exe models check
.\venv\Scripts\bgremove.exe models check --json
.\venv\Scripts\bgremove.exe models check portrait --json
```

This command checks registered files, exact sizes, SHA-256, commercial-use policy,
CPU provider availability and current memory. It creates no ONNX sessions, runs
no warmup/inference, downloads nothing and changes no model weights. It reports
the actual cache/file paths selected in that process; `--model-dir` and
`--registry` can select explicit locations. `--allow-noncommercial` applies to
custom registries requiring that acknowledgment.

Each JSON profile has an installed/verified state, `cpu_ready`, status, reason
and memory requirement. The top-level `inference_tested` is always false because
readiness is not a real processing test. A zero startup memory threshold for
Fast/Balanced means no additional threshold is configured; it does not mean zero
memory use.

| Exit code | Meaning |
| --- | --- |
| 0 | All selected profiles pass artifact and CPU startup checks. |
| 2 | Invalid profile or command arguments. |
| 3 | Unusable/missing/corrupt artifact, registry, licence policy or CPU provider. |
| 5 | Verified files exist, but at least one selected profile lacks startup RAM. |

Artifact/provider failures take precedence over resource blocks. Human output
and JSON explicitly distinguish readiness from successful inference.

## Run a guarded real-image check

The reusable [verification tool](../tools/verify_background_models.py) runs one
CPU model at a time in its own process. Without `--run`, it only checks readiness:

```powershell
.\venv\Scripts\python.exe tools/verify_background_models.py
```

To test the two remaining profiles when enough RAM is free:

```powershell
.\venv\Scripts\python.exe tools/verify_background_models.py `
  --profile quality --profile portrait --run `
  --input backgroundG/artifacts/demo/input/horse.jpg
```

To use an acceptance image, replace `--input` with its path. The bundled horse
example is a functional smoke image, not a portrait-quality benchmark.

Each profile is rechecked immediately before launch. Resource-blocked profiles
are recorded with `child_launched: false` and `inference_tested: false`; the
runner exits 5 without starting their inference. It never bypasses the app's
8 GiB policy. After closing other memory-heavy applications, run the readiness
command again before retrying. A suitable machine with more free RAM is also a
valid way to complete these tests.

For an eligible run, the default diagnostic limits are **1 GiB free system RAM**,
**8 GiB combined RSS for the owned process tree**, and **180 seconds per model**.
The parent samples at 100 ms intervals and stops only its own child/descendants
when a limit is exceeded or the test is interrupted. Sampling is not an OS hard
memory cap and cannot guarantee zero transient pressure. The diagnostic limits
can be changed with `--min-free-gib`, `--max-rss-gib` and `--timeout`; they do not
lower the production startup requirement. Tests use two ONNX threads by default
(`--threads`), which also matches the app's new default.

The child uses the original registered model on CPU, initializes its session,
removes the real image's background, writes a fresh PNG and grayscale mask,
decodes both outputs, reports dimensions/alpha/timings and verifies the source
SHA-256 is unchanged. The source is never an output destination. Unique report
folders preserve logs and any partial artifacts without overwriting earlier
checks. Successful processing does not measure segmentation quality across an
acceptance set.

Reports are saved under `scratch/model-verification/run-*/report.json` by default;
use `--report-dir` to change the parent folder. Exit codes are 0 for successful
selected checks, 1 for a failed/guard-stopped processing test, 2 for invalid
arguments or I/O, 3 for unusable model/provider, 5 for resource deferral and 130
for user interruption. Source diagnostics use the project virtual environment;
the previously built executable does not expose this new diagnostic command.

## Evidence from this continuation

- The latest complete background-library suite passed **293 tests, with 3 skipped**.
  Readiness, guarded-runner lifecycle and runtime-resource cases are included
  in that total. **110 focused app tests** also passed, including batch cleanup,
  resource concurrency and clipboard behavior. Earlier GUI/application results remain separately
  described in the [technical report](TECHNICAL_REPORT.md).
- Before the later session-policy optimization, the new guarded Fast check passed on the 770×595 horse image: RGBA PNG, alpha
  0–255, matching mask and unchanged source. Warmup was 0.864 seconds; real
  inference was 0.294 seconds, using two CPU threads. Peak interpreter RSS was
  about 558 MiB; full owned-tree RSS about 569 MiB. No guard triggered.
  [Fast evidence](../scratch/model-verification/run-eic2ux2o/report.json).
- A requested Quality/Portrait run verified both files, recorded insufficient
  RAM and launched neither child. This validates correct deferral, not their
  inference or segmentation quality.
  [Quality/Portrait deferral evidence](../scratch/model-verification/run-wrrbgjvl/report.json).

The detailed previous memory trials, model provenance and installation evidence
are in the [technical report](TECHNICAL_REPORT.md) and [model registry guide](../backgroundG/MODELS.md).
