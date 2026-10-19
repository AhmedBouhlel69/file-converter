"""Synthetic fixtures test tooling only; they are not a training/quality dataset."""
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image
import pytest

from training.dataset import load_prepared, prepare, validate_manifest, write_new_json


@pytest.fixture
def pairs(tmp_path):
    samples = []
    for index in range(10):
        pixels = np.zeros((12, 16, 3), dtype=np.uint8)
        pixels[:, :, 0] = index * 20
        pixels[:, 4:12, 1] = 255
        Image.fromarray(pixels).save(tmp_path / f"image-{index}.png")
        mask = np.zeros((12, 16), dtype=np.uint8)
        mask[:, 4:12] = 255
        Image.fromarray(mask).save(tmp_path / f"mask-{index}.png")
        samples.append({"id": f"sample-{index}", "group": f"subject-{index}",
                        "image": f"image-{index}.png", "mask": f"mask-{index}.png"})
    data = {"schema_version": 1,
            "provenance": {"name": "unit test fixtures", "rights": "synthetic test fixtures only",
                           "ground_truth": "human-reviewed", "annotation_process": "fixture generation"},
            "samples": samples}
    path = tmp_path / "pairs.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path, data


def save(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_split_is_deterministic_and_group_disjoint(pairs):
    path, data = pairs
    # A second photo of a subject must remain with its first photo.
    data["samples"][1]["group"] = data["samples"][0]["group"]
    save(path, data)
    prepared = prepare(path)
    save(path, {**data, "samples": list(reversed(data["samples"]))})
    assert prepared == prepare(path)
    groups = [{row["group"] for row in split} for split in prepared["splits"].values()]
    assert all(groups)
    assert not (groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
    assert sum(map(len, prepared["splits"].values())) == len(data["samples"])


@pytest.mark.parametrize("field,value", [("image", "../outside.png"), ("mask", "../outside.png")])
def test_paths_cannot_escape_manifest_directory(pairs, field, value):
    path, data = pairs
    Image.new("L", (16, 12)).save(path.parent.parent / "outside.png")
    data["samples"][0][field] = value
    save(path, data)
    with pytest.raises(ValueError, match="escapes"):
        validate_manifest(path)


def test_absolute_path_rejected(pairs):
    path, data = pairs
    data["samples"][0]["image"] = str((path.parent / "image-0.png").resolve())
    save(path, data)
    with pytest.raises(ValueError, match="relative"):
        validate_manifest(path)


def test_duplicate_pixels_across_subject_groups_rejected(pairs):
    path, data = pairs
    # Different filenames/metadata do not make a second independent image.
    with Image.open(path.parent / "image-0.png") as image:
        image.save(path.parent / "image-1.png")
    with pytest.raises(ValueError, match="Duplicate image pixels"):
        validate_manifest(path)


def test_dimensions_must_match(pairs):
    path, _ = pairs
    Image.new("L", (8, 8)).save(path.parent / "mask-0.png")
    with pytest.raises(ValueError, match="dimensions differ"):
        validate_manifest(path)


def test_color_mask_is_not_silently_interpreted(pairs):
    path, _ = pairs
    Image.new("RGBA", (16, 12), (255, 255, 255, 0)).save(path.parent / "mask-0.png")
    with pytest.raises(ValueError, match="grayscale"):
        validate_manifest(path)


def test_float_mask_range_is_checked(pairs):
    path, data = pairs
    Image.fromarray(np.full((12, 16), 1.5, dtype=np.float32)).save(path.parent / "bad.tiff")
    data["samples"][0]["mask"] = "bad.tiff"
    save(path, data)
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        validate_manifest(path)


def test_generated_labels_do_not_pass_attestation(pairs):
    path, data = pairs
    data["provenance"]["ground_truth"] = "teacher-generated"
    save(path, data)
    with pytest.raises(ValueError, match="human-reviewed"):
        validate_manifest(path)


def test_need_three_independent_groups(pairs):
    path, data = pairs
    for sample in data["samples"]:
        sample["group"] = "same-person-and-session"
    save(path, data)
    with pytest.raises(ValueError, match="three independent"):
        prepare(path)


def test_changed_input_is_detected_before_training(pairs):
    path, _ = pairs
    output = path.parent / "prepared.json"
    write_new_json(output, prepare(path))
    assert load_prepared(output)["splits"]["test"]
    Image.new("RGB", (16, 12), "red").save(path.parent / "image-0.png")
    with pytest.raises(ValueError, match="changed after preparation"):
        load_prepared(output)


def test_tampered_split_group_leakage_is_rejected(pairs):
    path, _ = pairs
    data = prepare(path)
    data["splits"]["test"][0]["group"] = data["splits"]["train"][0]["group"]
    output = path.parent / "prepared.json"
    write_new_json(output, data)
    with pytest.raises(ValueError, match="group leaked"):
        load_prepared(output)


def test_tampered_sample_identity_is_rejected(pairs):
    path, _ = pairs
    data = prepare(path)
    data["splits"]["test"][0]["id"] = "changed-after-preparation"
    output = path.parent / "prepared.json"
    write_new_json(output, data)
    with pytest.raises(ValueError, match="metadata changed"):
        load_prepared(output)


def test_whole_train_test_group_swap_is_rejected(pairs):
    path, _ = pairs
    data = prepare(path)
    data["splits"]["train"], data["splits"]["test"] = data["splits"]["test"], data["splits"]["train"]
    output = path.parent / "prepared.json"
    write_new_json(output, data)
    with pytest.raises(ValueError, match="split assignment or policy changed"):
        load_prepared(output)


def test_different_seed_changes_prepared_fingerprint(pairs):
    path, _ = pairs
    before, after = prepare(path, seed=42), prepare(path, seed=43)
    assert before["content_sha256"] == after["content_sha256"]
    assert before["dataset_sha256"] != after["dataset_sha256"]


@pytest.mark.parametrize("changed_key", ["seed", "group_assignments"])
def test_tampered_split_policy_is_rejected(pairs, changed_key):
    path, _ = pairs
    data = prepare(path)
    if changed_key == "seed":
        data["split_policy"]["seed"] += 1
    else:
        group = data["splits"]["test"][0]["group"]
        data["split_policy"]["group_assignments"][group] = "train"
    output = path.parent / "prepared.json"
    write_new_json(output, data)
    with pytest.raises(ValueError, match="split assignment or policy changed"):
        load_prepared(output)


def test_reordered_prepared_samples_keep_canonical_fingerprint(pairs):
    path, _ = pairs
    data = prepare(path)
    for rows in data["splits"].values():
        rows.reverse()
    output = path.parent / "prepared.json"
    write_new_json(output, data)
    assert load_prepared(output)["dataset_sha256"] == data["dataset_sha256"]


def test_output_is_never_overwritten(pairs):
    path, _ = pairs
    output = path.parent / "prepared.json"
    write_new_json(output, prepare(path))
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        write_new_json(output, {"oops": True})
    assert output.read_bytes() == original


@pytest.mark.parametrize("fraction", [float("nan"), float("inf"), -.1, 0, 1])
def test_invalid_split_fractions_rejected(pairs, fraction):
    path, _ = pairs
    with pytest.raises(ValueError):
        prepare(path, validation=fraction)


def test_training_tools_import_without_pytorch():
    subprocess.run([sys.executable, "-c", (
        "import sys; import training.finetune_u2netp, training.export_u2netp, "
        "training.evaluate_candidate; assert 'torch' not in sys.modules"
    )], check=True, cwd=Path(__file__).resolve().parents[2])
