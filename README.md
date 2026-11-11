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
  --inputs-file PATH     A UTF-8 JSON object of {input name: value}: literal values,
                         never evaluated; a name also in --constants takes the file's value
  --approved-secrets [NAME ...]
                         Turn on the secret gate: a getSecret for a secret not named
                         stops the run with NEEDS_APPROVAL (no names: none may be read)
  --start-time TEXT      Script start time
  --system-script        Run as system script
  --screen-plan-server   Enable ScriptActions that require the ScreenPlan.io server
```

`python -m ScriptEngine.script_manager --help` lists every option.

### Run Inputs and Outputs

`--constants name:value` takes a Python expression per input (the controller
and ScriptScheduler pass `repr()`s). `--inputs-file` takes values instead: the
file is a JSON object, its values are assigned to the run's inputs as they are,
so a default input (`isDefault` in inputs.json) takes them like a caller's
value, and nothing in them is ever run as Python. A file that is not a JSON
object fails the run at start (exit code 1, the reason on stderr).

Each script's log folder gets `outputs.txt` (for people) and `outputs.json`
beside it, and the run's top-level folder (the one holding
`00001-scriptReference-0-action-log.json`) gets an `outputs.json` with the
outputs of the script that was run, however the run ended:

```json
{"version": 1, "outputs": {
  "path": {"type": "json", "value": "C:\\Users\\x\\a.txt"},
  "window": {"type": "repr", "value": "<Window 0x1a2b>"}
}}
```

A value is `json` when `json.dumps` takes it as it is, else its `repr`. A user
secret is never written as its value: it, and any list or dict holding one, is
a `repr`, which redacts it. The top-level file leaves out names with no value
(a run that stopped before its script returned has only what the top level
held).

### The Secret Gate

Without `--approved-secrets` every `getSecret` reads its secret. With it, a
`userSecretManagementAction` `getSecret` for a secret not on the list sends no
request and stops the run: the action's node and the root
`00001-scriptReference-0` node get status `NEEDS_APPROVAL`, the run folder gets
`needs_approval.json`:

```json
{"status": "NEEDS_APPROVAL", "secret": "vdi_password", "script": "VDI_SignIn", "action": "userSecretManagementAction-12"}
```

and the engine exits with code 3, writing no `errors.txt` and nothing to
stderr. Device passwords (a PiKVM's login) are not user secrets and are not
gated.

### Script Structure

Scripts are organized in the `scripts/` directory with the following structure:

```
scripts/
└── scriptLibrary/          # User-created scripts
    └── MyScript/
        ├── actionRows.json # Action definitions (interfaceVersion >= 21)
        ├── assets/         # Flat asset folder; files named
        │                   # {md5}-{actionName}-{actionGroup}-{specificFileName}.{ext}
        ├── include/        # Included sub-scripts
        └── tmp/            # Runtime jsonFileAction read/write target
                            # (formerly named scriptAssets/ — see legacy note)
```

Each `ScriptAction` carries an `actionAssets` array that registers the assets
it owns. Each entry has `path`, `attributePath` (where to place the loaded
value on the action), `assetType` (`image` | `json` | `pointList` | `text`),
and the file's `md5` so the writer can skip rehashing on subsequent saves.

Legacy scripts saved before `interfaceVersion` 21 use the old nested
`actions/N-row/M-{actionName}/assets/...` layout and the `scriptAssets/`
folder name. Both readers fall back to the old layout when `actionAssets` is
absent or `interfaceVersion < 21`.

### Script data: scriptAssets

Separate from the library folder, each script gets a data folder of its own in
the controller's data root: `scriptAssets/{workspace}/{scriptName}/`. The
engine creates it the first time a `dataPersistenceAction` (formerly
`fileIOAction`, a name that still runs) of that script resolves a relative
`filePath`: every relative path resolves under it, so a script finds the files
it wrote on its next run wherever the engine was started. The folder belongs
to the script that holds the action, not the one that called it, and an agent
branch workspace (`.Workspace1.branch1`) gets its own, apart from its base
workspace's. Absolute paths are used as given.

`dataPersistenceAction` reads and writes `image`, `text`, `json` and `sqlite`
files. For `sqlite`, `inputExpression` evaluates to the SQL to run (plain SQL
that is not a Python expression is used as written), or to
`{"query": ..., "params": ...}`; a write may also give
`{"table": ..., "values": {...} | [{...}, ...]}`, which inserts the rows and
creates the table, or adds a column it lacks, from their keys. A read stores
its rows, a list of dicts, in `outputVarName`; a write stores
`{"rowcount", "lastrowid"}`.

```json
{
  "actionName": "dataPersistenceAction",
  "actionData": {
    "targetSystem": "none",
    "fileType": "sqlite",
    "fileActionType": "w",
    "filePath": "'scores.db'",
    "inputExpression": "{'table': 'scores', 'values': {'name': player, 'score': score}}",
    "outputVarName": "scoreWrite"
  }
}
```

### Example Script Actions

#### Mouse Actions
```json
{
  "actionName": "clickAction",
  "actionData": {
    "targetSystem": "python",
    "inputExpression": "detectObject_0_output",
    "pointList": [],
    "clickCount": 1,
    "mouseButton": "left"
  }
}
```

#### Object Detection
```json
{
  "actionName": "detectObject",
  "actionData": {
    "targetSystem": "adb",
    "detectActionType": "floatingObject",
    "matchMode": "bestMatch",
    "threshold": "0.3",
    "inputExpression": "",
    "outputVarName": "detectObject_0_output",
    "positiveExamples": [
      {
        "type": "templateMatchImage",
        "floatingObject": {
          "detectType": "floatingObject",
          "pairIndex": 0,
          "img": "actions/0-row/0-detectObject/assets/detectTypeObject/positiveExamples/0-floatingObject-img.png",
          "mask": "actions/0-row/0-detectObject/assets/detectTypeObject/positiveExamples/0-floatingObject-mask.png",
          "containedAreaMask": "actions/0-row/0-detectObject/assets/detectTypeObject/positiveExamples/0-floatingObject-containedAreaMask.png",
          "icon": "actions/0-row/0-detectObject/assets/detectTypeObject/positiveExamples/0-floatingObject-icon.png",
          "centerPoint": [10.5, 10.5],
          "sourceScreenWidth": 1512,
          "sourceScreenHeight": 944
        },
        "fixedObject": {
          "detectType": "fixedObject",
          "pairIndex": 1,
          "img": "actions/0-row/0-detectObject/assets/detectTypeObject/positiveExamples/0-fixedObject-img.png",
          "mask": "actions/0-row/0-detectObject/assets/detectTypeObject/positiveExamples/0-fixedObject-mask.png",
          "containedAreaMask": "actions/0-row/0-detectObject/assets/detectTypeObject/positiveExamples/0-fixedObject-containedAreaMask.png",
          "icon": "actions/0-row/0-detectObject/assets/detectTypeObject/positiveExamples/0-fixedObject-icon.png",
          "centerPoint": [10.5, 10.5],
          "sourceScreenWidth": 1512,
          "sourceScreenHeight": 944
        }
      }
    ],
    "negativeExamples": []
  }
}
```

#### Keyboard Input
```json
{
  "actionName": "keyboardAction",
  "actionData": {
    "targetSystem": "python",
    "keyboardActionType": "keyPress",
    "keyboardExpression": "Hello World"
  }
}
```

On a PiKVM, text is typed exactly or not at all: it may hold printable ASCII,
tab and line breaks (`\r\n`, `\n` and a lone `\r` are each one Enter). A
character the keyboard has no key for, such as `é`, fails the action before any
key is sent, with the character and its position in the action's log.

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