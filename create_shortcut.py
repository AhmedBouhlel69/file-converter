"""
Utility to create Windows Desktop and Start Menu shortcuts with the custom app icon.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def create_windows_shortcut(
    target_path: Path,
    shortcut_path: Path,
    working_dir: Path,
    icon_path: Path,
    arguments: str = "",
    description: str = "Universal File Converter",
) -> bool:
    """Create a Windows .lnk shortcut using PowerShell with WScript.Shell fallback."""
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)

    # Method 1: PowerShell with WScript.Shell
    ps_cmd = (
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{shortcut_path}'); "
        f"$s.TargetPath = '{target_path}'; "
        f"$s.WorkingDirectory = '{working_dir}'; "
        f"$s.IconLocation = '{icon_path}, 0'; "
        f"$s.Description = '{description}'; "
    )
    if arguments:
        escaped_args = arguments.replace("'", "''")
        ps_cmd += f"$s.Arguments = '{escaped_args}'; "
    ps_cmd += "$s.Save()"

    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            check=False,
        )
        if shortcut_path.exists():
            return True
    except Exception:
        pass

    # Method 2: Fallback VBScript
    clean_target = str(target_path).replace('"', '""')
    clean_workdir = str(working_dir).replace('"', '""')
    clean_icon = str(icon_path).replace('"', '""')
    clean_desc = description.replace('"', '""')
    clean_args = arguments.replace('"', '""')

    vbs_script = (
        'Set oWS = WScript.CreateObject("WScript.Shell")\r\n'
        f'sLinkFile = "{shortcut_path}"\r\n'
        'Set oLink = oWS.CreateShortcut(sLinkFile)\r\n'
        f'oLink.TargetPath = "{clean_target}"\r\n'
        f'oLink.WorkingDirectory = "{clean_workdir}"\r\n'
        f'oLink.IconLocation = "{clean_icon}, 0"\r\n'
        f'oLink.Description = "{clean_desc}"\r\n'
    )
    if arguments:
        vbs_script += f'oLink.Arguments = "{clean_args}"\r\n'
    vbs_script += "oLink.Save\r\n"

    temp_vbs = working_dir / "_temp_create_shortcut.vbs"
    try:
        temp_vbs.write_text(vbs_script, encoding="utf-8")
        subprocess.run(
            ["cscript", "//nologo", str(temp_vbs)],
            capture_output=True,
            text=True,
            check=False,
        )
        return shortcut_path.exists()
    finally:
        if temp_vbs.exists():
            try:
                temp_vbs.unlink()
            except Exception:
                pass


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Create Windows Desktop and Start Menu shortcut with app icon."
    )
    parser.add_argument(
        "--desktop",
        action="store_true",
        default=True,
        help="Create shortcut on User Desktop (default: True).",
    )
    parser.add_argument(
        "--start-menu",
        action="store_true",
        default=False,
        help="Create shortcut in Windows Start Menu.",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="Universal File Converter",
        help="Display name for the shortcut.",
    )
    parser.add_argument(
        "--create-shortcut",
        "--shortcut",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent
    icon_path = project_dir / "app_icon.ico"
    if not icon_path.exists():
        icon_path = project_dir / "image_converter" / "ui" / "assets" / "app_icon.ico"

    # Prefer standalone executable if already built
    dist_exe = project_dir / "dist" / "UniversalFileConverter.exe"
    pythonw_exe = project_dir / "venv" / "Scripts" / "pythonw.exe"
    bat_file = project_dir / "launch_converter.bat"

    if dist_exe.exists():
        target = dist_exe
        arguments = ""
    elif pythonw_exe.exists():
        target = pythonw_exe
        arguments = f'"{project_dir / "launch_converter.py"}"'
    else:
        target = bat_file
        arguments = ""

    user_profile = Path(os.environ.get("USERPROFILE", Path.home()))
    created_count = 0

    if args.desktop:
        desktop_dir = user_profile / "Desktop"
        desktop_shortcut = desktop_dir / f"{args.name}.lnk"
        if create_windows_shortcut(
            target_path=target,
            shortcut_path=desktop_shortcut,
            working_dir=project_dir,
            icon_path=icon_path,
            arguments=arguments,
            description="Universal File Converter - Convert Images, PDF, Word, Excel, CSV, Presentations",
        ):
            print(f"✅ Desktop shortcut created: {desktop_shortcut}")
            created_count += 1
        else:
            print(f"❌ Failed to create Desktop shortcut at: {desktop_shortcut}")

    if args.start_menu:
        start_dir = (
            user_profile
            / "AppData"
            / "Roaming"
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
        )
        start_shortcut = start_dir / f"{args.name}.lnk"
        if create_windows_shortcut(
            target_path=target,
            shortcut_path=start_shortcut,
            working_dir=project_dir,
            icon_path=icon_path,
            arguments=arguments,
            description="Universal File Converter - Convert Images, PDF, Word, Excel, CSV, Presentations",
        ):
            print(f"✅ Start Menu shortcut created: {start_shortcut}")
            created_count += 1
        else:
            print(f"❌ Failed to create Start Menu shortcut at: {start_shortcut}")

    if created_count > 0:
        print(f"\n🎉 Successfully created {created_count} shortcut(s) with application icon!")
        print(f"   Icon: {icon_path}")
        print(f"   Target: {target} {arguments}".strip())
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
