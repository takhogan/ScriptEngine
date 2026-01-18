from ScriptEngine.common.logging.script_logger import ScriptLogger,thread_local_storage
from ScriptEngine.clients.screenplan_api import ScreenPlanAPI, ScreenPlanAPIRequest
from ScriptEngine.common.constants.script_engine_constants import DETECT_OBJECT_RESULT_MARKER

script_logger = ScriptLogger()

class MessagingHelper:
    class SendMessageRequest:
        action: str
        messagingChannelName: str
        messagingProvider: str
        messageType: str

    def __init__(self):
        self.api = ScreenPlanAPI()

    def _serialize_image(self, image, index: int):
        """Serialize a screenplan image to JPEG bytes and return filename."""
        import cv2
        _, buffer = cv2.imencode('.jpg', image["matched_area"])
        image_bytes = buffer.tobytes()
        filename = f"image_{index}.jpg"
        return image_bytes, filename

    def _serialize_message(self, element, index: int = 0):
        """Serialize a single element into a list of MessageData objects and return image files."""
        image_files = []
        if isinstance(element, str):
            # If input is a string, set type to text
            return [{
                "type": "text",
                "content": element
            }], image_files
        elif isinstance(element, dict) and element.get(DETECT_OBJECT_RESULT_MARKER):
            # Single screenplan image
            image_bytes, filename = self._serialize_image(element, index)
            image_files.append((image_bytes, filename))
            return [{
                "type": "image",
                "images": [{"filename": filename}]
            }], image_files
        else:
            # All other cases - convert to string
            return [{
                "type": "text",
                "content": str(element)
            }], image_files

    def send_message(self, message_obj: "MessagingHelper.SendMessageRequest", message_pre_data):
        
        # Infer type from input structure
        all_image_files = []
        if isinstance(message_pre_data, list):
            # If input is a list, process each element individually to handle mixed types
            message_data = []
            for index, item in enumerate(message_pre_data):
                msg_data, img_files = self._serialize_message(item, index)
                message_data.extend(msg_data)
                all_image_files.extend(img_files)
        else:
            # Singular element - process directly
            message_data, img_files = self._serialize_message(message_pre_data, 0)
            all_image_files.extend(img_files)
        
        # type TextMessageData = {
        #     type: 'text';
        #     content: string;
        # };

        # type ImageMessageData = {
        #     type: 'image';
        #     images: string[];
        #     caption?: string; // Optional caption/text to accompany the image(s)
        # };

        # type MessageData = TextMessageData | HtmlMessageData | RichMessageData | ImageMessageData;

        message_obj["messageData"] = message_data
        
        # Prepare files for multipart/form-data
        files = None
        if all_image_files:
            # Convert image bytes to file tuples for requests library
            # Format: (field_name, (filename, file_bytes, content_type))
            files = []
            for idx, (image_bytes, filename) in enumerate(all_image_files):
                files.append((f'image_{idx}', (filename, image_bytes, 'image/jpeg')))
        
        request = ScreenPlanAPIRequest(
            request_id=None,
            method='POST',
            request_type='formData' if files else 'json',
            path='sendMessage',
            payload=message_obj,
            files=files
        )
        return self.api.send_request(request)

    def _render_text_to_image(self, text: str, max_width: int, text_padding: int):
        """
        Helper method to render text to a PIL Image with word wrapping.
        
        Args:
            text: Text string to render
            max_width: Maximum width for the text block
            text_padding: Padding around the text
        
        Returns:
            PIL Image with rendered text
        """
        from PIL import Image, ImageDraw, ImageFont
        # Use PIL's default font
        font = ImageFont.load_default()
        
        # Create a temporary image to measure text size
        temp_img = Image.new('RGB', (max_width, 100), color='white')
        temp_draw = ImageDraw.Draw(temp_img)
        
        # Wrap text to fit within max_width
        words = text.split(' ')
        lines = []
        current_line = []
        current_width = 0
        
        for word in words:
            word_width = temp_draw.textlength(word, font=font)
            if current_width + word_width + temp_draw.textlength(' ', font=font) <= max_width - 2 * text_padding:
                current_line.append(word)
                current_width += word_width + temp_draw.textlength(' ', font=font)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
                current_width = word_width
        
        if current_line:
            lines.append(' '.join(current_line))
        
        # Calculate text block dimensions
        line_height = temp_draw.textbbox((0, 0), "A", font=font)[3] - temp_draw.textbbox((0, 0), "A", font=font)[1]
        text_height = len(lines) * line_height + 2 * text_padding
        text_width = max_width
        
        # Create text image
        text_img = Image.new('RGB', (text_width, text_height), color='white')
        text_draw = ImageDraw.Draw(text_img)
        
        # Draw text lines
        y_offset = text_padding
        for line in lines:
            text_draw.text((text_padding, y_offset), line, fill='black', font=font)
            y_offset += line_height
        
        return text_img

    def _load_default_font_at_size(self, size: int):
        """
        Load a default font at the specified size.
        Tries to load a system font, falls back to PIL's default font if unavailable.
        
        Args:
            size: Font size in points
        
        Returns:
            PIL ImageFont object
        """
        from PIL import ImageFont
        try:
            # Try to load a common system font at specified size
            import platform
            if platform.system() == "Darwin":  # macOS
                return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
            else:
                # Try arial which is common on Windows/Linux
                return ImageFont.truetype("arial.ttf", size)
        except:
            # Fallback to default font (will be small, but simple)
            return ImageFont.load_default()

    def _render_h1_text_to_image(self, text: str, max_width: int, text_padding: int):
        """
        Helper method to render h1-style text to a PIL Image with word wrapping.
        Uses default font with extra padding to distinguish it as a header.
        
        Args:
            text: Text string to render
            max_width: Maximum width for the text block
            text_padding: Padding around the text
        
        Returns:
            PIL Image with rendered h1-style text
        """
        from PIL import Image, ImageDraw, ImageFont
        # Load default font at 24pt
        font = self._load_default_font_at_size(24)
        
        # Use extra padding for h1 header
        h1_padding = text_padding + 10
        
        # Create a temporary image to measure text size
        temp_img = Image.new('RGB', (max_width, 100), color='white')
        temp_draw = ImageDraw.Draw(temp_img)
        
        # Wrap text to fit within max_width
        words = text.split(' ')
        lines = []
        current_line = []
        current_width = 0
        
        for word in words:
            word_width = temp_draw.textlength(word, font=font)
            if current_width + word_width + temp_draw.textlength(' ', font=font) <= max_width - 2 * h1_padding:
                current_line.append(word)
                current_width += word_width + temp_draw.textlength(' ', font=font)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
                current_width = word_width
        
        if current_line:
            lines.append(' '.join(current_line))
        
        # Calculate text block dimensions
        line_height = temp_draw.textbbox((0, 0), "A", font=font)[3] - temp_draw.textbbox((0, 0), "A", font=font)[1]
        text_height = len(lines) * line_height + 2 * h1_padding
        text_width = max_width
        
        # Create text image
        text_img = Image.new('RGB', (text_width, text_height), color='white')
        text_draw = ImageDraw.Draw(text_img)
        
        # Draw text lines (h1 style - extra padding)
        y_offset = h1_padding
        for line in lines:
            text_draw.text((h1_padding, y_offset), line, fill='black', font=font)
            y_offset += line_height
        
        return text_img

    def create_log_image(self, message_pre_data, subject=None):
        """
        Create a composite image from message_pre_data (array of text/images or singular text/image).
        Elements are stacked vertically like an HTML block with <p> and <img> elements.
        If subject is provided, it will be rendered as an h1-style header at the top.
        
        Args:
            message_pre_data: Can be a list of elements, or a singular element (text string or image dict)
            subject: Optional subject string to render as h1 header at the top
        
        Returns:
            PIL Image object with all elements stacked vertically
        """
        from PIL import Image
        import cv2
        # Normalize input to a list
        if isinstance(message_pre_data, list):
            elements = message_pre_data
        else:
            elements = [message_pre_data]
        
        # Process each element and collect rendered components
        components = []
        padding = 10  # Padding between elements
        max_width = 800  # Maximum width for the output image
        text_padding = 15  # Padding around text
        
        # Add subject as h1 header at the top if provided
        if subject:
            subject_text = "subject: " + str(subject)
            if subject_text:
                h1_img = self._render_h1_text_to_image(subject_text, max_width, text_padding)
                components.append(h1_img)
        
        # Add "message: " label before message content if there are elements
        if elements:
            message_label_img = self._render_text_to_image("message: ", max_width, text_padding)
            components.append(message_label_img)
        
        for element in elements:
            if isinstance(element, str):
                # Text element - render as text
                text_img = self._render_text_to_image(element, max_width, text_padding)
                components.append(text_img)
                
            elif isinstance(element, dict) and element.get(DETECT_OBJECT_RESULT_MARKER):
                # Image element - convert cv2 BGR to PIL RGB
                matched_area = element["matched_area"]
                # Convert BGR to RGB
                if len(matched_area.shape) == 3:
                    matched_area_rgb = cv2.cvtColor(matched_area, cv2.COLOR_BGR2RGB)
                else:
                    matched_area_rgb = matched_area
                
                # Convert numpy array to PIL Image
                pil_image = Image.fromarray(matched_area_rgb)
                
                # Resize if too wide
                if pil_image.width > max_width:
                    ratio = max_width / pil_image.width
                    new_height = int(pil_image.height * ratio)
                    pil_image = pil_image.resize((max_width, new_height), Image.Resampling.LANCZOS)
                
                components.append(pil_image)
            else:
                # Other types - convert to string and render as text
                text_content = str(element)
                text_img = self._render_text_to_image(text_content, max_width, text_padding)
                components.append(text_img)
        
        if not components:
            # Return a blank white image if no components
            return Image.new('RGB', (max_width, 100), color='white')
        
        # Calculate total height and max width
        total_height = sum(comp.height for comp in components) + padding * (len(components) - 1)
        max_component_width = max(comp.width for comp in components) if components else max_width
        
        # Create composite image
        composite = Image.new('RGB', (max_component_width, total_height), color='white')
        y_position = 0
        
        for component in components:
            # Center component horizontally if it's narrower than max width
            x_offset = (max_component_width - component.width) // 2
            composite.paste(component, (x_offset, y_position))
            y_position += component.height + padding
        
        return composite

    def create_and_save_log_image(self, message_data, thread_script_logger, subject=None):
        """
        Create a log image from message_data and save it as the post file.
        This method is designed to be called asynchronously via io_executor.submit.
        
        Args:
            message_data: The message data (same format as message_pre_data for create_log_image)
            thread_script_logger: Thread-safe script logger instance
            subject: Optional subject string to render as h1 header at the top
        """
        thread_local_storage.script_logger = thread_script_logger
        script_logger = ScriptLogger.get_logger()
        
        try:
            script_logger.log('Creating log image for sendMessageAction')
            
            # Create the log image using messaging_helper
            log_image = self.create_log_image(message_data, subject=subject)
            
            # Convert PIL Image (RGB) to numpy array (BGR for cv2)
            import numpy as np
            import cv2
            image_array = np.array(log_image)
            # PIL Image is RGB, convert to BGR for cv2
            image_bgr = cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR)
            
            # Save the image
            post_image_relative_path = 'sendMessage-log.png'
            cv2.imwrite(script_logger.get_log_path_prefix() + post_image_relative_path, image_bgr)
            script_logger.log('Successfully created log image: ' + post_image_relative_path)
            
            # Set as post file
            script_logger.get_action_log().set_post_file('image', post_image_relative_path)
        except Exception as e:
            script_logger.log('Error creating sendMessage log image: ' + str(e))

