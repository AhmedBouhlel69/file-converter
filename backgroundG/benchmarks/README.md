# Offline quality and timing reports

Use a verified, locally installed model. No benchmark or evaluation command downloads
weights or datasets. Reports from synthetic models or generated images validate the
tooling only; they do not establish real-photo quality or release readiness.

```powershell
.\.venv\Scripts\python benchmarks/benchmark.py photo.jpg --registry registry.json --model-dir models --output timings.json
```

Defaults: 3 warmups and 20 measured runs **per size**, at 1, 12 and 24 megapixels.
`--sizes 1 12 24`, `--runs` and `--warmups` are configurable. Omitting `photo.jpg`
generates an RGB gradient. Source aspect ratio is preserved; dimensions are rounded
to whole pixels. Each resized input is encoded to JPEG at quality 95 outside the
measurement, then read from disk by the pipeline. PNG export is timed on every run,
including warmups. This measures each stage's median and p95 in seconds, plus total
wall-clock duration. PNG/JPEG compression costs depend on image content.

The report contains the actual provider, OS, CPU, Python and ONNX Runtime versions,
requested runtime options, plus a `sizes` object. Its process peak RSS is sampled every 5 ms through optional
`psutil`; it includes native allocations and pre-existing process memory, and can
miss short peaks. Without the sampler RSS is `null` with a reason. VRAM is `null`
because no portable per-process GPU sampler is configured. The input is subject to
the normal byte/pixel limits. Input preparation and model construction are excluded.

## Evaluation manifest

Create a JSON object with explicit mask pairs. Paths are relative to the manifest;
`image` and `id` are optional. If provided, image dimensions are checked after EXIF
orientation. Ground-truth masks should already match that oriented image.

```json
{
  "profile": "balanced",
  "samples": [
    {"id": "portrait-1", "image": "photos/1.jpg", "prediction": "pred/1.png", "ground_truth": "truth/1.png"}
  ]
}
```

```python
import json
from bgremove.evaluation import evaluate_manifest

quality = evaluate_manifest("manifest.json", matting=True)
with open("quality.json", "w", encoding="utf-8") as stream:
    json.dump(quality, stream, indent=2, allow_nan=False)
```

Mask files use alpha for RGBA/LA, otherwise grayscale. Eight-bit alpha divides by
255 and 16-bit integer masks by 65535; float TIFF masks must already lie in [0, 1].
Predictions and truth must have identical dimensions. RGB foreground cutouts without
alpha are not masks. Segmentation uses threshold 0.5 and reports per-image IoU,
soft-alpha MAE, F1 (`beta=1`) and boundary F-score, then the unweighted mean across
images. Boundary matching uses inner 8-connected boundaries and a 2-pixel Euclidean
tolerance, configurable in the API. Two empty masks have IoU/F1/boundary score 1;
one empty boundary against one nonempty boundary scores 0.

Optional matting metrics are SAD (`sum(abs(alpha error))/1000`), MSE and gradient
error (`sum(squared gradient-magnitude error)/1000`, sampled Gaussian derivatives,
sigma 1.4). Connectivity error is explicitly listed as unavailable. These metrics
are a documented local protocol; compare with the same settings and dataset.
Review real-photo results side by side as well, especially hair, transparency and halos.

## Release comparison

Merge quality and timing reports for the same model and test conditions:

```python
from bgremove.evaluation import compare_reports

candidate = {**timings, "metrics": quality["metrics"]}
gate = compare_reports("baseline.json", candidate)
assert gate["passed"], gate["failures"]
```

The gate rejects an IoU or boundary F-score decrease **greater than 0.01 absolute**,
or any stage p95 increase **greater than 15%**. Exactly those limits pass. Timing
stages include export. Missing metrics, empty reports, missing stages/sizes/profiles,
nonfinite/negative values, zero p95 baselines and changed timing units fail with a
reason. Legacy flat `stages: {stage: {median, p95}}` timing summaries are accepted.
For multiple model profiles, wrap merged reports as
`{"profiles": {"fast": {...}, "balanced": {...}, "quality": {...}}}` on both sides.
Evaluation reports fingerprint ground-truth file contents, optional source images and
sample IDs; predictions are excluded and sample ordering does not affect the hash.
When these fields are present, the gate also requires matching dataset identity,
evaluation settings, sample count, dimensions, actual provider, requested runtime
options and CPU information. Changing hardware, providers or evaluation data requires
rerunning the approved baseline under the new conditions. Legacy summaries without
these fields cannot establish those conditions, so keep full merged reports.
Never substitute synthetic measurements for a real-image release baseline.
