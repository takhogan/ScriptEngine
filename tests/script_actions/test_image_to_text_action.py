import importlib
from pathlib import Path

import numpy as np
import pytest
from ScriptEngine.common.enums import ScriptExecutionState
import ScriptEngine.system_script_action_executor as ssae_mod


def _image_to_text_action(conversion_engine):
    return {
        "actionName": "imageToTextAction",
        "actionData": {
            "targetSystem": "none",
            "conversionEngine": conversion_engine,
            "characterWhiteList": "",
            "increaseContrast": False,
            "invertColors": False,
            "targetType": "word",
            "outputVarName": "ocr_out",
        },
    }


def _require_module(module_name):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.fail(
            "Missing required OCR dependency '{}'. Install it in the test environment; "
            "these tests intentionally fail instead of skipping when OCR engines are absent. "
            "Original error: {}".format(module_name, exc)
        )


def test_image_to_text_action_easyocr(system_executor, base_context, run_queue, monkeypatch):
    _require_module("easyocr")
    executor, _, _ = system_executor
    screenshot = np.random.randint(0, 255, (30, 60, 3), dtype=np.uint8)
    monkeypatch.setattr(
        ssae_mod.DetectObjectHelper,
        "get_detect_area",
        lambda *_: {"screencap_im_bgr": screenshot},
    )
    action = _image_to_text_action("easyOCR")
    _, status, state, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    assert status == ScriptExecutionState.SUCCESS
    assert isinstance(state["ocr_out"], str)


def test_image_to_text_action_tesseract(system_executor, base_context, run_queue, monkeypatch):
    _require_module("PIL")
    tessdata_dir = Path("/opt/homebrew/share/tessdata")
    if not tessdata_dir.exists():
        pytest.fail(
            "tesserocr is installed but tessdata was not found at '{}'. "
            "Install Tesseract language data and set TESSDATA_PREFIX.".format(tessdata_dir)
        )
    monkeypatch.setenv("TESSDATA_PREFIX", str(tessdata_dir))
    _require_module("tesserocr")
    executor, _, _ = system_executor
    screenshot = np.random.randint(0, 255, (30, 60, 3), dtype=np.uint8)
    monkeypatch.setattr(
        ssae_mod.DetectObjectHelper,
        "get_detect_area",
        lambda *_: {"screencap_im_bgr": screenshot},
    )
    action = _image_to_text_action("tesseractOCR")
    try:
        _, status, state, _, _, _ = executor.handle_action(action, {}, base_context, run_queue)
    except RuntimeError as exc:
        pytest.fail(
            "Real tesserocr API failed to initialize. Ensure tesserocr is built/installed against the "
            "current local Tesseract installation and tessdata path. Original error: {}".format(exc)
        )
    assert status == ScriptExecutionState.SUCCESS
    assert isinstance(state["ocr_out"], str)
