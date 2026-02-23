import cv2
import numpy as np
import os
import datetime
import sys

from .script_log_tree_generator import ScriptLogTreeGenerator
bin_path = os.path.abspath("bin")
os.environ["PATH"] += os.pathsep + bin_path

class ScriptLogPreviewGenerator:
    def __init__(self):
        pass

    @staticmethod
    def log_tree_to_image_list(log_tree, image_list, last_image=None):
        # Check if this action should reuse the previous image
        if log_tree['name'].startswith('variableAssignment') or\
            log_tree['name'].startswith('sleepStatement') or\
            log_tree['name'].startswith('conditionalStatement') or\
            log_tree['name'].startswith('imageToTextAction'):
            if last_image is not None:
                # Reuse the previous image
                image_list.append({
                    'script_name': last_image['script_name'],
                    'action_name': log_tree['name'],
                    'post_file': last_image['post_file'],
                    'caption' : log_tree.get('summary', '') or '',
                    'start_time': log_tree.get('start_time', '')
                })
                # Update last_image to the newly added one (with new action_name)
                last_image = image_list[-1]
        elif log_tree['name'].startswith('detectObject') or\
            log_tree['name'].startswith('mouseInteractionAction') or\
            log_tree['name'].startswith('mouseMoveAction') or\
            log_tree['name'].startswith('sendMessageAction'):
            if "file_path" in log_tree['post_file']:
                image_list.append({
                    'script_name': log_tree['base_path'].split('/')[-2],
                    'action_name': log_tree['name'],
                    'post_file': log_tree['post_file']['file_path'],
                    'caption' : log_tree.get('summary', '') or '',
                    'start_time': log_tree.get('start_time', '')
                })
                # Update last_image to the newly added one
                last_image = image_list[-1]
        # Process children with the current last_image
        for child in log_tree.get('children', []):
            last_image = ScriptLogPreviewGenerator.log_tree_to_image_list(child, image_list, last_image)
        return last_image

    @staticmethod
    def wrap_text(text, max_chars):
        """Wrap text to fit within max_chars characters per line. Respects existing newlines."""
        if not text:
            return []
        
        all_lines = []
        # First split by newlines to respect existing line breaks
        paragraphs = text.split('\n')
        
        for paragraph in paragraphs:
            words = paragraph.split(' ')
            current_line = []
            current_length = 0
            
            for word in words:
                # Add 1 for space if not first word
                word_length = len(word) + (1 if current_line else 0)
                
                if current_length + word_length <= max_chars or len(current_line) == 0:
                    # Word fits or it's the first word (must add it even if too long)
                    current_line.append(word)
                    current_length += word_length
                else:
                    # Current line is full, start a new line
                    all_lines.append(' '.join(current_line))
                    current_line = [word]
                    current_length = len(word)
            
            # Add the last line of the paragraph
            if current_line:
                all_lines.append(' '.join(current_line))
        
        return all_lines

    @staticmethod
    def overlay_text(image, text, position, font=cv2.FONT_HERSHEY_SIMPLEX, font_scale=1, color=(255, 255, 255),
                     thickness=2, max_chars=None, outline=True):
        """Overlay text onto the image at the given position. If max_chars is provided, wrap text to fit.
        Also handles newlines in the text. If outline is True, draws black outline around white text."""
        if max_chars is not None:
            # Wrap text and display multiple lines
            lines = ScriptLogPreviewGenerator.wrap_text(text, max_chars)
        elif '\n' in text:
            # Text contains newlines, split and display each line
            lines = text.split('\n')
        else:
            # Single line text
            if outline:
                # Draw black outline first with larger thickness
                outline_color = (0, 0, 0)
                outline_thickness = thickness + 3
                cv2.putText(image, text, position, font, font_scale, outline_color, outline_thickness)
            cv2.putText(image, text, position, font, font_scale, color, thickness)
            return
        
        # Display multiple lines
        (_, line_height), _ = cv2.getTextSize('M', font, font_scale, thickness)
        line_spacing = int(line_height * 1.2)  # 20% spacing between lines
        
        for i, line in enumerate(lines):
            y = position[1] + (i * line_spacing)
            if outline:
                # Draw black outline first with larger thickness
                outline_color = (0, 0, 0)
                outline_thickness = thickness + 3
                cv2.putText(image, line, (position[0], y), font, font_scale, outline_color, outline_thickness)
            cv2.putText(image, line, (position[0], y), font, font_scale, color, thickness)

    @staticmethod
    def resize_with_padding(image, target_width, target_height):
        """
        Resize an image while keeping the aspect ratio intact. Add padding if necessary to match the target dimensions.
        """
        height, width = image.shape[:2]

        if target_width == width and target_height == height:
            return image

        aspect_ratio_image = width / height
        aspect_ratio_target = target_width / target_height

        if aspect_ratio_image > aspect_ratio_target:
            # Image is wider than the target: resize based on width
            new_width = target_width
            new_height = int(target_width / aspect_ratio_image)
        else:
            # Image is taller than the target: resize based on height
            new_height = target_height
            new_width = int(target_height * aspect_ratio_image)

        # Resize the image to the new dimensions
        resized_image = cv2.resize(image, (new_width, new_height))

        # Create a black canvas for the target size
        canvas = np.zeros((target_height, target_width, 3), dtype=np.uint8)

        canvas[0:new_height, 0:new_width] = resized_image

        return canvas

    @staticmethod
    def parse_start_time(start_time_str):
        """Parse start_time string to datetime object."""
        try:
            # Format: "%Y-%m-%d %H:%M:%S.%f"
            return datetime.datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S.%f")
        except (ValueError, TypeError):
            return None

    @staticmethod
    def images_to_video(image_paths, output_path, fps=30, realtime=False):
        # Read the first image to get the width and height
        first_image = cv2.imread(image_paths[0]['post_file'])

        height, width, layers = first_image.shape

        # avc1 is the MP4-friendly H.264 tag; 'H264' triggers fallback warnings on some builds
        fourcc = cv2.VideoWriter_fourcc(*'avc1')
        video = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        if not video.isOpened():
            raise RuntimeError(f"Failed to open VideoWriter for {output_path}")

        if realtime:
            # Real-time mode: calculate frame durations based on start_time
            for i, image_path in enumerate(image_paths):
                img = cv2.imread(image_path['post_file'])

                if img is None:
                    print(f"Error reading {image_path}. Skipping.", file=sys.stderr)
                    continue
                img = ScriptLogPreviewGenerator.resize_with_padding(img, width, height)
                
                ScriptLogPreviewGenerator.overlay_text(img, image_path['script_name'], (50, 50))
                ScriptLogPreviewGenerator.overlay_text(img, image_path['action_name'], (50, 100))
                # Wrap caption text at 80 characters per line
                caption_text = image_path.get('caption', '') or ''
                ScriptLogPreviewGenerator.overlay_text(img, caption_text, (50, 150), max_chars=70)
                
                # Calculate duration for this frame
                current_start_time = ScriptLogPreviewGenerator.parse_start_time(image_path.get('start_time', ''))
                
                if i < len(image_paths) - 1:
                    # Calculate time until next action starts
                    next_start_time = ScriptLogPreviewGenerator.parse_start_time(image_paths[i + 1].get('start_time', ''))
                    if current_start_time and next_start_time:
                        duration_seconds = (next_start_time - current_start_time).total_seconds()
                        # Ensure minimum duration of 1 frame
                        duration_seconds = max(duration_seconds, 1.0 / fps)
                    else:
                        # Fallback: use default duration if parsing fails
                        duration_seconds = 1.0
                else:
                    # Last frame: display for a default duration
                    duration_seconds = 2.0
                
                # Calculate number of frames to write
                num_frames = int(duration_seconds * fps)
                
                # Write the frame multiple times to achieve the duration
                for _ in range(num_frames):
                    video.write(img)
        else:
            # Regular mode: each image appears once
            for image_path in image_paths:
                img = cv2.imread(image_path['post_file'])

                if img is None:
                    print(f"Error reading {image_path}. Skipping.", file=sys.stderr)
                    continue
                img = ScriptLogPreviewGenerator.resize_with_padding(img, width, height)
                
                ScriptLogPreviewGenerator.overlay_text(img, image_path['script_name'], (50, 50))
                ScriptLogPreviewGenerator.overlay_text(img, image_path['action_name'], (50, 100))
                # Wrap caption text at 80 characters per line
                caption_text = image_path.get('caption', '') or ''
                ScriptLogPreviewGenerator.overlay_text(img, caption_text, (50, 150), max_chars=70)
                
                video.write(img)

        # Release everything when job is finished
        video.release()

    @staticmethod
    def assemble_script_log_preview(action_log_path, output_path, realtime=False):
        log_tree = {
            'action_log_path': action_log_path
        }
        ScriptLogTreeGenerator.assemble_script_log_tree(log_tree)
        image_list = []
        ScriptLogPreviewGenerator.log_tree_to_image_list(log_tree, image_list)
        if len(image_list) > 0:
            # Always generate the regular video
            ScriptLogPreviewGenerator.images_to_video(image_list, output_path, fps=2)
            
            # If realtime is specified, also generate the realtime video
            if realtime:
                # Generate realtime video with modified filename
                base_name, ext = os.path.splitext(output_path)
                realtime_output_path = f"{base_name}_realtime{ext}"
                # For real-time mode, use higher FPS for smoother playback
                ScriptLogPreviewGenerator.images_to_video(image_list, realtime_output_path, fps=30, realtime=True)

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Script Log Preview Generator')
    parser.add_argument('action_log_path', help='Path to action log file')
    parser.add_argument('output_file_name', help='Output file name')
    parser.add_argument('--realtime', action='store_true', default=True, help='Additionally generate real-time video based on start_time')
    args = parser.parse_args()
    
    # print('Running ScriptLogPreviewGenerator with args', args.action_log_path, args.output_file_name, '--realtime' if args.realtime else '')
    ScriptLogPreviewGenerator.assemble_script_log_preview(
        args.action_log_path,
        args.output_file_name,
        realtime=args.realtime
    )

if __name__ == '__main__':
    main()
