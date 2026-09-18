# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

BASE_DIR = Path(SPECPATH).resolve()

hidden_imports = [
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PIL",
    "PIL.Image",
    "PIL.ImageOps",
    "fitz",
    "docx",
    "pptx",
    "striprtf",
    "odf",
    "reportlab",
    "pandas",
    "openpyxl",
    "pytesseract",
    "charset_normalizer",
    "image_converter.core",
    "image_converter.core.engine",
    "image_converter.core.document_engine",
    "image_converter.core.data_engine",
    "image_converter.core.presentation_engine",
    "image_converter.core.rich_doc_engine",
    "image_converter.core.security",
    "image_converter.core.ocr_engine",
    "image_converter.core.logging_config",
    "image_converter.ui",
    "image_converter.ui.main_window",
    "image_converter.ui.components",
    "image_converter.ui.theme",
    "image_converter.ui.worker",
    "image_converter.cli",
]

# Collect optional pillow-heif
try:
    import pillow_heif
    hidden_imports.extend(collect_submodules("pillow_heif"))
except ImportError:
    pass

datas = []
# Include app icons
icon_ico = BASE_DIR / "app_icon.ico"
icon_png = BASE_DIR / "app_icon.png"
if icon_ico.exists():
    datas.append((str(icon_ico), "."))
if icon_png.exists():
    datas.append((str(icon_png), "."))
assets_dir = BASE_DIR / "image_converter" / "ui" / "assets"
if assets_dir.exists():
    datas.append((str(assets_dir), "image_converter/ui/assets"))

# Collect reportlab fonts and resources
try:
    datas.extend(collect_data_files("reportlab"))
except Exception:
    pass

a = Analysis(
    [str(BASE_DIR / "launch_converter.py")],
    pathex=[str(BASE_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "IPython"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="UniversalFileConverter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Desktop GUI by default
    icon=str(icon_ico) if icon_ico.exists() else None,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
