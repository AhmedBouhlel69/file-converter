# Background-removal resource optimization

Updated **19 October 2026, Africa/Tunis**. This is an addendum to the
[GUI report](GUI_REPORT.html) and [technical report](TECHNICAL_REPORT.md).
Those reports describe the earlier application snapshot; the runtime changes
below take precedence for session startup, CPU threading and session lifetime.

The Fast profile now uses substantially less inference memory in a controlled
local comparison, while producing exactly the same mask and RGBA pixels on the
test image. Original model files, input resolution, normalization parameters and
model-selection labels remain unchanged. These are runtime optimizations, not
new training or a replacement of Quality/Portrait with another model.

## What changed

| Change | Purpose and practical effect |
| --- | --- |
| Two ONNX CPU threads by default | Limits inference parallelism so a background-removal job leaves more CPU capacity for the desktop. Explicit library/CLI thread overrides remain available. This is a thread-pool setting, not a percentage CPU quota. |
| Sequential ONNX graph execution | Avoids parallel execution of graph branches. Operator work can still use the configured two threads. |
| ONNX worker spinning disabled | Idle inference workers wait instead of polling for the next image. This reduces avoidable idle CPU activity; no battery-life claim is established by this test. |
| CPU memory arena and memory patterns disabled | Avoids retaining large activation allocations between images. Normal tensor-lifetime reuse and graph optimizations remain enabled. Allocation overhead can increase slightly. |
| Only the registered output requested | Requests the actual foreground mask instead of converting every exported auxiliary output to Python arrays. |
| Two synthetic warmup inferences removed | Session initialization still checks input/output metadata. The first actual image performs the first inference, removing two unneeded startup runs. The public `warmup()` method initializes the session; it no longer executes two dummy images. |
| In-place input normalization | Reuses the resized float32 buffer for division, mean subtraction and standard-deviation normalization, reducing temporary arrays. Model preprocessing values and final tensor layout remain the same. |
| Sessions reused within a batch, released afterward | A batch uses one model session. The application releases its session/cache ownership when the batch ends, including error, callback-exception and cancellation paths. A single-image service call also releases ownership in its cleanup path. A caller still using an engine keeps a valid reference; release does not interrupt an active inference. |
| One idle cached model at a time | Switching profiles releases idle previous-model ownership before constructing a replacement. This avoids keeping several heavyweight idle sessions alive. |
| General conversion defaults to at most two workers | Limits the number of simultaneous ordinary conversion jobs. Explicit configuration/CLI worker requests remain supported; separate converters can still allocate their own resources. |
| Convert and Remove Background jobs cannot overlap | The GUI blocks starting either page's processing while the other is running, avoiding an unnecessary combined memory/CPU peak. |

The application continues processing background-removal images serially. The
existing minimum of 8 GiB available physical RAM before starting the registered
Quality/Portrait CPU models remains in place. It is a startup check, not a
reservation or continuous memory cap.

Core implementation is in [engine.py](../backgroundG/src/bgremove/engine.py),
[preprocess.py](../backgroundG/src/bgremove/preprocess.py) and the application's
[background-removal service](../image_converter/core/background_removal.py).

## Measured Fast results

The comparison used the bundled **770 × 595 horse JPEG**, the pinned U²-NetP
ONNX file, CPU execution, two threads and two real-image runs per candidate.
Each candidate ran in a separate owned Python process. The reference used the
previous engine/preprocessing implementation, including its two dummy warmup
runs. The candidate progressively changed the runtime policy. **Both reference
and candidates already used two threads**, so the table does not measure a
six-to-two-thread change.

Machine: Windows 11, AMD Ryzen 5 4600H, 15.42 GiB physical RAM, Python 3.14.2,
ONNX Runtime 1.25.0. Other desktop applications remained open. Available system
memory varied between runs. These are one-image local measurements, not a
representative benchmark across computers or image categories.

| Runtime policy | Peak owned-process-tree RSS | First result, including verification/session startup | Second-image inference | RSS retained after second image |
| --- | ---: | ---: | ---: | ---: |
| Previous implementation | 566.6 MiB | 1.697 s | 0.334 s | 556.0 MiB |
| Selected mask, no dummy warmups | 566.0 MiB | 0.538 s | 0.341 s | 555.5 MiB |
| Also disable CPU arena | 345.4 MiB | 0.550 s | 0.374 s | 89.9 MiB |
| Also disable memory patterns — adopted | **278.1 MiB** | **0.551 s** | **0.357 s** | **89.8 MiB** |
| Also disable prepacking — experiment only | 277.4 MiB | 0.556 s | 0.363 s | 89.3 MiB |

For the adopted candidate, sampled peak RSS fell **50.9%**, and first-result
time fell **67.6%**. Second-image inference was **6.7% slower** in this single
sample. The tradeoff favors lower memory and faster startup rather than a claim
that every operation became faster. Disabling prepacking produced little extra
memory benefit here and was **not adopted**. Production keeps ordinary ONNX
graph optimizations and prepacking.

After releasing all session references and collecting garbage in the diagnostic
process, RSS was **76.6 MiB** for the adopted candidate. The reference also fell
to 77.3 MiB after explicit release: unloading sessions matters independently of
the allocation policy. This does not mean the complete GUI will use 76.6 MiB.
Qt, previews, source/result images, clipboard data and unrelated conversion
features have their own memory allocations.

All four candidates matched the reference **exactly** for the saved floating
mask and exported RGBA image: maximum absolute mask error **0.0**, identical
RGBA pixels. That establishes equivalence for this fixture and settings, not
universal segmentation quality or accuracy on hair, glass and other difficult
subjects. No model weights were changed.

The parent sampled memory every 25 ms and would stop only its owned diagnostic
process tree below 800 MiB available system RAM, above the candidate RSS limit,
or after 90 seconds. No guard triggered in these five Fast comparisons. Sampled
RSS can miss a brief transient peak; the diagnostic guard is not an operating
system memory limit. The first-result figure stops when the first processed
result exists in memory and excludes PNG/mask export, process startup and GUI
painting. “Second-image inference” is the second real image's ONNX duration,
not an average over many iterations.

Evidence:

- [All measured results](../scratch/runtime-resource-benchmark/results.json)
- [Pixel/mask comparisons](../scratch/runtime-resource-benchmark/comparisons.json)
- [Comparison script](../scratch/benchmark_resource_runtime.py)
- [Reference output](../scratch/runtime-resource-benchmark/baseline/removed.png)
- [Adopted-policy output](../scratch/runtime-resource-benchmark/noarena-nopattern/removed.png)

The comparison script is a recorded development experiment. It loads a saved
reference implementation from `scratch/`; it is not a supported user command or
a replacement for the reusable [guarded verifier](../tools/verify_background_models.py).
The `scratch/` evidence is local and may not be included in a Git checkout.

## GUI verification

A real Fast job also passed through the four-page application UI using the
same horse image. The check verified the full-resolution PNG clipboard image,
transparent output, unchanged source, updated two-thread hint and **empty model
cache after batch completion**. It exercised the normal and minimum-size page
layouts. The sampled GUI interpreter peak was **314.1 MiB**, and its combined
owned process-tree peak was **325.7 MiB**. The check exited successfully without
triggering a diagnostic guard.

These are one-fixture absolute observations, not a before/after GUI comparison
or a guarantee for every source image, queue size or destination application.
The test used Qt's offscreen platform; native Windows clipboard interoperability
was tested separately in the earlier clipboard work.
[GUI memory evidence](../scratch/current-resource-checks/gui.json),
[GUI assertions and result](../scratch/current-resource-checks/gui.log),
[screenshot](../scratch/background-gui-smoke/background-page.png).

The focused application checks passed **110 tests**, including resource-lifetime
and concurrency behavior. The complete background-library checks passed **293
tests, with 3 skipped**. These counts do not claim a successful full
Office-dependent application suite or new Quality/Portrait inference.

## Balanced, Quality and Portrait

The same runtime policy applies to all CPU profiles, but the Fast percentages
must not be extrapolated to other architectures. An optimized **Balanced
real-image check passed** once available RAM increased to 2.58 GiB. It used two
CPU threads, disabled arena/memory patterns and retained normal graph
optimizations. No diagnostic guard triggered.

| Optimized Balanced observation | Result |
| --- | ---: |
| Sampled peak owned-process-tree RSS | **701.9 MiB** |
| Minimum physical RAM left available | 1.59 GiB |
| Session construction, without dummy inference | 0.891 s |
| Real-image ONNX inference | 2.755 s |
| Real-image removal, excluding file export | 2.903 s |
| Interpreter RSS retained after processing | 258.3 MiB |
| Interpreter RSS after explicit session release | 78.8 MiB |
| Whole diagnostic child wall time | 5.202 s |

Its exported **770 × 595 RGBA image matched the earlier Balanced output exactly**:
maximum channel error 0, with alpha spanning 0–255. The mask was finite and saved,
but this diagnostic did not compare its floating-point mask array with the old
run. Exact exported RGBA equality is the equivalence claim established here.

The previous Balanced check recorded **1.43 GiB** peak process-tree RSS and
1.680-second real inference on the same image with two threads. The current
peak is much lower, while its measured inference is slower. These were separate
runs with different available RAM, instrumentation and startup work, so they
are **cross-run observations**, not a controlled percentage improvement or a
promise about throughput. In particular, the previous “warmup” duration included
two synthetic inferences; the current session-construction duration does not.

The optimized Balanced check initially deferred while available RAM was below
its diagnostic's conservative 1.8 GiB launch threshold; it subsequently ran
successfully when eligible. That diagnostic threshold is not an application
startup rule for Balanced. Its active guards required at least 1 GiB available
RAM, at most 1.1 GiB owned-process-tree RSS and completion within 90 seconds.
[Optimized Balanced monitor](../scratch/runtime-resource-benchmark/balanced-optimized/monitor.json),
[result and equivalence evidence](../scratch/runtime-resource-benchmark/balanced-optimized/result.json),
[earlier Balanced monitor](../scratch/model-smoke/balanced/monitor.json).

Quality and Portrait retain their original 1024 × 1024 FP32 graphs and the
8 GiB startup check. Earlier guarded trials exhausted the machine's available
RAM, and **successful Quality/Portrait inference remains unverified**.
Lowering the check merely to allow them to launch would not make their
activation tensors smaller. Large source images, two-pass refinement, exports,
previews and clipboard images can also increase peak memory. These runtime
changes do not impose a fixed RAM budget on the complete application.

See [model readiness and guarded verification](BACKGROUND_MODELS.md) for the
distinction between installed, startup-ready and inference-tested states.

## What graph inspection established

A streaming metadata inspector read graph structure while seeking over tensor
payloads. It inspected all four installed files without loading a 973 MB model
or creating an inference session. Its maximum sampled own RSS was approximately
49 MiB. [Metadata evidence](../scratch/onnx-stream-metadata.json) and
[inspection script](../scratch/inspect_onnx_stream.py) are available locally.

| Profile | Registered input | Exported outputs | Consequence |
| --- | --- | ---: | --- |
| Fast | Fixed 1 × 3 × 320 × 320 FP32 | 7 | Only the registered mask is needed by this app. |
| Balanced | Fixed 1 × 3 × 1024 × 1024 FP32 | 12 | Unused static outputs total **120,061,952 bytes / 114.5 MiB**, including intermediate feature maps. Avoiding Python materialization saves needless output copies; this number is not a measured reduction in the model's activation peak. |
| Quality | Fixed 1 × 3 × 1024 × 1024 FP32 | 1 | Selected-output optimization cannot remove auxiliary outputs here. |
| Portrait | Fixed 1 × 3 × 1024 × 1024 FP32 | 1 | Same limitation as Quality. |

All graph inputs have fixed dimensions. Changing a registry value to 512 does
not safely make these files lower-resolution models. It requires a compatible
re-export and evaluation. The two BiRefNet graphs use opset 17 and include
expanded deformable-convolution primitives; no graph surgery or model rewrite
was performed in this work.

## Weight compression and additional training

Runtime optimization, quantization and training solve different problems.
Further training by itself does not reduce parameter count or guarantee lower
inference RAM. A smaller student architecture, carefully calibrated
quantization, or a newer validated export can reduce deployment cost, but each
requires accuracy and resource testing before replacing installed weights.

For convolutional networks, ONNX Runtime's primary documentation recommends
**static quantization**, using representative calibration inputs, and identifies
S8S8 with QDQ as the initial CPU choice. Quantization changes numerical results;
it can harm edge quality or be slower on a particular processor. The Fast and
Balanced graphs each contain 119 Conv nodes and no MatMul nodes, so an approach
that quantizes only MatMul would not address their main weights. A few demo
photos cannot establish quality across the user's intended content.
[ONNX Runtime quantization documentation](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html).

The pinned Quality/Portrait publisher revisions offer FP16 files of 489,666,272
bytes, approximately half their FP32 disk size. Those files were not downloaded
or activated. Half-sized weights do not establish half-sized peak RAM; CPU
float16 operator gaps and fallback/cast behavior must be evaluated. The current
CPU runtime's operator table and float16 guide do not justify a blanket CPU FP16
deployment change.
[Float16 guide](https://onnxruntime.ai/docs/performance/model-optimizations/float16.html),
[versioned CPU operator kernels](https://raw.githubusercontent.com/microsoft/onnxruntime/v1.25.0/docs/OperatorKernels.md).

The official **BiRefNet Lite** is a plausible smaller student: its published
model card lists 44.4 million parameters and a Swin-Tiny backbone. This is a
different architecture/quality tradeoff, not an optimized copy of the current
Quality/Portrait weights. Upstream also recommends newer native DeformConv ONNX
exports for lower memory and inference cost. Both routes require a separate,
pinned export, compatibility checks and acceptance evaluation.
[Official Lite model](https://huggingface.co/ZhengPeng7/BiRefNet_lite),
[official BiRefNet repository](https://github.com/ZhengPeng7/BiRefNet).

The [optional training preparation/evaluation workflow](TRAINING_AND_OPTIMIZATION.md)
accompanies this work; **no additional training has run**, and no new trained
model is shipped. There is no supplied
representative labeled dataset or independent acceptance set. Original
framework checkpoints and dedicated training compute are also needed for real
fine-tuning or distillation. Training tools and their heavyweight dependencies
must remain outside the normal application installation and frozen executable.

## Using the lighter application behavior

Use **Fast** for the lowest-cost registered workflow. Balanced is an optional
quality/resource tradeoff whose current measurements must be checked before
assuming it is suitable for a busy machine. Leave two-pass refinement off
unless the result needs it; that option adds another model pass. Process one
batch at a time and allow the batch to finish so session ownership is released.
PNG clipboard copies preserve the full-resolution result, so copying a very
large image can still consume significant memory independently of inference.

Source launches receive these changes after restarting the application. An
older packaged executable continues using its bundled code until rebuilt;
installed model cache files do not update executable runtime behavior.

## Delivered build and final checks

The optimized Windows executable was rebuilt successfully with PyInstaller
6.22.3: **251,236,908 bytes**, at
`scratch/background-build/dist/UniversalFileConverter.exe`. It contains the
runtime changes above and only the bundled Fast weights; the other verified
profiles remain in the user cache. A source-archive inventory found no training,
PyTorch, TorchVision, TensorFlow or JAX modules in its 3,656 Python module entries.
The optional training tools do not enlarge the desktop runtime.

The rebuilt executable passed real Fast CPU inference offline from an isolated
working folder: 770×595 RGBA output, alpha 0–255, matching saved mask and unchanged
source. The validation monitor observed about 359 MiB peak interpreter RSS and
404 MiB for the complete owned verification tree; no guard triggered. These are
separate frozen-CLI measurements, not the earlier source-GUI measurement or a
hard application memory ceiling.
[Frozen check](../scratch/current-resource-checks/frozen.json),
[output](../scratch/background-executable-smoke/horse-1792408941317588900.png).

The same executable discovered the verified cached Quality file, then correctly
refused to allocate it with 3.9 GiB available, explaining its 8 GiB startup
requirement. This confirms the protective path; it does not prove successful
Quality inference. No output/mask was created and the source remained unchanged.
[Quality preflight](../scratch/background-frozen-quality-preflight/1792408998266360700/result.json).

Final source verification: **110 focused application tests passed**, **293
backend tests passed / 3 skipped**, and **32 separate training-tool tests passed**.
The app checks used `--noconftest` to avoid invoking the unrelated Office COM
installation probe. No complete Office-dependent suite, actual training,
checkpoint loading or training export is claimed by those counts.
