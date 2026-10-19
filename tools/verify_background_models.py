"""Check local models, then optionally smoke-test each in a guarded CPU process.

Default execution verifies readiness only. --run explicitly requests inference.
This is a diagnostic tool; it does not replace or weaken the app's RAM preflight.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import psutil


GIB = 1024**3
ROOT = Path(__file__).resolve().parents[1]


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, data):
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temporary.replace(path)


def stop_owned_tree(owner):
    """Terminate only the child created by this tool and its descendants."""
    try:
        owned = [owner, *owner.children(recursive=True)]
    except psutil.NoSuchProcess:
        return
    for process in reversed(owned):
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(owned, timeout=5)


def monitor_child(child, min_free_bytes, max_rss_bytes, timeout):
    owner = None
    try:
        owner = psutil.Process(child.pid)
        start = time.monotonic()
        peak_rss = peak_tree = 0
        minimum_free = psutil.virtual_memory().available
        reason = None
        while child.poll() is None:
            elapsed = time.monotonic() - start
            available = psutil.virtual_memory().available
            minimum_free = min(minimum_free, available)
            try:
                family = [owner, *owner.children(recursive=True)]
                readings = []
                for process in family:
                    try:
                        readings.append(process.memory_info().rss)
                    except psutil.NoSuchProcess:
                        pass
            except psutil.NoSuchProcess:
                break
            peak_rss = max(peak_rss, max(readings, default=0))
            peak_tree = max(peak_tree, sum(readings))
            if available < min_free_bytes:
                reason = "available RAM fell below the diagnostic headroom limit"
            elif sum(readings) > max_rss_bytes:
                reason = "owned process tree exceeded the diagnostic RSS limit"
            elif elapsed >= timeout:
                reason = "diagnostic timeout"
            if reason:
                stop_owned_tree(owner)
                break
            time.sleep(0.1)
        returncode = child.wait(timeout=10)
    except BaseException:
        if owner is not None:
            stop_owned_tree(owner)
        else:
            # Popen retains the OS process handle even if monitoring failed
            # before psutil could establish the child's identity.
            if child.poll() is None:
                child.kill()
        child.wait(timeout=10)
        raise
    return {
        "returncode": returncode, "guard_reason": reason,
        "wall_seconds": time.monotonic() - start,
        "peak_interpreter_rss_bytes": peak_rss,
        "peak_process_tree_rss_bytes": peak_tree,
        "minimum_available_memory_bytes": minimum_free,
    }


def child_run(args):
    from PIL import Image
    from bgremove import Remover

    directory = args.child_directory.resolve()
    source = args.input.resolve()
    signature = file_hash(source)
    stage = directory / "stage.json"
    write_json(stage, {"stage": "verify_model"})
    remover = Remover(
        model=args.profile[0], device="cpu", strict_device=True,
        registry=args.registry, model_dir=args.model_dir, threads=args.threads,
    )
    write_json(stage, {"stage": "warmup"})
    start = time.perf_counter()
    remover.warmup()
    warmup = time.perf_counter() - start
    write_json(stage, {"stage": "real_image", "warmup_seconds": warmup})
    result = remover.remove(source)
    output, mask = directory / "cutout.png", directory / "mask.png"
    result.save(output)
    result.save_mask(mask)
    with Image.open(output) as saved:
        saved.load()
        assert saved.mode == "RGBA", saved.mode
        dimensions = list(saved.size)
        alpha = list(saved.getchannel("A").getextrema())
    with Image.open(mask) as saved_mask:
        saved_mask.load()
        assert list(saved_mask.size) == dimensions
    unchanged = file_hash(source) == signature
    assert unchanged, "Source changed during the diagnostic"
    data = {
        "status": "passed", "inference_tested": True,
        "profile": args.profile[0], "provider": result.provider,
        "threads": args.threads, "warmup_seconds": warmup,
        "timings": result.timings, "output": str(output), "mask": str(mask),
        "dimensions": dimensions, "alpha_extrema": alpha,
        "source_sha256": signature, "source_unchanged": unchanged,
    }
    write_json(directory / "result.json", data)
    write_json(stage, {"stage": "complete"})
    return 0


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--profile", action="append", help="Repeat to select profiles; default all")
    result.add_argument("--model-dir", type=Path)
    result.add_argument("--registry", type=Path)
    result.add_argument("--run", action="store_true", help="Explicitly request real inference")
    result.add_argument("--input", type=Path, help="Required with --run")
    result.add_argument("--report-dir", type=Path, default=ROOT / "scratch/model-verification")
    result.add_argument("--threads", type=int, default=2)
    result.add_argument("--timeout", type=float, default=180)
    result.add_argument("--min-free-gib", type=float, default=1)
    result.add_argument("--max-rss-gib", type=float, default=8)
    result.add_argument("--child-directory", type=Path, help=argparse.SUPPRESS)
    return result


def run(args):
    from bgremove.readiness import check_models, readiness_exit_code

    if args.run and (args.input is None or not args.input.is_file()):
        raise ValueError("--run requires --input pointing to an existing image")
    limits = (args.timeout, args.min_free_gib, args.max_rss_gib)
    if args.threads < 1 or any(not math.isfinite(value) or value <= 0 for value in limits):
        raise ValueError("Threads, timeout and diagnostic memory limits must be positive")
    # Profile names are registry keys, not output paths. Child directories use indices.
    available = check_models(registry=args.registry, model_dir=args.model_dir)
    known = [item["profile"] for item in available["profiles"]]
    selected = list(dict.fromkeys(args.profile or known))
    unknown = set(selected) - set(known)
    if unknown:
        raise ValueError(f"Unknown model profiles: {', '.join(sorted(unknown))}")
    args.report_dir.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="run-", dir=args.report_dir.resolve()))
    report = {"schema_version": 1, "mode": "inference" if args.run else "readiness",
              "report_directory": str(folder), "cpu_threads": args.threads,
              "guard": {"minimum_free_bytes": int(args.min_free_gib * GIB),
                        "maximum_tree_rss_bytes": int(args.max_rss_gib * GIB),
                        "timeout_seconds": args.timeout}, "profiles": []}
    exit_code = 0
    for index, profile in enumerate(selected):
        readiness = check_models(profile, registry=args.registry, model_dir=args.model_dir)
        entry = dict(readiness["profiles"][0])
        entry.update(inference_tested=False, child_launched=False,
                     readiness_status=entry["status"], readiness_reason=entry["reason"],
                     available_memory_bytes=readiness["available_memory_bytes"])
        code = readiness_exit_code(readiness)
        if code:
            entry["verification_status"] = "blocked"
        elif not args.run:
            entry["verification_status"] = "ready_not_tested"
        elif psutil.virtual_memory().available < args.min_free_gib * GIB:
            code = 5
            entry.update(verification_status="blocked", reason="Insufficient diagnostic RAM headroom")
        else:
            child_folder = folder / f"{index:02d}"
            child_folder.mkdir()
            command = [sys.executable, str(Path(__file__).resolve()),
                       "--child-directory", str(child_folder), "--profile", profile,
                       "--input", str(args.input.resolve()), "--threads", str(args.threads), "--run"]
            for option, value in (("--model-dir", args.model_dir), ("--registry", args.registry)):
                if value is not None:
                    command.extend((option, str(value.resolve())))
            environment = dict(os.environ)
            environment["BGREMOVE_OFFLINE"] = "1"
            startup = None
            flags = 0
            if os.name == "nt":
                startup = subprocess.STARTUPINFO()
                startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startup.wShowWindow = subprocess.SW_HIDE
                flags = subprocess.CREATE_NO_WINDOW
            with (child_folder / "stdout.log").open("wb") as stdout, (child_folder / "stderr.log").open("wb") as stderr:
                child = subprocess.Popen(command, env=environment, cwd=ROOT, stdout=stdout,
                                         stderr=stderr, startupinfo=startup, creationflags=flags)
                entry["child_launched"] = True
                outcome = monitor_child(child, int(args.min_free_gib * GIB),
                                        int(args.max_rss_gib * GIB), args.timeout)
            entry["monitor"] = outcome
            evidence = child_folder / "result.json"
            if outcome["returncode"] == 0 and evidence.is_file() and not outcome["guard_reason"]:
                entry.update(json.loads(evidence.read_text(encoding="utf-8")))
                entry["verification_status"] = "passed"
                entry["reason"] = "Real CPU warmup, image inference, PNG/mask decoding and source-integrity checks passed."
            else:
                code = 1
                entry.update(verification_status="failed", evidence_directory=str(child_folder))
        if code == 1 or (code == 3 and exit_code != 1) or (code == 5 and exit_code == 0):
            exit_code = code
        report["profiles"].append(entry)
        report["exit_code"] = exit_code
        write_json(folder / "report.json", report)
    print(json.dumps(report, indent=2))
    return exit_code


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.child_directory is not None:
            if not args.run or not args.profile or len(args.profile) != 1 or args.input is None:
                raise ValueError("Invalid internal child arguments")
            return child_run(args)
        return run(args)
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
