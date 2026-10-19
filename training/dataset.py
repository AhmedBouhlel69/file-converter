"""Validate explicit human-reviewed image/mask pairs and split by subject group.

python -m training.dataset pairs.json --output training/data/prepared.json
No model is loaded and source files are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

MAX_PIXELS = 24_000_000
SPLITS = ("train", "validation", "test")
IDENTITY_KEYS = ("id", "group", "image_sha256", "mask_sha256", "pixel_sha256")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def identities(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(({key: row[key] for key in IDENTITY_KEYS} for row in rows), key=lambda row: row["id"])


def split_policy(groups: set[str], seed: int, validation: float, test: float) -> dict[str, Any]:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("Split seed must be an integer")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) and 0 < v < 1 for v in (validation, test)):
        raise ValueError("Validation and test group fractions must be finite and positive")
    if validation + test >= 1:
        raise ValueError("Validation and test group fractions must sum to less than 1")
    if len(groups) < 3:
        raise ValueError("At least three independent subject/capture groups are required")
    ordered = sorted(groups, key=lambda group: hashlib.sha256(f"{seed}:{group}".encode()).hexdigest())
    validation_count = max(1, round(len(ordered) * validation))
    test_count = max(1, round(len(ordered) * test))
    if validation_count + test_count >= len(ordered):
        raise ValueError("These fractions leave no training groups; add groups or reduce fractions")
    mapping = dict.fromkeys(ordered[:test_count], "test")
    mapping.update(dict.fromkeys(ordered[test_count:test_count + validation_count], "validation"))
    mapping.update(dict.fromkeys(ordered[test_count + validation_count:], "train"))
    return {
        "seed": seed, "unit": "subject/capture group", "requested_validation_fraction": validation,
        "requested_test_fraction": test, "group_assignments": mapping,
    }


def prepared_fingerprint(data: dict[str, Any]) -> str:
    return fingerprint({
        "prepared_schema_version": 2, "content_sha256": data["content_sha256"],
        "provenance": data["provenance"], "split_policy": data["split_policy"],
        "splits": {name: identities(data["splits"][name]) for name in SPLITS},
    })


def training_lineage(data: dict[str, Any]) -> dict[str, Any]:
    """Describe the exact prepared content, split assignment and selection policy."""
    return {
        "schema_version": 1, "prepared_dataset_sha256": data["dataset_sha256"],
        "content_sha256": data["content_sha256"], "split_policy_sha256": fingerprint(data["split_policy"]),
        "split_sha256": {name: fingerprint(identities(data["splits"][name])) for name in SPLITS},
        "sample_counts": {name: len(data["splits"][name]) for name in SPLITS},
    }


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_new_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value.strip()


def local_file(root: Path, value: Any, label: str) -> Path:
    relative = Path(_text(value, label))
    if relative.is_absolute() or relative.drive:
        raise ValueError(f"{label} must be relative to the manifest directory")
    resolved = (root / relative).resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError(f"{label} escapes the dataset directory")
    if not resolved.is_file():
        raise ValueError(f"{label} must name a file")
    return resolved


def read_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as original:
        if original.width * original.height > MAX_PIXELS:
            raise ValueError(f"Image exceeds {MAX_PIXELS:,} pixels: {path}")
        if getattr(original, "n_frames", 1) != 1:
            raise ValueError(f"Animated images are not training samples: {path}")
        return np.array(ImageOps.exif_transpose(original).convert("RGB"), dtype=np.uint8)


def read_alpha(path: Path) -> np.ndarray:
    with Image.open(path) as original:
        if original.width * original.height > MAX_PIXELS:
            raise ValueError(f"Mask exceeds {MAX_PIXELS:,} pixels: {path}")
        if getattr(original, "n_frames", 1) != 1:
            raise ValueError(f"Animated masks are not supported: {path}")
        image = ImageOps.exif_transpose(original)
        # Color masks are ambiguous: a white RGB image with a perfect alpha
        # channel is easy to misread. Require an explicit grayscale annotation.
        if image.mode in {"L", "1"}:
            alpha = np.asarray(image.convert("L"), dtype=np.float32) / 255
        elif image.mode.startswith("I;16") or image.mode == "I":
            alpha = np.asarray(image, dtype=np.float32) / 65535
        elif image.mode == "F":
            alpha = np.asarray(image, dtype=np.float32)
        else:
            raise ValueError(f"Mask must be grayscale/float alpha, not {image.mode}: {path}")
    if alpha.ndim != 2 or not alpha.size or not np.isfinite(alpha).all():
        raise ValueError(f"Mask must be a finite 2D array: {path}")
    if np.any((alpha < 0) | (alpha > 1)):
        raise ValueError(f"Mask alpha must be in [0, 1]: {path}")
    return alpha


def validate_manifest(path: str | Path) -> dict[str, Any]:
    path = Path(path).resolve(strict=True)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Expected a schema_version=1 dataset object")
    provenance = data.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("provenance is required")
    for key in ("name", "rights", "annotation_process"):
        _text(provenance.get(key), f"provenance.{key}")
    if provenance.get("ground_truth") != "human-reviewed":
        raise ValueError("Only explicitly human-reviewed ground truth is accepted")
    samples = data.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("samples must be a nonempty list")
    checked, ids, content_groups = [], set(), {}
    warnings = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise ValueError(f"Sample {index} must be an object")
        identity = _text(sample.get("id"), f"Sample {index} id")
        group = _text(sample.get("group"), f"Sample {identity} group")
        if identity in ids:
            raise ValueError(f"Duplicate sample id: {identity}")
        ids.add(identity)
        image = local_file(path.parent, sample.get("image"), f"{identity}.image")
        mask = local_file(path.parent, sample.get("mask"), f"{identity}.mask")
        if image == mask:
            raise ValueError(f"Image and mask must be separate files: {identity}")
        rgb, alpha = read_rgb(image), read_alpha(mask)
        if rgb.shape[:2] != alpha.shape:
            raise ValueError(f"Image/mask dimensions differ after EXIF orientation: {identity}")
        pixel_hash = hashlib.sha256(str(rgb.shape).encode() + rgb.tobytes()).hexdigest()
        if pixel_hash in content_groups and content_groups[pixel_hash] != group:
            raise ValueError(f"Duplicate image pixels assigned to different groups: {identity}")
        content_groups[pixel_hash] = group
        if not np.any(alpha > 0) or not np.any(alpha < 1):
            warnings.append(f"{identity}: mask is entirely background or foreground")
        checked.append({
            "id": identity, "group": group,
            "image": str(image), "mask": str(mask),
            "image_sha256": sha256(image), "mask_sha256": sha256(mask),
            "pixel_sha256": pixel_hash, "width": rgb.shape[1], "height": rgb.shape[0],
        })
    if len(content_groups) < 3:
        raise ValueError("At least three distinct source images are needed for three splits")
    checked.sort(key=lambda row: row["id"])
    return {
        "schema_version": 1, "provenance": provenance,
        "content_sha256": fingerprint(identities(checked)),
        "samples": checked, "warnings": warnings,
    }


def prepare(path: str | Path, *, seed: int = 42, validation: float = .15,
            test: float = .15) -> dict[str, Any]:
    data = validate_manifest(path)
    groups = {row["group"] for row in data["samples"]}
    data["split_policy"] = split_policy(groups, seed, validation, test)
    mapping = data["split_policy"]["group_assignments"]
    data["splits"] = {
        name: [row for row in data["samples"] if mapping[row["group"]] == name]
        for name in SPLITS
    }
    del data["samples"]
    data["schema_version"] = 2
    data["dataset_sha256"] = prepared_fingerprint(data)
    return data


def load_prepared(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema_version") != 2:
        raise ValueError("Expected a prepared schema_version=2 dataset; reprepare older manifests")
    if data.get("provenance", {}).get("ground_truth") != "human-reviewed":
        raise ValueError("Prepared dataset lacks human-reviewed ground truth attestation")
    split_groups, seen_ids, content_splits, all_rows = {}, set(), {}, []
    for name in SPLITS:
        rows = data.get("splits", {}).get(name)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"Prepared dataset requires a nonempty {name} split")
        groups = set()
        for row in rows:
            if row["id"] in seen_ids:
                raise ValueError("Sample id occurs in more than one split")
            seen_ids.add(row["id"])
            groups.add(row["group"])
            for key in ("image", "mask"):
                if sha256(Path(row[key])) != row[f"{key}_sha256"]:
                    raise ValueError(f"Dataset file changed after preparation: {row[key]}")
            previous = content_splits.setdefault(row["pixel_sha256"], name)
            if previous != name:
                raise ValueError("Duplicate image content leaked across splits")
            all_rows.append(row)
        if any(groups & previous for previous in split_groups.values()):
            raise ValueError("Subject/capture group leaked across splits")
        split_groups[name] = groups
    if fingerprint(identities(all_rows)) != data.get("content_sha256"):
        raise ValueError("Prepared dataset metadata changed after preparation")
    policy = data.get("split_policy")
    if not isinstance(policy, dict):
        raise ValueError("Prepared dataset requires its split policy")
    actual_assignments = {group: name for name, groups in split_groups.items() for group in groups}
    expected_policy = split_policy(set(actual_assignments), policy.get("seed"),
                                   policy.get("requested_validation_fraction"),
                                   policy.get("requested_test_fraction"))
    if policy != expected_policy or actual_assignments != expected_policy["group_assignments"]:
        raise ValueError("Prepared split assignment or policy changed after preparation")
    if prepared_fingerprint(data) != data.get("dataset_sha256"):
        raise ValueError("Prepared dataset split fingerprint changed after preparation")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", default=42, type=int)
    parser.add_argument("--validation", default=.15, type=float)
    parser.add_argument("--test", default=.15, type=float)
    args = parser.parse_args()
    try:
        result = prepare(args.manifest, seed=args.seed, validation=args.validation, test=args.test)
        write_new_json(args.output, result)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f"Dataset rejected: {exc}\n")
    print(json.dumps({"output": str(args.output.resolve()),
                      "samples": {key: len(rows) for key, rows in result["splits"].items()},
                      "warnings": result["warnings"]}, indent=2))


if __name__ == "__main__":
    main()
