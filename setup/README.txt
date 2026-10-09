##1. Run python setup/setup.py from the main ScriptEngine directory

This creates the venvs and also installs tesserocr + Tesseract language data into the script venv
(see setup/setup_tesseract.py).

#On Windows:
Nothing extra needed. setup_tesseract.py installs the prebuilt tesserocr wheel matching the venv's
Python version from https://github.com/simonflueckiger/tesserocr-windows_build/releases
and downloads eng.traineddata into <ScriptEngine>/tessdata.
If a newer Python version has no wheel in the pinned release, bump TESSEROCR_WINDOWS_RELEASE in setup_tesseract.py.

To repair an existing venv without recreating it (e.g. "No module named 'tesserocr'"):
python setup/setup_tesseract.py

#On Mac:
Install Tesseract first (brew install tesseract). If the tesserocr build fails, try specifying the
path to the library and/or install an earlier version:
CFLAGS="-I/opt/homebrew/include -I/opt/homebrew/Cellar/leptonica/1.83.1/include" LDFLAGS="-L/opt/homebrew/lib -L/opt/homebrew/Cellar/leptonica/1.83.1/lib" pip install --no-cache-dir tesserocr==2.6.0

#On Linux:
sudo apt-get install tesseract-ocr libtesseract-dev libleptonica-dev

##2. ADB should be installed and added to path
https://developer.android.com/tools/releases/platform-tools
