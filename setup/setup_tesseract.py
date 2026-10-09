import os
import subprocess
import sys
import urllib.request

# Prebuilt Windows wheels (tesserocr can't be built from source on Windows without a
# full Tesseract SDK). Bump this when a newer Python version needs a newer release.
TESSEROCR_WINDOWS_VERSION = '2.10.0'
TESSEROCR_WINDOWS_RELEASE = 'tesserocr-v2.10.0-tesseract-5.5.2'
TESSEROCR_WINDOWS_WHEEL_URL = (
    'https://github.com/simonflueckiger/tesserocr-windows_build/releases/download/'
    '{release}/tesserocr-{version}-{tag}.whl'
)

# Language data isn't bundled with the wheel; ImageToTextActionHelper looks for it in <repo>/tessdata
TESSDATA_LANGUAGES = ['eng']
TESSDATA_URL = 'https://github.com/tesseract-ocr/tessdata/raw/main/{lang}.traineddata'

is_windows = (os.name == 'nt')
setup_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(setup_dir)


def get_wheel_tag(env_python):
    # e.g. cp314-cp314-win_amd64, read from the venv's interpreter rather than the one running setup
    return subprocess.check_output([
        env_python, '-c',
        "import sys, sysconfig; v = 'cp{}{}'.format(*sys.version_info[:2]); "
        "print(v + '-' + v + '-' + sysconfig.get_platform().replace('-', '_'))"
    ]).decode('utf-8').strip()


def install_tesserocr(env_python):
    if is_windows:
        wheel_url = TESSEROCR_WINDOWS_WHEEL_URL.format(
            release=TESSEROCR_WINDOWS_RELEASE,
            version=TESSEROCR_WINDOWS_VERSION,
            tag=get_wheel_tag(env_python)
        )
        print(f'Installing tesserocr from {wheel_url}')
        subprocess.run([env_python, '-m', 'pip', 'install', wheel_url], check=True)
    else:
        # Builds against the system Tesseract (brew install tesseract / apt-get install tesseract-ocr libtesseract-dev)
        subprocess.run([env_python, '-m', 'pip', 'install', 'tesserocr'], check=True)


def install_tessdata():
    tessdata_dir = os.path.join(base_dir, 'tessdata')
    os.makedirs(tessdata_dir, exist_ok=True)
    for lang in TESSDATA_LANGUAGES:
        target = os.path.join(tessdata_dir, lang + '.traineddata')
        if os.path.isfile(target):
            print(f'{target} already exists')
            continue
        print(f'Downloading {lang}.traineddata to {tessdata_dir}')
        tmp_target = target + '.part'
        urllib.request.urlretrieve(TESSDATA_URL.format(lang=lang), tmp_target)
        os.replace(tmp_target, target)


def setup_tesseract(env_python):
    install_tesserocr(env_python)
    # Non-Windows tesserocr builds use the system Tesseract's tessdata
    tessdata_dir = ''
    if is_windows:
        install_tessdata()
        tessdata_dir = os.path.join(base_dir, 'tessdata')

    # Fail setup now rather than at the first imageToTextAction
    subprocess.run([
        env_python, '-c',
        'import sys, tesserocr; '
        'langs = tesserocr.get_languages(sys.argv[1]) if sys.argv[1] else tesserocr.get_languages(); '
        'print("tesserocr", tesserocr.__version__, "found languages", langs[1], "in", langs[0]); '
        'sys.exit(0 if "eng" in langs[1] else "eng.traineddata not found")',
        tessdata_dir
    ], check=True)


if __name__ == '__main__':
    # Standalone usage repairs an existing venv: python setup/setup_tesseract.py [path/to/venv]
    env_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(base_dir, 'venv')
    setup_tesseract(os.path.join(env_path, 'Scripts' if is_windows else 'bin', 'python'))
