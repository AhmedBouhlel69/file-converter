"""
Build script for packaging Universal File Converter into a standalone executable using PyInstaller.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Build Universal File Converter executable.")
    parser.add_argument(
        "--onefile",
        action="store_true",
        default=True,
        help="Package application into a single executable file (default: True).",
    )
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="Package application into a single directory containing dependencies.",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Keep console window open (useful for debugging CLI or logging).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build and dist directories before building.",
    )
    parser.add_argument(
        "--shortcut",
        action="store_true",
        help="Create a Windows Desktop shortcut with application icon pointing to the built executable.",
    )
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent
    spec_path = project_dir / "universal_file_converter.spec"

    print("=" * 60)
    print("Building Universal File Converter Standalone Executable")
    print("=" * 60)

    if args.clean:
        print("[1/3] Cleaning previous build artifacts...")
        for folder in [project_dir / "build", project_dir / "dist"]:
            if folder.exists():
                shutil.rmtree(folder)
                print(f"  Removed: {folder.name}/")

    print("[2/3] Running PyInstaller build...")
    pyinstaller_exe = project_dir / "venv" / "Scripts" / "pyinstaller.exe"
    if not pyinstaller_exe.exists():
        pyinstaller_exe = "pyinstaller"

    cmd = [str(pyinstaller_exe), str(spec_path), "--noconfirm"]

    if args.clean:
        cmd.append("--clean")

    print(f"  Command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(project_dir))

    if result.returncode == 0:
        dist_dir = project_dir / "dist"
        print("[3/3] Build completed successfully!")
        print(f"\nArtifacts located in: {dist_dir}")
        for item in dist_dir.glob("*"):
            size_mb = item.stat().st_size / (1024 * 1024) if item.is_file() else 0
            if item.is_file():
                print(f"  • {item.name} ({size_mb:.1f} MB)")
            else:
                print(f"  • {item.name}/ (directory bundle)")

        if args.shortcut:
            print("\nCreating Windows Desktop shortcut...")
            try:
                from create_shortcut import main as shortcut_main
                shortcut_main()
            except Exception as e:
                print(f"Warning: Could not create shortcut: {e}", file=sys.stderr)

        return 0
    else:
        print("\nBuild failed with exit code:", result.returncode, file=sys.stderr)
        return result.returncode


if __name__ == "__main__":
    sys.exit(main())
