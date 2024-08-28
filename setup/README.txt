##1. you need to install tessocr

Follow the steps here:
https://pypi.org/project/tesserocr/

#On Windows:
Installing via wheel is relatively painless
https://github.com/simonflueckiger/tesserocr-windows_build/releases
eg:
venv\Scripts\activate
pip install tesserocr-2.7.1-cp311-cp311-win_amd64.whl

You also need to install the tessdata
https://github.com/UB-Mannheim/tesseract/wiki

#On Mac:
If you run into any errors, try specifying the path to the library and/or try to install an earlier version

Example:
CFLAGS="-I/opt/homebrew/include -I/opt/homebrew/Cellar/leptonica/1.83.1/include" LDFLAGS="-L/opt/homebrew/lib -L/opt/homebrew/Cellar/leptonica/1.83.1/lib" pip install --no-cache-dir tesserocr==2.6.0

##2. Run python setup/setup.py from the main ScriptEngine directory

##3. ADB should be installed and added to path
https://developer.android.com/tools/releases/platform-tools