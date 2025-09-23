# ScriptEngine

ScriptEngine is a powerful automation framework and backend engine for ScreenPlan Scripts (https://screenplan.io). It provides cross-platform device automation capabilities with support for desktop computers, Android devices and PiKVM systems.

## Features

### 🎯 Multi-Platform Device Support
- **Desktop Automation**: Windows and macOS support via PyAutoGUI
- **Android Devices**: ADB-based automation for Android phones, tablets, and emulators (BlueStacks, AVD)
- **PiKVM**: Remote device control via PiKVM systems

### 🤖 Advanced Computer Vision
- **Object Detection**: Template matching and feature-based object detection
- **Image Processing**: OpenCV-powered image analysis and manipulation
- **OCR Support**: Text extraction using Tesseract and EasyOCR

### 🔧 Rich Action Library
- **Mouse Actions**: Click, drag, scroll, and smooth movement
- **Keyboard Actions**: Key press, hotkeys, and text input
- **Device Control**: Screenshot, device initialization, and status monitoring
- **Shell Scripts**: Execute system commands and scripts
- **File Operations**: JSON file handling and data persistence
- **User Secrets**: Secure credential management
- **Conditional Logic**: Branching and control flow
- **Variable Management**: Dynamic state and variable assignment

### 📊 Comprehensive Logging
- **Action Logging**: Detailed execution logs for each action
- **Screenshot Capture**: Automatic screenshot logging
- **Error Handling**: Robust error reporting and recovery

## Installation

### Prerequisites

1. **Python 3.8+** installed on your system
2. **ADB (Android Debug Bridge)** for Android device support
3. **Platform-specific dependencies** (see below)

### Platform-Specific Setup (Only if using imageToTextAction with tesseractOCR as the parser)

#### Windows
```bash
# Install Tesseract OCR
# Download from: https://github.com/UB-Mannheim/tesseract/wiki

# Install TesserOCR wheel
pip install tesserocr-2.7.1-cp311-cp311-win_amd64.whl

# Install ADB
# Download from: https://developer.android.com/tools/releases/platform-tools
```

#### macOS
```bash
# Install Tesseract via Homebrew
brew install tesseract

# Settings Flags may be nescessary
CFLAGS="-I/opt/homebrew/include -I/opt/homebrew/Cellar/leptonica/1.83.1/include" \
LDFLAGS="-L/opt/homebrew/lib -L/opt/homebrew/Cellar/leptonica/1.83.1/lib" \

# Install tesseract in virtualenv
pip install --no-cache-dir tesserocr==2.6.0
```

#### Linux
```bash
# Install Tesseract
sudo apt-get install tesseract-ocr

# Install TesserOCR
pip install tesserocr
```

### Installation Steps

1. **Clone the repository**:
   ```bash
   git clone https://github.com/takhogan/ScriptEngine.git
   cd ScriptEngine
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r setup/venv_requirements.txt
   ```

## Usage

### Basic Usage

Run a script using the script manager:

```bash
python ScriptEngine/script_manager.py --script-name my_script
```

### Command Line Options

```bash
python ScriptEngine/script_manager.py [OPTIONS]

Options:
  --script-name TEXT     Name of the script to execute
  --script-id TEXT       Unique identifier for the script execution
  --timeout INTEGER      Script timeout in seconds
  --device-details TEXT  Device configuration JSON
  --constants TEXT       Script constants JSON
  --start-time TEXT      Script start time
  --system-script        Run as system script
  --screen-plan-server   Enable ScriptActions that require the ScreenPlan.io server
```

### Script Structure

Scripts are organized in the `scripts/` directory with the following structure:

```
scripts/
└── scriptLibrary/          # User-created scripts
    └── MyScript/
        ├── actions/        # Action definitions
        ├── include/        # Included sub-scripts
        └── scriptAssets/   # Script resources
```

### Example Script Actions

#### Mouse Actions
```json
{
  "actionName": "clickAction",
  "actionData": {
    "targetSystem": "desktop",
    "clickType": "leftClick",
    "x": 100,
    "y": 200
  }
}
```

#### Object Detection
```json
{
  "actionName": "detectObject",
  "actionData": {
    "targetSystem": "desktop",
    "detectActionType": "detectAndClick",
    "positiveExamples": ["button.png"],
    "negativeExamples": ["not_button.png"]
  }
}
```

#### Keyboard Input
```json
{
  "actionName": "keyboardAction",
  "actionData": {
    "targetSystem": "desktop",
    "keyboardActionType": "keyPress",
    "keyboardExpression": "Hello World"
  }
}
```

#### Android Device Control
```json
{
  "actionName": "adbAction",
  "actionData": {
    "targetSystem": "android",
    "adbActionType": "tap",
    "x": 500,
    "y": 1000
  }
}
```
## Development

### Building from Source

1. **Install build dependencies**:
   ```bash
   pip install pyinstaller
   ```

2. **Run build command**:
   ```bash
   ./runBuild.sh # ./runBuild.cmd on windows
   ```

### Project Structure

```
ScriptEngine/
└── ScriptEngine/              # Core engine modules
    ├── managers/              # Device managers
    ├── helpers/               # Action helpers
    ├── common/                # Shared utilities
    └── clients/               # API clients
```

## API Reference

### Core Classes

- **`ScriptExecutor`**: Main script execution engine
- **`DeviceController`**: Device abstraction layer
- **`ScriptActionExecutor`**: Action execution handler
- **`ParallelizedScriptExecutor`**: Parallel execution manager

### Device Managers

- **`DesktopDeviceManager`**: Desktop automation
- **`ADBDeviceManager`**: Android device control
- **`PiKVMDeviceManager`**: PiKVM remote control

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

This project is licensed under the GNU General Public License v3 (GPLv3) - see the LICENSE file for details.

## Support

- **Documentation**: https://screenplan.io/help
- **Issues**: https://github.com/takhogan/ScriptEngine/issues

## Changelog

### Version 1.0.0
- Initial release
- Multi-platform device support
- Advanced computer vision capabilities
- Parallel execution engine
- Comprehensive logging system