# Contributing to Universal File Converter

Thank you for your interest in contributing to Universal File Converter! We welcome community contributions, bug reports, feature requests, and new format pipelines.

---

## 🛠️ Development Setup

1. **Fork and Clone the Repository**:
   ```bash
   git clone https://github.com/your-username/file-converter.git
   cd file-converter
   ```

2. **Create and Activate a Virtual Environment**:
   ```powershell
   # Windows
   python -m venv venv
   .\venv\Scripts\activate

   # macOS / Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r image_converter/requirements.txt
   pip install pytest
   ```

---

## 📐 Coding Standards & Architecture Principles

- **Type Annotations**: All public functions and engine methods must include explicit type hints (`str | Path`, `Optional[int]`, `Dict[str, Any]`, etc.).
- **Docstrings & Comments**: Keep docstrings comprehensive, describing arguments, return types, and possible exceptions. Preserve existing comments.
- **Security-First Design**:
  - Always sanitize output paths with `validate_output_path()`.
  - Always validate input files with `validate_input_file()`.
  - Check container limits with `validate_zip_container()` for any zip-based archive format.
  - Never trust file extensions alone; verify binary magic signatures with `sniff_file_type()`.
- **Zero Headless Crashes**: Pure-Python fallbacks are required. Operations should never assume a local Microsoft Office, Word, or Excel installation is available.
- **Thread Safety**: Any background tasks or engine extensions must be thread-safe for use within `ThreadPoolExecutor` and PySide6 `QThread` workers.

---

## 🧩 Adding Support for a New File Format

1. **Engine Implementation**:
   - Create or extend an engine module under `image_converter/core/` (e.g. `document_engine.py`, `presentation_engine.py`, or a new specialized engine).
   - Implement metadata extraction returning consistent keys: `file_name`, `file_path`, `file_size`, `format`, `width`, `height`, etc.
2. **Register in `engine.py`**:
   - Add input extensions to `SUPPORTED_INPUT_FORMATS`.
   - Add target format uppercase name to `SUPPORTED_OUTPUT_FORMATS` and `FORMAT_EXTENSIONS`.
   - Add routing branch inside `ImageConverterEngine.convert_single()`.
   - Add metadata handler inside `get_image_metadata()`.
3. **GUI and CLI Integration**:
   - Update `FilePreviewWidget` in `image_converter/ui/components.py` with preview rendering or summary card.
   - Update `cli.py` `--list-formats` documentation.
4. **Automated Testing**:
   - Add unit tests under `image_converter/tests/` covering normal conversions, empty files, and corrupted headers.

---

## 🧪 Running the Test Suite

Before submitting a pull request, ensure all tests pass cleanly:

```powershell
# Run the complete test suite
python -m pytest image_converter/tests -v
```

Expected result: 69/69 tests passing across all modules.

---

## 📝 Pull Request Checklist

- [ ] All new functions include type hints and docstrings.
- [ ] No regression in existing formats or CLI flags.
- [ ] Added unit tests covering new features or bug fixes.
- [ ] All 69+ tests in `image_converter/tests` pass without errors.
- [ ] `README.md` updated if new flags, formats, or options were introduced.
