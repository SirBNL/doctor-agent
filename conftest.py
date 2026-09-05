"""تنظیمات pytest: مسیر پروژه + ریست خودکار حافظه کلینیک قبل از هر تست."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from tools import reset_clinic_state


@pytest.fixture(autouse=True)
def fresh_clinic_state():
    """قبل و بعد از هر تست، نوبت‌ها و حافظه کلینیک از نو ساخته می‌شوند."""
    reset_clinic_state()
    yield
    reset_clinic_state()
