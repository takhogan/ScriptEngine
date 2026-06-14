import numpy as np
import cv2

from ScriptEngine.common.logging.script_logger import ScriptLogger, thread_local_storage
script_logger = ScriptLogger()


class ImageToTextActionHelper:
    def __init__(self):
        pass

    @staticmethod
    def preprocess_image(action, search_im):
        pre_log = 'Image Transformations:\n'

        image_to_text_input = cv2.cvtColor(search_im.copy(), cv2.COLOR_BGR2GRAY)
        conversion_log = 'converted to grayscale'
        script_logger.log(conversion_log)
        pre_log += conversion_log + '\n'

        if action["actionData"]["increaseContrast"]:
            image_to_text_input = cv2.equalizeHist(image_to_text_input)
            conversion_log = 'increased contrast'
            script_logger.log(conversion_log)
            pre_log += conversion_log + '\n'

        if action["actionData"]["invertColors"]:
            image_to_text_input = cv2.bitwise_not(image_to_text_input)
            conversion_log = 'inverted colors'
            script_logger.log(conversion_log)
            pre_log += conversion_log + '\n'

        im_height = image_to_text_input.shape[0]
        if im_height < 50:
            image_to_text_input = cv2.resize(image_to_text_input, None, fx=int(100 / im_height), fy=int(100 / im_height), interpolation=cv2.INTER_CUBIC)
            conversion_log = 'input too small, boosted size by factor of {}'.format(int(100 / im_height))
            script_logger.log(conversion_log)
            pre_log += conversion_log + '\n'
        if 'blur' in action['actionData']:
            if action["actionData"]["blur"] == 'bilateralFilter':
                image_to_text_input = cv2.bilateralFilter(image_to_text_input, 5, 75, 75)
                conversion_log = 'applied bilateral filter'
                script_logger.log(conversion_log)
                pre_log += conversion_log + '\n'
            elif action["actionData"]["blur"] == 'medianBlur':
                image_to_text_input = cv2.medianBlur(image_to_text_input, 3)
                conversion_log = 'applied median blur'
                script_logger.log(conversion_log)
                pre_log += conversion_log + '\n'
            elif action["actionData"]["blur"] == 'gaussianBlur':
                image_to_text_input = cv2.GaussianBlur(image_to_text_input, (5, 5), 0)
                conversion_log = 'applied gaussian blur'
                script_logger.log(conversion_log)
                pre_log += conversion_log + '\n'
        if 'binarize' in action['actionData']:
            if action["actionData"]["binarize"] == 'regular':
                image_to_text_input = cv2.threshold(
                    image_to_text_input,
                    0,
                    255,
                    cv2.THRESH_BINARY + cv2.THRESH_OTSU
                )[1]
                conversion_log = 'applied regular binarization'
                script_logger.log(conversion_log)
                pre_log += conversion_log + '\n'
            elif action["actionData"]["binarize"] == 'adaptive':
                image_to_text_input = cv2.adaptiveThreshold(
                    image_to_text_input,
                    255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY,
                    31,
                    2
                )
                conversion_log = 'applied adaptive binarization'
                script_logger.log(conversion_log)
                pre_log += conversion_log + '\n'
        if 'makeBorder' in action['actionData'] and (
                action['actionData']['makeBorder'] == True or
                action['actionData']['makeBorder'] == 'true'
            ):
            if len(image_to_text_input.shape) == 2:
                border_color = int(image_to_text_input[0, 0])
            else:
                border_color = list(map(int, image_to_text_input[0,0][::-1]))
            # Add a 2-pixel border to the image
            image_to_text_input = cv2.copyMakeBorder(
                image_to_text_input, 2, 2, 2, 2,
                cv2.BORDER_CONSTANT, value=border_color
            )
            conversion_log = 'added border'
            script_logger.log(conversion_log)
            pre_log += conversion_log + '\n'

        return image_to_text_input, pre_log

    @staticmethod
    def run_tesseract_ocr(action, image_to_text_input, is_image_to_text_debug_mode):
        TARGET_TYPE_TO_PSM = {
            'word': '8',
            'sentence': '7',
            'page': '3',
            'character': '10',
            'rawLine': '13'
        }
        PSM_TO_TARGET_TYPE = {
            value: key for key, value in TARGET_TYPE_TO_PSM.items()
        }

        tesseract_params = [
            [
                TARGET_TYPE_TO_PSM[action['actionData']['targetType']],
                str(action["actionData"]["characterWhiteList"])
            ]
        ]
        if is_image_to_text_debug_mode:
            psm_values = list(TARGET_TYPE_TO_PSM.values())
            psm_values.remove(TARGET_TYPE_TO_PSM[action['actionData']['targetType']])
            tesseract_params = tesseract_params + [
                [
                    psm_val,
                    str(action["actionData"]["characterWhiteList"])
                ] for psm_val in psm_values
            ]

        outputs = []
        inputs_log = ''
        import tesserocr 
        from PIL import Image
        for [psm_value, character_white_list] in tesseract_params:
            with tesserocr.PyTessBaseAPI() as api:
                api.SetImage(Image.fromarray(image_to_text_input))
                api.SetPageSegMode(int(psm_value))
                if len(character_white_list) > 0:
                    api.SetVariable("tessedit_char_whitelist", character_white_list)
                # may want to consider bgr to rgb conversion
                output_text = api.GetUTF8Text().strip()
                outputs.append(output_text)
                input_result_log = 'Running with psm {} ({}) characterWhiteList {}'.format(
                    psm_value,
                    PSM_TO_TARGET_TYPE[psm_value],
                    character_white_list if len(character_white_list) > 0 else 'none'
                ) + ' and output was: {}'.format(output_text)
                script_logger.log(input_result_log)
                inputs_log += input_result_log +'\n'

        post_log = ''

        if is_image_to_text_debug_mode:
            for output_index, debug_output in enumerate(outputs[1:]):
                post_log += '\n' + 'final debug output for psm {} was:{}'.format(
                    tesseract_params[output_index + 1][0],
                    debug_output
                )
        return outputs, inputs_log, post_log

    @staticmethod
    def run_easy_ocr(action, image_to_text_input, easy_ocr_reader):
        import easyocr 
        post_log = ''
        inputs_log = ''

        if easy_ocr_reader is None:
            script_logger.log('initializing easyOCR model...')
            easy_ocr_reader = easyocr.Reader(['en'], verbose=False)
            script_logger.log('easyOCR model initialized')

        script_logger.log('parsing text from image...')
        results = easy_ocr_reader.readtext(image_to_text_input)

        # Get character whitelist from action data
        character_white_list = str(action["actionData"]["characterWhiteList"])

        outputs = [[]]

        for bbox, text, confidence in results:
            if confidence < 0.75:
                continue
            script_logger.log(f"Detected word: {text}")
            script_logger.log(f"Bounding box: {bbox}")
            script_logger.log(f"Confidence: {confidence}\n")
            outputs[0].append(text)

        # Join all detected text first
        outputs[0] = ' '.join(outputs[0])

        # Apply character whitelist filter to the final output if specified
        if len(character_white_list) > 0:
            original_output = outputs[0]
            outputs[0] = ''.join(char for char in outputs[0] if char in character_white_list)
            script_logger.log(f"Applied character whitelist '{character_white_list}' to output: '{original_output}' -> '{outputs[0]}'")

        input_results_log = 'Running easyOCR model with characterWhiteList {} and output was '.format(
            character_white_list if len(character_white_list) > 0 else 'none'
        ) + outputs[0]
        inputs_log += input_results_log + '\n'

        return outputs, inputs_log, post_log, easy_ocr_reader

    @staticmethod
    def handle_image_to_text(action, input_obj, state, io_executor, easy_ocr_reader):
        search_im = input_obj['screencap_im_bgr']
        pre_image_relative_path = 'imageToTextAction-raw-input.png'
        cv2.imwrite(script_logger.get_log_path_prefix() + pre_image_relative_path, search_im)
        script_logger.get_action_log().set_pre_file('image', pre_image_relative_path)

        image_to_text_input, pre_log = ImageToTextActionHelper.preprocess_image(
            action, search_im
        )

        is_image_to_text_debug_mode = "runMode" in action["actionData"] and action["actionData"][
            "runMode"] == "debug"

        if action["actionData"]["conversionEngine"] == "tesseractOCR":
            outputs, inputs_log, post_log = ImageToTextActionHelper.run_tesseract_ocr(
                action, image_to_text_input, is_image_to_text_debug_mode
            )
        elif action["actionData"]["conversionEngine"] == "easyOCR":
            outputs, inputs_log, post_log, easy_ocr_reader = ImageToTextActionHelper.run_easy_ocr(
                action, image_to_text_input, easy_ocr_reader
            )
        else:
            raise Exception('Unsupported OCR engine' + action["actionData"]["conversionEngine"])
        post_log += '\n final primary output was:{}'.format(
            outputs[0]
        )

        script_logger.log(post_log)
        script_logger.get_action_log().add_supporting_file(
            'text',
            'imageToText-results.txt',
            pre_log + '\n' + inputs_log + '\n' + post_log
        )
        extracted_text = outputs[0].strip()
        state[action["actionData"]["outputVarName"]] = extracted_text
        # Create summary: truncate text if too long
        if len(extracted_text) > 50:
            summary_text = extracted_text[:47] + '...'
        else:
            summary_text = extracted_text
        script_logger.get_action_log().set_summary("extracted text: '{}'".format(summary_text))

        parsed_input_relative_path = 'imageToTextAction-parsed-input.png'
        parsed_input_script_logger = script_logger.copy()
        io_executor.submit(
            ImageToTextActionHelper.create_parsed_input_post_image,
            parsed_input_script_logger,
            image_to_text_input.copy(),
            extracted_text,
            parsed_input_relative_path
        )

        return easy_ocr_reader

    @staticmethod
    def create_parsed_input_post_image(
        thread_script_logger, parsed_input_image, extracted_text, parsed_input_relative_path
    ):
        thread_local_storage.script_logger = thread_script_logger
        thread_logger = ScriptLogger.get_logger()
        try:
            if len(parsed_input_image.shape) == 2:
                overlay_im = cv2.cvtColor(parsed_input_image, cv2.COLOR_GRAY2BGR)
            else:
                overlay_im = parsed_input_image.copy()

            height, width = overlay_im.shape[:2]
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = max(0.4, min(1.0, width / 600))
            thickness = 1
            line_height = int(30 * font_scale) + 10
            display_text = 'result: ' + (extracted_text if len(extracted_text) > 0 else '<no text detected>')

            # Wrap the OCR'd text to fit the image width
            lines = []
            current_line = ''
            for word in display_text.split(' '):
                candidate = word if current_line == '' else current_line + ' ' + word
                (candidate_width, _), _ = cv2.getTextSize(candidate, font, font_scale, thickness)
                if candidate_width > width - 20 and current_line != '':
                    lines.append(current_line)
                    current_line = word
                else:
                    current_line = candidate
            if current_line != '':
                lines.append(current_line)

            banner_height = line_height * len(lines) + 10
            banner = np.full((banner_height, width, 3), 255, dtype=np.uint8)
            text_y = line_height
            for line in lines:
                cv2.putText(banner, line, (10, text_y), font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)
                text_y += line_height

            overlay_im = np.vstack([overlay_im, banner])

            cv2.imwrite(thread_logger.get_log_path_prefix() + parsed_input_relative_path, overlay_im)
            thread_logger.get_action_log().set_post_file('image', parsed_input_relative_path)
        except Exception as e:
            thread_logger.log('Error creating imageToTextAction parsed input image: ' + str(e))
