"""
Universal File Converter Launcher
Runs the PySide6 Desktop GUI by default, or routes to CLI if arguments are supplied.
Supports Images, PDF, Word (DOCX), CSV, and Excel (XLSX).
"""

import sys
from pathlib import Path

# Add package directory to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def main():
    if "--create-shortcut" in sys.argv or "--shortcut" in sys.argv:
        from create_shortcut import main as shortcut_main
        return shortcut_main()

    # If launched with CLI arguments (other than just --gui), route to CLI
    if len(sys.argv) > 1 and "--gui" not in sys.argv:
        from image_converter.cli import main as cli_main
        return cli_main()

    # Otherwise launch Desktop GUI
    from image_converter.ui.main_window import launch_app
    return launch_app()


if __name__ == "__main__":
    sys.exit(main() or 0)
