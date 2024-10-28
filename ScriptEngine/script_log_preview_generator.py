import cv2
import sys
import json
import numpy as np

sys.path.append("..")


class ScriptLogPreviewGenerator:
    def __init__(self):
        pass


    @staticmethod
    def assemble_script_log_tree(child_obj):
        action_log_dict = None
        with open(child_obj['action_log_path'], 'r') as action_log_file:
            action_log_dict = json.load(action_log_file)
        if action_log_dict is not None:
            child_obj.update(action_log_dict)
            for child in action_log_dict['children']:
                ScriptLogPreviewGenerator.assemble_script_log_tree(child)

    @staticmethod
    def log_tree_to_image_list(log_tree, image_list):
        if log_tree['name'].startswith('detectObject') or\
            log_tree['name'].startswith('clickAction') or\
            log_tree['name'].startswith('dragLocationSource') or\
            log_tree['name'].startswith('dragLocationTarget') or\
            log_tree['name'].startswith('mouseScrollAction'):
            if "file_path" in log_tree['post_file']:
                image_list.append({
                    'script_name': log_tree['base_path'].split('/')[-2],
                    'action_name': log_tree['name'],
                    'post_file': log_tree['post_file']['file_path']
                })
        for child in log_tree['children']:
            ScriptLogPreviewGenerator.log_tree_to_image_list(child, image_list)

    @staticmethod
    def overlay_text(image, text, position, font=cv2.FONT_HERSHEY_SIMPLEX, font_scale=1, color=(255, 255, 255),
                     thickness=2):
        """Overlay text onto the image at the given position."""
        cv2.putText(image, text, position, font, font_scale, color, thickness)

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
    def images_to_video(image_paths, output_path, fps=30, codec="H264"):
        # Read the first image to get the width and height
        first_image = cv2.imread(image_paths[0]['post_file'])

        height, width, layers = first_image.shape

        # Define the codec and create VideoWriter object
        if codec == "H264":
            fourcc = cv2.VideoWriter_fourcc(*'H264')  # H.264 codec
            output_path += ".mp4"  # H.264 is commonly saved as .mp4
        else:
            fourcc = cv2.VideoWriter_fourcc(*'XVID')  # Fallback codec

        video = cv2.VideoWriter(output_path, fourcc, fps, (width, height))


        for image_path in image_paths:
            img = cv2.imread(image_path['post_file'])
            ScriptLogPreviewGenerator.overlay_text(img, image_path['script_name'], (50, 50))
            ScriptLogPreviewGenerator.overlay_text(img, image_path['action_name'], (50, 100))

            if img is None:
                print(f"Error reading {image_path}. Skipping.")
                continue
            img = ScriptLogPreviewGenerator.resize_with_padding(img, width, height)
            video.write(img)

        # Release everything when job is finished
        video.release()
        cv2.destroyAllWindows()

    @staticmethod
    def assemble_script_log_preview(action_log_path, output_path):
        log_tree = {
            'action_log_path': action_log_path
        }
        ScriptLogPreviewGenerator.assemble_script_log_tree(log_tree)
        image_list = []
        ScriptLogPreviewGenerator.log_tree_to_image_list(log_tree, image_list)
        # with open('./log_tree.json', 'w') as log_tree_file:
        #     json.dump(log_tree, log_tree_file)
        if len(image_list) > 0:
            ScriptLogPreviewGenerator.images_to_video(image_list, output_path, fps=2)

if __name__=='__main__':
    ScriptLogPreviewGenerator.assemble_script_log_preview(
        '/Users/takhogan/Documents/Script-Engine-Controller/logs/00000-DeviceToWaoLoadingScreen-2024-10-14 22-49-41/00001-scriptReference-0-action-log.json',
        'test'
    )
