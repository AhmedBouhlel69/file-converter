import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any

import typer
from typer.core import TyperGroup

from .batch import BatchOptions, plan_batch, run_batch
from .compose import ComposeOptions
from .config import model_directory
from .refine import RefineOptions
from .registry import ModelError, read_registry, verify_model
from .remover import Remover


class DefaultGroup(TyperGroup):
    """Keep the spec's `bgremove INPUT -o DIR` syntax alongside subcommands."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        if (
            args
            and args[0] not in self.commands
            and args[0] not in {"--help", "--install-completion", "--show-completion"}
        ):
            args.insert(0, "remove")
        return super().parse_args(ctx, args)


app = typer.Typer(
    cls=DefaultGroup,
    no_args_is_help=True,
    help="Offline background removal. Pass image paths directly or use a subcommand.",
)
models_app = typer.Typer(no_args_is_help=True, help="Explicit model installation and verification.")
app.add_typer(models_app, name="models")


@contextmanager
def errors() -> Iterator[None]:
    try:
        yield
    except typer.Exit:
        raise
    except ModelError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(3) from exc
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc


@app.command("remove")
def main(
    inputs: Annotated[list[Path], typer.Argument(help="Image files or folders")],
    output: Annotated[Path, typer.Option("--output", "-o")],
    model: str = "balanced",
    device: str = "auto",
    strict_device: bool = False,
    registry: Path | None = None,
    model_dir: Path | None = None,
    format: str = "png",
    save_mask: bool = False,
    mask_only: bool = False,
    bg_color: str | None = None,
    bg_image: Path | None = None,
    bg_blur: float | None = None,
    shadow: bool = False,
    crop: bool = False,
    padding: int = 0,
    aspect: float | None = None,
    threshold: float | None = None,
    edge_shift: int = 0,
    feather: float = 0,
    min_blob_ratio: float = 0.001,
    guided_radius: int = 0,
    guided_eps: float = 0.001,
    matting: bool = False,
    two_pass: bool = False,
    jobs: int = 1,
    threads: int = 0,
    recursive: bool = False,
    skip_existing: bool = False,
    overwrite: bool = False,
    keep_metadata: bool = False,
    allow_noncommercial: bool = False,
    verbose: bool = False,
) -> None:
    """Remove backgrounds; also accepts `bgremove INPUT -o DIR` without `remove`."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.WARNING)
    with errors():
        refinement = RefineOptions(
            threshold=threshold,
            edge_shift=edge_shift,
            min_blob_ratio=min_blob_ratio,
            feather_sigma=feather,
            guided_radius=guided_radius,
            guided_eps=guided_eps,
            matting=matting,
        )
        composition = ComposeOptions(
            bg_color=bg_color,
            bg_image=str(bg_image) if bg_image else None,
            bg_blur=bg_blur,
            shadow=shadow,
            crop=crop,
            padding=padding,
            aspect=aspect,
        )
        items = plan_batch(
            inputs,
            output,
            recursive=recursive,
            format=format,
            save_mask=save_mask,
            mask_only=mask_only,
            skip_existing=skip_existing,
            overwrite=overwrite,
        )
        config = {
            "model": model,
            "device": device,
            "registry": registry,
            "model_dir": model_dir,
            "strict_device": strict_device,
            "allow_noncommercial": allow_noncommercial,
            "threads": threads,
        }
        results = run_batch(
            items,
            config,
            BatchOptions(refinement, composition, two_pass, overwrite, keep_metadata),
            jobs=jobs,
        )
        for result in results:
            typer.echo(
                f"{result.status}: {result.source}" + (f": {result.error}" if result.error else ""),
                err=result.status == "failed",
            )
        failures = [result for result in results if result.status == "failed"]
        if failures:
            raise typer.Exit(4 if len(results) == 1 and failures[0].input_error else 1)


@models_app.command("list")
def models_list(registry: Path | None = None, model_dir: Path | None = None) -> None:
    """List profiles, licence information and local installation status as JSON."""
    with errors():
        data = []
        for profile, config in read_registry(registry).items():
            path = (model_dir or model_directory()) / config.file
            data.append(
                {
                    "profile": profile,
                    "name": config.name,
                    "licence": config.licence,
                    "commercial_use": config.commercial_use,
                    "installed": path.is_file(),
                    "checksum_registered": bool(config.sha256),
                    "path": str(path),
                }
            )
        typer.echo(json.dumps(data, indent=2))


@models_app.command("verify")
def models_verify(
    profile: Annotated[str | None, typer.Argument()] = None,
    registry: Path | None = None,
    model_dir: Path | None = None,
    allow_noncommercial: bool = False,
) -> None:
    """Verify an installed profile, or all registered profiles."""
    with errors():
        configs = read_registry(registry)
        if profile is not None and profile not in configs:
            raise ValueError(f"Unknown model profile: {profile}")
        for name, config in configs.items():
            if profile is None or profile == name:
                typer.echo(
                    f"Verified {name}: {verify_model(config, model_dir, allow_noncommercial)}"
                )


@models_app.command("pull")
def models_pull(
    profile: str,
    registry: Path | None = None,
    model_dir: Path | None = None,
    allow_noncommercial: bool = False,
    overwrite: bool = False,
) -> None:
    """Explicitly download a pinned ONNX artifact and verify its SHA-256."""
    with errors():
        from .model_install import pull_model

        configs = read_registry(registry)
        if profile not in configs:
            raise ValueError(f"Unknown model profile: {profile}")
        typer.echo(
            pull_model(
                configs[profile],
                model_dir or model_directory(),
                allow_noncommercial=allow_noncommercial,
                overwrite=overwrite,
            )
        )


@app.command("bench")
def bench(
    image: Path,
    output: Annotated[Path, typer.Option("--output", "-o")],
    model: str = "balanced",
    device: str = "auto",
    registry: Path | None = None,
    model_dir: Path | None = None,
    runs: int = 20,
    warmups: int = 3,
    sizes: str = "1,12,24",
    threads: int = 0,
    strict_device: bool = False,
    allow_noncommercial: bool = False,
) -> None:
    """Benchmark each stage at requested megapixel sizes (three warmups, 20 timed runs)."""
    with errors():
        from .benchmark import run_benchmark

        remover = Remover(
            model,
            device,
            registry=registry,
            model_dir=model_dir,
            allow_noncommercial=allow_noncommercial,
            threads=threads,
            strict_device=strict_device,
        )
        report = run_benchmark(
            remover,
            image,
            warmups=warmups,
            runs=runs,
            megapixels=tuple(float(x) for x in sizes.split(",")),
            profile=model,
        )
        _write_json(output, report)


@app.command("evaluate")
def evaluate(
    manifest: Path,
    output: Annotated[Path, typer.Option("--output", "-o")],
    benchmark: Path | None = None,
    matting: bool = False,
) -> None:
    """Measure predicted masks against ground truth; optionally attach benchmark timings."""
    with errors():
        from .evaluation import evaluate_manifest

        report = evaluate_manifest(manifest, matting=matting)
        if benchmark:
            timings = json.loads(benchmark.read_text(encoding="utf-8-sig"))
            if not isinstance(timings, dict):
                raise ValueError("Benchmark report must be a JSON object")
            if timings.get("profile") != report.get("profile"):
                raise ValueError("Evaluation and benchmark profiles must match")
            for key in ("sizes", "stages", "environment", "runs", "warmups", "timing_unit", "runtime_options"):
                if key in timings:
                    report[key] = timings[key]
        _write_json(output, report)


@app.command("gate")
def gate(baseline: Path, candidate: Path, output: Path | None = None) -> None:
    """Fail on quality drops over one point or p95 regressions over 15%."""
    with errors():
        from .evaluation import compare_reports

        report = compare_reports(baseline, candidate)
        if output:
            _write_json(output, report)
        else:
            typer.echo(json.dumps(report, indent=2, allow_nan=False))
        if not report["passed"]:
            raise typer.Exit(1)


def _write_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    typer.echo(f"Saved {path}")
