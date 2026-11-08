import os
import pytest


def _check_office_installed() -> bool:
    if os.name != "nt":
        return False
    try:
        from image_converter.core.com_utils import com_initialized
        with com_initialized():
            import win32com.client
            app = win32com.client.DispatchEx("Word.Application")
            app.Quit()
            return True
    except Exception:
        return False


_OFFICE_INSTALLED = _check_office_installed()


def pytest_collection_modifyitems(config, items):
    if not _OFFICE_INSTALLED:
        skip_office = pytest.mark.skip(reason="Microsoft Office not installed on Windows")
        for item in items:
            if "office" in item.keywords:
                item.add_marker(skip_office)


@pytest.fixture(scope="session")
def is_office_available():
    return _OFFICE_INSTALLED


@pytest.fixture(autouse=True)
def _no_libreoffice_unless_requested(request, monkeypatch):
    """Keep Office-path tests deterministic whether or not LibreOffice is installed.

    Tests that exercise the LibreOffice fallback are marked ``libreoffice``.
    """
    if "libreoffice" in request.keywords:
        return
    monkeypatch.setattr("image_converter.core.platform.libreoffice.find_soffice", lambda: None)
