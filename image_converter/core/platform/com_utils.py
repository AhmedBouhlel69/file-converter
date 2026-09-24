"""
COM Automation utilities and constants for Windows Microsoft Office integration.
Provides thread-safe CoInitialize/CoUninitialize management and security constants.
"""

import sys
import os
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Microsoft Office constants
WD_ALERTS_NONE = 0
EXCEL_ALERTS_NONE = False
PP_ALERTS_NONE = 1

# MsoAutomationSecurity:
# 1 = msoAutomationSecurityLow
# 2 = msoAutomationSecurityByUI
# 3 = msoAutomationSecurityForceDisable (disables all macros without any alerts)
MSO_AUTOMATION_SECURITY_FORCE_DISABLE = 3

# Office FileFormat / Export format constants
WD_FORMAT_DOCX = 16
WD_FORMAT_PDF = 17
XL_TYPE_PDF = 0
PP_SAVE_AS_PDF = 32


@contextmanager
def com_initialized():
    """
    Context manager to ensure COM library is initialized on the current thread
    before any COM operations and properly uninitialized on exit.
    
    CRITICAL for multithreaded environments (such as ThreadPoolExecutor workers),
    where each worker thread must initialize COM independently before calling
    DispatchEx, or CoInitialize errors / RPC failures will occur.
    """
    if sys.platform == "win32" or os.name == "nt":
        initialized = False
        try:
            import pythoncom
            pythoncom.CoInitialize()
            initialized = True
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to CoInitialize COM: {e}")
        try:
            yield
        finally:
            if initialized:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception as e:
                    logger.warning(f"Failed to CoUninitialize COM: {e}")
    else:
        yield

