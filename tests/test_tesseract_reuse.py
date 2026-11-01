import random
import time

import cv2
import numpy as np
import pytest
import tesserocr
from PIL import Image

import ScriptEngine.helpers.image_to_text_action_helper as helper_mod
from ScriptEngine.helpers.image_to_text_action_helper import ImageToTextActionHelper

# OCR reuses one Tesseract instance per process instead of building one per
# action, because building one reads the language model from disk. A reused
# instance must read every image exactly as a fresh one would.

TEXTS = ['Stamina Potion (20)', 'Healing Speed Up (5Min)', 'Deep Lode', "Today's Times Remaining: 7/10", '6500000', 'BLACK_RICE']
SETTINGS = [('word', ''), ('sentence', ''), ('page', ''), ('word', '0123456789'), ('sentence', '0123456789/')]
PSM = {'word': 8, 'sentence': 7, 'page': 3}


def text_image(text, scale, inverted):
    width = 24 * len(text) + 20
    image = np.full((48, width), 255, np.uint8)
    cv2.putText(image, text, (8, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 0, 2)
    image = cv2.resize(image, None, fx=scale, fy=scale)
    if inverted:
        image = 255 - image
    return cv2.copyMakeBorder(image, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=0 if inverted else 255)


def action(target_type, whitelist):
    return {'actionData': {'targetType': target_type, 'characterWhiteList': whitelist}}


def read_with_a_fresh_instance(image, target_type, whitelist):
    """What every OCR action did before: build an instance, read, throw it away."""
    tessdata_path = ImageToTextActionHelper.get_tessdata_path()
    with tesserocr.PyTessBaseAPI(**({'path': tessdata_path} if tessdata_path else {})) as api:
        api.SetImage(Image.fromarray(image))
        api.SetPageSegMode(PSM[target_type])
        if whitelist:
            api.SetVariable('tessedit_char_whitelist', whitelist)
        return api.GetUTF8Text().strip()


def read_with_the_shared_instance(image, target_type, whitelist):
    outputs, _, _ = ImageToTextActionHelper.run_tesseract_ocr(action(target_type, whitelist), image, False)
    return outputs[0]


@pytest.fixture(autouse=True)
def no_shared_instance_yet():
    helper_mod._tesseract_apis.clear()
    yield
    helper_mod._tesseract_apis.clear()


def test_a_shared_instance_reads_what_a_fresh_one_reads():
    cases = [
        (text_image(text, scale, inverted), target_type, whitelist)
        for text in TEXTS
        for scale, inverted in ((1, False), (2, True))
        for target_type, whitelist in SETTINGS
    ]
    # Shuffled, so each call follows a different page mode and whitelist than
    # the one before it, and whatever the instance kept would show.
    random.Random(7).shuffle(cases)

    for image, target_type, whitelist in cases:
        assert read_with_the_shared_instance(image, target_type, whitelist) == \
            read_with_a_fresh_instance(image, target_type, whitelist), (target_type, whitelist)


def test_a_whitelist_does_not_carry_over_to_the_next_action():
    image = text_image('Stamina Potion (20)', 2, True)

    digits_only = read_with_the_shared_instance(image, 'sentence', '0123456789')
    unrestricted = read_with_the_shared_instance(image, 'sentence', '')

    assert not any(character.isalpha() for character in digits_only)
    assert 'Stamina' in unrestricted


def test_the_model_is_loaded_once_per_process(monkeypatch):
    built = []
    real_api = tesserocr.PyTessBaseAPI

    def counting_api(*args, **kwargs):
        built.append(kwargs)
        return real_api(*args, **kwargs)

    monkeypatch.setattr(tesserocr, 'PyTessBaseAPI', counting_api)
    image = text_image('Deep Lode', 2, False)

    for target_type, whitelist in SETTINGS * 3:
        read_with_the_shared_instance(image, target_type, whitelist)

    assert len(built) == 1


def test_a_shared_instance_is_faster(capsys):
    image = text_image('Healing Speed Up (5Min)', 2, True)
    read_with_the_shared_instance(image, 'sentence', '')

    def time_of(read, calls=10):
        started = time.perf_counter()
        for _ in range(calls):
            read(image, 'sentence', '')
        return (time.perf_counter() - started) / calls

    fresh = time_of(read_with_a_fresh_instance)
    shared = time_of(read_with_the_shared_instance)
    with capsys.disabled():
        print('\nOCR per call: fresh instance {:.0f} ms, shared instance {:.0f} ms'.format(fresh * 1000, shared * 1000))

    assert shared < fresh
