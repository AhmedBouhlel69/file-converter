# Changelog

## 0.2.0 — Phase 2 implementation

- Pinned model profiles and explicit checksum-verified installation.
- Soft-mask cleanup, threshold, edge shift, feather, guided filter and optional matting.
- Two-pass crop inference; backgrounds, shadow, subject crop and aspect padding.
- Recursive CPU batches, collision checks, masks, lossless WebP and resume.
- Benchmark, mask evaluation and fail-closed release comparison commands/workflow.
- Fast model verified and five public samples processed offline.
- Corrected the IS-Net preprocessing template against rembg reference code.

Pending acceptance: user-labelled quality set, PyTorch parity, larger-model and
real matting validation, GPU and cross-platform measurements.

## 0.1.0 — Phase 1 implementation

Initial offline core, local registry, Python API, CLI, tests and benchmark scaffold.
