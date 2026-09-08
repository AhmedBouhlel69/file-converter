"""Compatibility entry point for the Universal Image Converter."""

from launch_converter import main


if __name__ == "__main__":
    raise SystemExit(main() or 0)
