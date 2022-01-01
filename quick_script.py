import pyautogui
import time
import subprocess
import pyperclip
import random

subprocess.Popen("cd /Applications;open \"Google Chrome.app\"", shell=True)
time.sleep(3)
for file_index in range(0, 137):
    print('file_index: ' + str(file_index))
    pyautogui.click(730,145)
    time.sleep(1)
    loaded = False
    max_retries = 20
    retries = 0

    # 260, 172, 32, 33, 36, 255
    while not loaded:
        # im = pyautogui.screenshot()
        pick_color = pyautogui.pixel(479, 348)

        print(pick_color)
        if pick_color.red == 218 and pick_color.green == 220 and pick_color.blue == 222:
            loaded = True
        retries += 1
        if retries > max_retries:
            pyautogui.screenshot('timeout-import-page.png')
            exit(0)
        time.sleep(1)


    pyautogui.click(468,350)
    time.sleep(1)
    pyautogui.click(504,281)
    time.sleep(1)
    pyautogui.press('down',presses=file_index,interval=0.25)
    time.sleep(0.5)
    pyautogui.press('enter')
    time.sleep(1)
    pyautogui.scroll(-200)
    time.sleep(1)
    pyautogui.click(1191,742)
    time.sleep(1)
    loaded = False
    max_retries = 50
    retries = 0
    print('part2')
    while not loaded:
        randomizer = random.randint(0,1000)
        # im = pyautogui.screenshot('completion' + str(randomizer) + '.png', region=(0,0,875,345))
        pick_color = pyautogui.pixel(875, 345)
        loaded = (pick_color.red == 235 and pick_color.green == 247 and pick_color.blue == 168)
        print(randomizer, end=' ')
        print(pick_color)
        retries += 1
        if retries > max_retries:
            pyautogui.screenshot('timeout.png')
            exit(0)
        time.sleep(1)