# -*- mode: python ; coding: utf-8 -*-

import sys
import hashlib
import json
import os
from pathlib import Path
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)

BASE_DIR = Path(SPECPATH).resolve()

# This application reads existing ONNX graphs through the CPU runtime. Training,
# model export, and framework frontends are optional ORT paths, and inspecting
# them can otherwise pull globally installed PyTorch/CUDA stacks into the bundle.
excluded_modules = [
    "tkinter", "matplotlib", "scipy", "pymatting", "numba", "IPython",
    "torch", "torchvision", "torchaudio", "tensorflow", "keras", "jax", "jaxlib",
    "onnx", "transformers",
    "onnxruntime.training", "onnxruntime.experimental", "onnxruntime.tools",
    "onnxruntime.transformers", "onnxruntime.quantization", "onnxruntime.backend",
    "onnxruntime.datasets",
]

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
    "image_converter.core.background_removal",
    "image_converter.ui",
    "image_converter.ui.main_window",
    "image_converter.ui.components",
    "image_converter.ui.theme",
    "image_converter.ui.worker",
    "image_converter.ui.background_removal_page",
    "image_converter.cli",
]

# Collect optional pillow-heif
try:
    import pillow_heif
    hidden_imports.extend(collect_submodules("pillow_heif"))
except ImportError:
    pass

datas = []
binaries = []
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

# Optional local segmentation. Collect packages through PyInstaller hooks rather
# than copying backgroundG/, which contains its own venv and sample artifacts.
try:
    import bgremove
    import cv2
    import onnxruntime
except ImportError as error:
    print(
        "Background Removal will be unavailable in this build: "
        f"{error}. Install image_converter/requirements-background.txt from the "
        "repository root using Python 3.11+ to include it."
    )
else:
    hidden_imports.extend(collect_submodules("bgremove"))
    hidden_imports.extend(["cv2", "onnxruntime", "onnxruntime.capi.onnxruntime_pybind11_state"])
    for package in ("bgremove", "cv2", "onnxruntime"):
        datas.extend(collect_data_files(package))
    for package in ("cv2", "onnxruntime"):
        binaries.extend(collect_dynamic_libs(package))
    for distribution in ("local-bgremove", "opencv-python-headless", "onnxruntime"):
        datas.extend(copy_metadata(distribution))

    registry_file = Path(bgremove.__file__).with_name("models.json")
    registry = json.loads(registry_file.read_text(encoding="utf-8"))
    fast = registry["fast"]
    from bgremove.config import model_directory

    # No downloads during packaging. Only the small default model is embedded;
    # larger models can be selected from an external folder after installation.
    model_dirs = [BASE_DIR / "backgroundG" / "models", model_directory()]
    if os.environ.get("BGREMOVE_MODEL_DIR"):
        model_dirs.insert(0, Path(os.environ["BGREMOVE_MODEL_DIR"]))
    fast_model = None
    for model_dir in dict.fromkeys(model_dirs):
        candidate = model_dir / fast["file"]
        if candidate.is_file():
            with candidate.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != fast["sha256"]:
                raise SystemExit(f"Refusing to bundle a model with a SHA-256 mismatch: {candidate}")
            fast_model = candidate
            break
    if fast_model is not None:
        datas.append((str(fast_model), "background_models"))
        print(f"Bundling verified fast background-removal model: {fast_model}")
    else:
        print(
            "No fast model was found; the Background Removal page will require "
            "a local model folder. To embed the default model, explicitly run "
            "'bgremove models pull fast --model-dir backgroundG/models' before building."
        )
    notices_dir = BASE_DIR / "image_converter" / "notices" / "background-removal"
    if not notices_dir.is_dir():
        raise SystemExit("Background-removal redistribution notices are missing.")
    datas.append((str(notices_dir), "notices/background-removal"))
    datas.append((str(registry_file), "notices/background-removal"))

# Collect reportlab fonts and resources
try:
    datas.extend(collect_data_files("reportlab"))
except Exception:
    pass

a = Analysis(
    [str(BASE_DIR / "launch_converter.py")],
    pathex=[str(BASE_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
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
