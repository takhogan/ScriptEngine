import importlib

import pytest


def test_required_ocr_modules_available():
    required_modules = ["easyocr", "tesserocr", "PIL"]
    missing = []
    for module_name in required_modules:
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            missing.append(module_name)

    if missing:
        pytest.fail(
            "Missing OCR dependencies: {}. Install these packages in the test environment. "
            "This test intentionally fails so dependency gaps are addressed.".format(", ".join(missing))
        )
