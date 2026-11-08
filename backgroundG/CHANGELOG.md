# Changelog

## Unreleased

- `RefineOptions.decontaminate` and `estimate_foreground`: blur-fusion foreground colour
  estimation removes background halos on soft edges (synthetic edge colour error 84 -> 17 of 255)
  and blanks hidden colours under transparent pixels. Striped, so memory stays low.
- `RefineOptions.levels_low` / `levels_high`: alpha levels to remove faint ghosting.
- `Remover.remove(tta=True)` / `BatchOptions.tta`: flip-averaged prediction (about 2x inference time).
- CLI: `--clean-edges`, `--levels-low`, `--levels-high`, `--accurate`.
- Model verification is cached per process for an unchanged file (size + mtime).
- Export falls back to exclusive-create + copy when hard links are unavailable
  (FAT/exFAT, network shares); still never overwrites.

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
