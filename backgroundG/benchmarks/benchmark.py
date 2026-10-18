import argparse
import json
from pathlib import Path

from bgremove import Remover
from bgremove.benchmark import run_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark installed background removal models")
    parser.add_argument("image", nargs="?", type=Path, help="Omit to generate synthetic RGB inputs")
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--model", default="balanced")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--allow-noncommercial", action="store_true")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--sizes", type=float, nargs="+", default=[1, 12, 24])
    parser.add_argument("--output", type=Path, default=Path("benchmark-results.json"))
    args = parser.parse_args()
    remover = Remover(
        args.model,
        args.device,
        registry=args.registry,
        model_dir=args.model_dir,
        allow_noncommercial=args.allow_noncommercial,
    )
    report = run_benchmark(
        remover,
        args.image,
        warmups=args.warmups,
        runs=args.runs,
        megapixels=args.sizes,
        profile=args.model,
    )
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
