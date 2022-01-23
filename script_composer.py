import cv2
import numpy as np
import pandas as pd
import timeit
import json

'''
    Bring up a screen displaying an image of the first scene,
    ask if all the operations are on a subset of the screen
    
    if yes, ask user to label portion of the screen
    and crop image to fit that portion
    
    (for now assume no)
    take diff of each frame, graph diff sum

'''


def take_diff(last_frame, curr_frame):
     np.square(last_frame - curr_frame).sum() / last_frame.size


def initScript(recording):
    # recording = cv2.VideoCapture(video_filename)
    fps = int(recording.get(cv2.CAP_PROP_FPS))
    height = int(recording.get(cv2.CAP_PROP_FRAME_HEIGHT))
    width = int(recording.get(cv2.CAP_PROP_FRAME_WIDTH))
    n_frames: int = int(recording.get(cv2.CAP_PROP_FRAME_COUNT))
    print('fps: ', fps, '; height: ', height, '; width: ', width, '; n_frames: ', n_frames)
    print('total frames: ', n_frames)
    last_img = None
    diffs = np.zeros(n_frames, dtype=np.float32)
    for img_index in range(0, n_frames):
        if img_index % 100 == 0:
            print(img_index)

        success, img = recording.read()
        if last_img is not None and img is not None:
            diffs[img_index] = np.square(last_img - img).sum() / img.size

        last_img = img

    recording.release()

    diffs_json = pd.DataFrame(diffs).to_dict()
    diffs_json['fps'] = fps
    diffs_json['nFrames'] = n_frames
    diffs_json['height'] = height
    diffs_json['width'] = width

    with open('frameDiffData.json', 'w') as f_diff_data:
        json.dump(diffs_json, f_diff_data)
    np.save('diffs.npy', diffs)





# print('initScript')
# print(timeit.timeit(stmt=initScript, number=1))
# print('scikit_video_test')
# print(timeit.timeit(stmt=scikit_video_test, number=1))


if __name__=='__main__':
    video_filename = 'data/2022-01-20 22-24-42.mkv'
    # cv2.VideoCapture()
    initScript(cv2.VideoCapture(video_filename))


# make screen resolution editable in the settings of website