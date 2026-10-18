# Model provenance and installation

Inference loads local files and verifies their full SHA-256 before opening them with
ONNX Runtime. It never downloads a missing model. The separate `bgremove models pull`
command is the only download path. `BGREMOVE_OFFLINE=1` blocks that command before
networking imports or filesystem changes.

The registry contains these pinned FP32 exports. Download sizes are decimal MB;
inference can require substantially more RAM than the file size.

| Profile | Artifact | Download | Upstream license | Validation in this workspace |
| --- | --- | ---: | --- | --- |
| `fast` | U²-NetP, 320 × 320 | 4.57 MB | Apache-2.0 | Downloaded; SHA-256 and publisher MD5 verified |
| `balanced` | IS-Net general use, 1024 × 1024 | 178.65 MB | Apache-2.0 | Publisher hash metadata checked; not locally run |
| `quality` | BiRefNet general, 1024 × 1024 | 972.67 MB | MIT | Publisher hash metadata checked; not locally run |
| `portrait` | BiRefNet portrait, 1024 × 1024 | 972.67 MB | MIT | Publisher hash metadata checked; not locally run |

Profile names describe intended roles. They are not measured accuracy or speed
rankings on this machine. These are segmentation masks, not a guarantee of correct
hair, glass, fine boundaries, or alpha matting. No parity with remove.bg or the
original PyTorch implementations has been established.

## Exact artifacts

`src/bgremove/models.json` is the authoritative machine-readable list of URLs,
SHA-256 hashes, exact sizes, normalization, licenses, and redirect allowlists.

- `fast`: the [rembg U2netpSession](https://github.com/danielgatis/rembg/blob/main/rembg/sessions/u2netp.py)
  links to its v0.0.0 `u2netp.onnx` release and records MD5
  `8e83ca70e441ab06c318d82300c84806`. The file was downloaded on 2026-10-18;
  its computed SHA-256 is
  `309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8`.
  This also matches the [pinned mirror's file metadata](https://huggingface.co/fofr/comfyui/blob/b1d7aa4aa716f042673b8f5b4b8ed4fec88631b4/rembg/u2netp.onnx).
  The local downloaded copy is `models/u2netp.onnx`; weights are not package data.
- `balanced`: the [fofr/comfyui mirror](https://huggingface.co/fofr/comfyui/blob/0cd0e3e76111f1f2e6f25091581958f381a2357e/rembg/isnet-general-use.onnx)
  at commit `0cd0e3e76111f1f2e6f25091581958f381a2357e`. SHA-256 and size were
  read from that publisher's LFS metadata on 2026-10-18. This is a third-party
  mirror, not an export published directly by the IS-Net authors. Its input and
  output normalization follow [rembg DisSession](https://github.com/danielgatis/rembg/blob/main/rembg/sessions/dis_general_use.py).
- `quality`: the [onnx-community export](https://huggingface.co/onnx-community/BiRefNet-ONNX/tree/534d3c82d3bb8b2f0867db6dfbc3a525b8e42f67)
  at commit `534d3c82d3bb8b2f0867db6dfbc3a525b8e42f67`, `onnx/model.onnx`.
  SHA-256 and size were read from its publisher's LFS metadata on 2026-10-18.
- `portrait`: the [onnx-community portrait export](https://huggingface.co/onnx-community/BiRefNet-portrait-ONNX/tree/dd7167f6a8b54ff7efc29a4c988938d79866464f)
  at commit `dd7167f6a8b54ff7efc29a4c988938d79866464f`, `onnx/model.onnx`.
  SHA-256 and size were read from its publisher's LFS metadata on 2026-10-18.

The two BiRefNet profiles follow their pinned export's `preprocessor_config.json`
and README: resize to 1024 × 1024, divide by 255, ImageNet mean/std, and apply
sigmoid to output 0 without min/max stretching. U²-NetP and IS-Net use the rembg
wrapper's image-maximum normalization and output min/max stretching. Min/max
stretching can amplify tiny differences on empty or nearly uniform scenes; those
profiles are not empty-scene detectors. This implementation uses OpenCV resizing;
the reference wrappers use Pillow, so numerical identity is not claimed.

## Licenses

The model sources declare [U²-Net Apache-2.0](https://github.com/xuebinqin/U-2-Net/blob/master/LICENSE),
[IS-Net Apache-2.0](https://github.com/xuebinqin/DIS/blob/main/LICENSE.md), and
[BiRefNet MIT](https://github.com/ZhengPeng7/BiRefNet/blob/main/LICENSE).
The [BiRefNet export card](https://huggingface.co/onnx-community/BiRefNet-ONNX/blob/534d3c82d3bb8b2f0867db6dfbc3a525b8e42f67/README.md)
also declares MIT. The `commercial_use` field reflects these declared upstream
terms; it is not an independent legal clearance or training-data rights audit.
Retain the applicable copyright/license notices when redistributing weights.
No weights are bundled in the Python distribution.

A custom profile defaults to `commercial_use: false` and `licence: unverified`.
Using such a profile requires explicit `--allow-noncommercial`, including during
installation. An empty SHA-256 always blocks installation and inference. Never
fill a placeholder hash with a guessed value.

## Download behavior

Downloads require an explicit command, HTTPS, a pinned SHA-256, and a plain ONNX
filename. Redirects are limited to the original hostname and the exact CDN hosts
listed in that profile; downgrades, credentials, unexpected hosts, and nonstandard
ports are rejected. Each request has a 30-second socket timeout. The installer
also checks a 30-minute total deadline between network reads and enforces the
registered byte size (or a 2 GiB ceiling for custom profiles without a size).

The installer writes a temporary file in the model directory, verifies the complete
content, then publishes atomically. Existing files are preserved unless overwrite
is explicitly requested. Failed downloads remove the temporary file and preserve
existing models. Atomic publication without overwrite requires a filesystem with
hard-link support, such as NTFS. A blocked CDN host must be reviewed and explicitly
added to the registry; the installer does not expand the allowlist automatically.

Tests mock network responses and verify checksum, size/deadline, offline mode,
license opt-in, HTTPS/redirect restrictions, cleanup, and concurrent-file protection.
The separate original ReduceMean ONNX test fixture is only a pipeline test; it is
not a segmentation model or a quality benchmark.
