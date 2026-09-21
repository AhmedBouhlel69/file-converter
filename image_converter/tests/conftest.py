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
