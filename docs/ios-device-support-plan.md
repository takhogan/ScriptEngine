# Adding iOS devices as a device type

Plan for making an iPhone/iPad a first-class device alongside `adb` and `kvm`.

Written against the current `master` of ScriptEngine, Script-Engine-Controller,
script-studio and screenplan-contracts.

**Status:** steps 1a, 1c and 1f are done. `IOSDeviceManager` is a complete
read-only manager, `ios` is wired through `device_controller.py`, and the
controller's `+ Add Device` → iOS device form now finds the attached phone
itself, checks every prerequisite of §4 and offers a button for each fix it can
apply — pairing, revealing the Developer Mode switch, and mounting the developer
disk image. `ScriptEngine/helpers/ios_setup_helper.py` holds the checks;
`src/iosSetup.mjs` and `renderer/iosSetup.js` are the controller's side.

1b is done too: the iOS 17+ tunnel now installs itself as a launchd daemon
through `SMAppService`, so **Set up tunnel** is a button like the others. §8 is
the design and what each file in it does. It needs a signed build, because macOS
validates the daemon against the app's signature — in a dev checkout the button
says so and names `sudo pymobiledevice3 remote tunneld` instead.

1d, 1e, 1g and 1h are done as well. A run's device is labelled by its own type
(1d). `ios` is in `SystemName` in both `screenplan-contracts` and the editor's
mirror in `screenplan-script-actions` (1e). The editor maps a device id to its
target system in one place, `deviceIdToTargetSystem()`, so an iPhone's actions
are stamped `ios` rather than falling through to `adb` (1g). A notarized build
was installed and run against a real iPhone: the frozen engine passes every
check and the frozen tunnel daemon opens a tunnel (1h). Two things only showed
up in the frozen build. Packages that read their own version at import time need
their dist-info bundled. And a root process cannot read the engine out of
`~/Documents`, so test it from where it ships.

Until phase 2, the editor flags any mouse action made for an iPhone (a ⚠️ on its
card, and the reason in its information panel), because the engine would only
fail it at run time.

Still open: all of phase 2 (WebDriverAgent input).

---

## 1. How a device type works today

Adding `adb` touches five layers. iOS has to touch the same five.

### 1.1 Discovery and registration (Script-Engine-Controller, Node)

- `src/initialize.mjs` → `collectHostDeviceData()` auto-discovers emulators at
  startup and emits records of the shape
  `{ deviceId, name, deviceName, type, ip, port, status }`. AVDs come from
  `emulator -list-avds` (`getHostAVDs`), BlueStacks from `bluestacks.conf`.
- Manual registration: `index.html` holds the `+ Add Device` dropdown
  (`pikvmOption`, `adbOption`) and one shared `deviceForm`;
  `renderer/devices.js` tracks a `deviceType` variable, shows/hides per-type
  field blocks in `updateFormFieldsForDeviceType()`, and sends `formData` over
  IPC as `addDeviceButtonClicked`.
- `src/index.mjs:275` routes that to `handleAddDevice()` in
  `src/clients/hostDataClient.mjs`, which mints
  `deviceId = ${type}:${hostSerialNumber}-${ip}[:${port}]`, stores PiKVM
  passwords through the secrets manager, calls `fetchDeviceApplications`, pushes
  the record to cloud `hostData`, and writes
  `host_devices_config.json` via `saveHostDevicesConfiguration`.

### 1.2 The long-lived device controller (Python)

`ScriptEngine/device_controller.py` is a process reading
`id###deviceKey###action args` lines from stdin.

- `device_id_to_device_type()` maps the `deviceId` prefix to a device type:
  no colon → `python`; `avd` / `bluestacks` / `adb` → `adb`; `pikvm` → `kvm`.
- `initialize_device()` is the factory: one `elif` per device type, importing
  the manager lazily and caching it in `self.devices`.
- `DEVICE_TYPES_REQUIRING_ATTACHMENT = ('adb', 'kvm')` decides which types
  raise the "no device attached to this run" error.
- `parse_inputs()` is the command surface the editor's live view uses:
  `check_status`, `screen_capture`, `click`, `click_and_drag`, `send_keys`,
  `list_applications`, `start_application`, `stop_application`.

### 1.3 Script runs (Python)

`ScriptEngine/script_manager.py` resolves `--device` against
`host_devices_config.json` into `device_params` and hands it to
`DeviceController`. Every action carries `actionData.targetSystem`, and
`script_action_executor.py` resolves the manager per action through
`device_controller.get_device_action(targetSystem, ...)`.

### 1.4 The manager contract

`ScriptEngine/managers/device_manager.py` declares 16 abstract methods:
`ensure_device_initialized`, `get_status`, `screenshot`, `key_down`, `key_up`,
`key_press`, `hotkey`, `mouse_down`, `mouse_up`, `smooth_move`, `click`,
`click_and_drag`, `scroll`, `start_device`, `stop_device`,
`list_applications`, `start_application`, `stop_application`.

Callers also depend on undeclared attributes, which are part of the real
contract:

- `width` / `height` — read via `get_device_attribute` by
  `script_action_executor.py` (lines 93, 158, 169).
- `dummy_mode` — read by `DeviceActionInterpreter.parse_keyboard_action`; every
  manager must expose it or keyboard actions throw.
- `input_source` / file mode — `script_manager.py` can pass a static image as
  the device (`file:` selections), and each manager short-circuits on
  `dummy_mode`.
- `screenshot()` must return a **BGR `numpy` array** (OpenCV convention), not
  PNG bytes — `device_controller.py` `imencode`s it and the matchers index it
  as `shape[1]`/`shape[0]`.

### 1.5 Contracts and the editor

- `packages/screenplan-contracts/screenplan_contracts_schemas/schemas/common.schema.json`
  defines `SystemName` as `["python", "adb", "kvm", "none"]`, generated into
  `screenplan-contracts-ts` (`src/_generated/common.ts`) and
  `screenplan-contracts-py`. Both are separate repos, pulled from GitHub by
  `setup.py`.
- script-studio maps a `deviceId` prefix to a target system in **three** places,
  each with `default: 'adb'`:
  - `src/app/editor/video-workspace/host-input-selector/host-input-selector.component.ts:122`
  - `src/app/editor/video-workspace/host-input-selector/host-device-interface/host-device-interface.component.ts:77`
  - `src/app/editor/video-workspace/video-workspace.component.ts:657`

---

## 2. What already exists for iOS

Two files, neither referenced from anywhere else in any repo:

**`ScriptEngine/managers/ios_device_manager.py`**
- Subclasses `DeviceManager` but implements only `take_screenshot`,
  `list_applications`, `start_application`, `stop_application` — the other 14
  abstract methods are missing, so the class **cannot be instantiated**
  (`TypeError` at construction).
- `__init__(self, sudo_client)` does not match the shape `DeviceController`
  constructs managers with (`props`, `device_params`, `input_source`).
- `take_screenshot()` returns the `Screenshot` *service object*, never calls
  `get_screenshot()`, and is named `take_screenshot` rather than `screenshot`.
- Uses `asyncio.run(async_get_tunneld_devices())` and grabs `rsds[0]` — no
  selection by UDID, so it cannot target a specific device.
- No `width`, `height`, `dummy_mode`, or `input_source`.

**`ScriptEngine/managers/pymobile_tunnel_server_manager.py`** *(since deleted —
replaced by `ScriptEngine/ios_tunnel_server.py`, §8)*
- `subprocess.Popen([self.tunneld_server.start()])` passes the return value of
  `Tunneld.start()` as an argv list — that is not a launch, and the whole
  object is constructed in-process anyway. Needs rewriting as either an
  in-process `Tunneld` or a supervised `pymobiledevice3 remote tunneld`
  subprocess, not both.

Nothing else mentions iOS: not `device_controller.py`, not `script_manager.py`,
not the controller UI, not the contracts, not `script_engine.spec`.

Good news: `pymobiledevice3 4.20.12` is already installed in `venv/`.

---

## 3. The one hard constraint: iOS has no `input tap`

This is the decision that shapes the whole plan.

`pymobiledevice3` gives us, with no extra tooling:

| Need | How |
| --- | --- |
| screenshot | `services/screenshot.py` (iOS < 17, `com.apple.mobile.screenshotr`) or `services/dvt/instruments/screenshot.py` (iOS 17+, over RSD) |
| list apps | `services/installation_proxy.py` |
| launch / kill app | `services/dvt/instruments/process_control.py` |
| device identity, OS version | `LockdownClient` properties |
| iOS 17+ transport | `remote/tunneld.py` + `tunneld/api.py` |
| port forwarding | `tcp_forwarder.py` (`UsbmuxTcpForwarder`, `LockdownTcpForwarder`) |
| run an XCUITest bundle | `services/dvt/testmanaged/xcuitest.py` (`XCUITestService`) |

What it does **not** give us is coordinate-based input. There is no touch
injection service on iOS. `services/accessibilityaudit.py` has only
`perform_press(element)` — element-addressed, not `(x, y)` — so it cannot back
`click`, `click_and_drag`, `smooth_move` or `scroll`.

Coordinate input on iOS means **WebDriverAgent (WDA)**: an XCUITest runner app
launched on the device (`XCUITestService` with
`com.facebook.WebDriverAgentRunner.xctrunner` — pymobiledevice3's own docstring
uses exactly that bundle id), whose HTTP server on port 8100 we reach through a
`UsbmuxTcpForwarder`. From there: `POST /session`, `POST /session/:id/actions`
(W3C pointer actions — the right primitive for the generated click paths),
`POST /session/:id/wda/tap/0`, `POST /session/:id/wda/keys`,
`POST /session/:id/wda/pressButton`, `GET /session/:id/window/size`.

WDA's cost is real and user-facing: it must be **built and signed** with an
Apple developer identity and installed on the device. That is a much heavier
prerequisite than `adb pair`.

**Therefore: phase the work.** A read-only iOS device is genuinely useful
(live view in the editor, image matching, detect object/scene, OCR, launch and
stop apps) and needs no WDA at all. Input comes second, behind an explicit
prerequisite.

---

## 4. Prerequisites the user must satisfy

Worth stating plainly in the controller UI, because each one is a distinct
failure mode:

1. **Trust** — "Trust This Computer" on first USB connection (pairing record).
2. **Developer Mode** — iOS 16+: Settings → Privacy & Security → Developer Mode,
   then reboot.
3. **Developer disk image mounted** — required for the screenshot service *and*
   all DVT services. `pymobiledevice3 mounter auto-mount`
   (`services/mobile_image_mounter.py`) downloads and mounts it. Without this,
   even `screenshot` fails.
4. **iOS 17+ only: an RSD tunnel**, which needs **root**. This is what
   `pymobile_tunnel_server_manager.py` and the `SudoClient` in the existing
   draft were reaching for; §8 is how it was actually done. iOS < 17 works over
   plain usbmux with no root.
5. **Input only: WebDriverAgent** built, signed and installed.

Platform note: usbmux on Windows comes from Apple Mobile Device Support
(iTunes); `tunneld` on Windows is the least-tested path in pymobiledevice3.
Target macOS first and say so.

---

## 5. Plan

### Phase 0 — decide the device-type name and ID shape

Recommendation: device type `ios`, device IDs `ios:<udid>`.

- The `<prefix>:<id>` convention is already load-bearing in
  `device_id_to_device_type()` and in the three studio switches.
- UDID, not `hostSerial-ip`: a USB iPhone has no IP, and the UDID is the stable
  identifier both usbmux and tunneld select on.
- Keep the Simulator out of scope, or give it its own prefix (`iossim:`) later —
  it is a different transport (`xcrun simctl`) and, unlike a physical phone,
  it *can* be booted and shut down, so it is the only iOS variant where
  `start_device` / `stop_device` can mean anything.

### Phase 1 — a read-only iOS device (no WDA)

**1a. Rewrite `ScriptEngine/managers/ios_device_manager.py`.**

Constructor matching the others:
`IOSDeviceManager(props, device_params, input_source=None, ...)`.

- Resolve the device by UDID from `device_params`, not `rsds[0]`.
- Connection strategy: `create_using_usbmux(serial=udid)` first; if the device
  reports iOS 17+ or a DVT service is refused, fall back to the tunneld RSD
  path (`async_get_tunneld_devices()`, filtered by UDID).
- `screenshot()` → PNG bytes from the screenshot service, `PIL` →
  `cv2.cvtColor(..., COLOR_RGB2BGR)` → `numpy` array. Mirror
  `PiKVMDeviceManager.screenshot()`, which is the closest existing shape.
- `ensure_device_initialized()` → set `width`/`height` from the first
  screenshot (same as PiKVM/ADB), build a `ClickPathGenerator`, and record the
  **pixel-to-point scale factor** (see the gotcha in §6).
- `get_status()` → `"online"` / `"offline"` from whether lockdown connects and
  a screenshot succeeds. PiKVM's implementation is the model.
- `list_applications()` → `installation_proxy.get_apps(application_type='User')`,
  returning `{bundle_id: display_name}` to match the ADB manager's
  `{package: label}` contract.
- `start_application(bundle_id, args)` → DVT `ProcessControl.launch`.
  `stop_application(bundle_id)` → `ProcessControl.kill` by pid.
- `start_device` / `stop_device` → log and no-op for a physical device (the
  `emulator_type == 'adb'` branches in the ADB manager already set this
  precedent).
- Input methods (`click`, `click_and_drag`, `smooth_move`, `scroll`,
  `key_*`, `hotkey`) → raise a single, explicit
  `"iOS input requires WebDriverAgent; see docs/ios-device-support-plan.md"`.
  Do **not** silently fall through to `pyautogui`, which is what the ADB
  manager does for `key_up`/`key_down`/`hotkey` and which would drive the
  *host desktop* instead of the phone.
- Expose `dummy_mode`, `input_source`, `width`, `height`, and honour file mode
  exactly like the other managers.

**1b. Replace `pymobile_tunnel_server_manager.py` with a privileged tunnel
daemon.** The current file is broken — it passes `Tunneld().start()`'s return
value to `subprocess.Popen` as if it were a command line — and leaving it there
invites someone to call it. §8 is the design that replaces it: a one-time
privileged install of a launchd system daemon, plus a tiny engine entry point
for it to run (`TunneldRunner.create` is the whole body). Until then the
Add Device form's tunnel check reports the state and explains it but has no fix
button, which is `FIX_START_TUNNEL` with no entry in the renderer's
`FIX_ACTIONS` table.

**1c. Wire it into `device_controller.py`.**
- `device_id_to_device_type()`: add `ios` → `'ios'`. While there, give it an
  `else` — an unrecognised prefix currently falls through with `device_type`
  unbound and raises `UnboundLocalError` instead of a useful message.
- `initialize_device()`: add the `elif device_type == 'ios'` branch, lazy
  import, both the default-device and explicit-`device_params` paths (copy the
  `kvm` branch's structure).
- `DEVICE_TYPES_REQUIRING_ATTACHMENT`: add `'ios'`.
- Consider adding the iOS manager to `warm_request_path_imports()` —
  importing `pymobiledevice3` is not instant, and the existing comment explains
  why first-import-on-the-request-path has bitten this process before.

**1d. `script_manager.py`.** Line 153 hard-codes
`device_params['script-engine-device-type'] = 'bluestacks'` for every non-file
selection. Derive it from the resolved device's `type` instead; otherwise an
iOS run carries a label that says BlueStacks.

**1e. Contracts.** Add `"ios"` to the `SystemName` enum in
`common.schema.json`, regenerate `screenplan-contracts-ts` and
`screenplan-contracts-py`, publish both. **This lands first** — `setup.py`
pulls them from GitHub `@main`, so the engine change depends on it.

**1f. Controller UI.** *(done)*
- `index.html`: an `iosOption` entry in `deviceDropdown`; the UDID field with a
  Detect button beside it; the prerequisite checklist; the network fields wrapped
  in `networkFields` so they can be hidden.
- `renderer/devices.js`: `iosOption` click handler and the `DEVICE_TYPE_FORM`
  table that owns which blocks and which `required` flags each type has — the
  earlier per-type branches could leave a hidden input `required`, which blocks
  submit while showing the user nothing.
- `renderer/iosSetup.js`: Detect, Check, and the fix buttons the checklist grows.
- `src/iosSetup.mjs`: the `runIosSetupAction` IPC handler, which allow-lists the
  action name and shape-checks the UDID before sending either to the engine.
- `hostDataClient.mjs`: the `ios` branch in `handleAddDevice`, keying the device
  id off the UDID rather than `${hostSerial}-${ip}`.
- Discovery happens in the form rather than in `collectHostDeviceData()`: a
  phone is only enumerable while it is plugged in, so enumerating at startup
  would mostly produce records for devices that are not there. Pressing
  `+ Add Device` → iOS device runs `ios_list_devices` immediately and fills the
  UDID in, which is the same convenience without the stale records. Adding it to
  `collectHostDeviceData()` as well remains possible.

**1g. script-studio.** Add an `ios` case to the three prefix switches. Because
the mapping is now duplicated three times and each one defaults to `'adb'`
(so an `ios:` device would silently be driven as Android), replace them with
one shared `deviceIdToTargetSystem()` helper.

**1h. Packaging.** Add `pymobiledevice3` to `setup.py` `install_requires` and
`setup/venv_requirements.txt`; add it to `hiddenimports` for both
`device_controller_a` and `script_manager_a` in `script_engine.spec`.
Expect PyInstaller work for its transitive native/data deps (`construct`,
`cryptography`, `zeroconf`, `ifaddr`, `pyimg4`) — budget time for a frozen-build
smoke test, since the packaged build has already produced
import-hangs-on-the-request-path bugs in this process.

**Phase 1 definition of done:** register an iPhone in the controller, see it
online, see its live screen in the editor, list and launch its apps, and run a
script whose actions are screenshot-and-match only. Input actions fail with a
message that names WebDriverAgent.

### Phase 2 — WDA-backed input

**2a. A `WDAClient` helper** (`ScriptEngine/clients/wda_client.py`), separate
from the manager: start the runner via `XCUITestService`, forward port 8100 via
`UsbmuxTcpForwarder` on a free local port, create and cache a session, expose
`tap`, `perform_actions`, `send_keys`, `press_button`, `window_size`,
`orientation`, and health-check/recreate a dead session.

**2b. Implement the input methods** on `IOSDeviceManager`:
- `click(x, y, button, important, mouse_up)` → scale to points, then
  `/wda/tap/0` for a plain tap, or a pointer-action sequence when
  `mouse_up=False` (the engine uses `mouse_down`/`mouse_up` as separate calls).
- `smooth_move` / `click_and_drag` → reuse `ClickPathGenerator` exactly as the
  PiKVM manager does, then emit the generated path as one W3C
  `POST /session/:id/actions` pointer sequence. This is where iOS can actually
  do *better* than ADB, which replays coordinates through `sendevent`.
- `scroll` → `/wda/dragfromtoforduration` or a pointer sequence. Note the ADB
  manager raises on `scroll`; iOS does not have to.
- `key_press` / `key_down` / `key_up` / `hotkey` → `/wda/keys`. iOS has no
  real key-down/key-up distinction through WDA; make `key_down`/`key_up`
  raise rather than quietly typing the whole key.
- Keep the WDA session lazy: a script that only matches images should never
  pay to start the runner.

**2c. Orientation.** `GET /session/:id/orientation`, cached like
`ADBDeviceManager.screen_orientation`, and applied to coordinate mapping.

**2d. Reconnection.** The `restart_device_on_crash` / `restart_deadline` /
`cancel_check` machinery is ADB-specific today but the contract is general: a
dropped WDA session or a re-plugged phone should reconnect on the same
`ensure_device_initialized(reinitialize=True)` path.

### Phase 3 — optional

- `iossim:` device type over `xcrun simctl` (`boot`, `shutdown`, `io screenshot`,
  and real `start_device`/`stop_device` semantics).
- Wi-Fi (network) iOS devices rather than USB only.
- `system_script_handler` `startDevice` / `stopDevice` entries, which currently
  assume an emulator.

---

## 6. Gotchas worth knowing before writing code

1. **Pixel vs point coordinate spaces.** This is the subtle one. On Android,
   `screencap` and `input tap` share one pixel space, so the engine's
   `width`/`height` (taken from the screenshot) are directly tappable. On iOS,
   screenshots come back in **pixels** (2× or 3× Retina) while WDA takes
   **points**. `ensure_device_initialized()` must compute
   `scale = screenshot_width / wda_window_width` and divide every incoming
   coordinate. Get this wrong and every tap lands at a third of the intended
   position.
2. **`screenshot()` must return BGR `numpy`,** not the PNG bytes or the service
   object the current draft returns.
3. **`dummy_mode` is not optional** — `DeviceActionInterpreter` reads it through
   `get_device_attribute` before every keyboard action.
4. **`device_id_to_device_type()` has no `else`** and raises `UnboundLocalError`
   on an unknown prefix. Fix it in the same change.
5. **The three studio switches default to `'adb'`,** so an unregistered `ios:`
   prefix is not an error — it silently drives the phone as if it were Android.
6. **The developer disk image gates screenshots too,** not just DVT. The first
   failure a user hits will probably be this, so detect it and say so.
7. **Root for iOS 17+.** Decide early whether the controller prompts for admin
   (`SudoClient`) and supervises `tunneld`, or whether the user runs it. This
   decision leaks into the UI copy either way.
8. **Cross-repo ordering**: contracts → ScriptEngine → controller → studio.
   The contracts packages are consumed from GitHub `@main`.

---

## 7. Suggested commit sequence

1. `screenplan-contracts`: `"ios"` in the `SystemName` enum; regenerate and
   publish `-ts` and `-py`.
2. `ScriptEngine`: rewrite `IOSDeviceManager` as a complete read-only manager
   (+ unit tests with a mocked lockdown client, including a
   coordinate-scaling test).
3. `ScriptEngine`: wire `ios` through `device_controller.py`
   (`device_id_to_device_type`, `initialize_device`,
   `DEVICE_TYPES_REQUIRING_ATTACHMENT`, the `else` fix) and fix the
   hard-coded `'bluestacks'` label in `script_manager.py`.
4. `ScriptEngine`: packaging — `setup.py`, `venv_requirements.txt`,
   `script_engine.spec`, frozen-build smoke test.
5. `Script-Engine-Controller`: iOS auto-discovery in `collectHostDeviceData`,
   the `+ Add Device` option, prerequisites copy, `handleAddDevice` branch.
6. `script-studio`: the shared `deviceIdToTargetSystem()` helper replacing the
   three switches, with `ios` handled.
7. `ScriptEngine`: `WDAClient` + the input methods (Phase 2), behind the
   documented WDA prerequisite.

---

## 8. The iOS 17+ tunnel, and how to stop asking for a password

### 8.1 Does the tunnel have to stay up?

Yes, whenever an iOS 17-or-later device is being used — but it does not have to
be *recreated*.

From iOS 17 Apple moved every developer service behind RemoteServiceDiscovery,
which is reachable only over a tunnel to the device. The tunnel is a `utun`
interface plus a QUIC or TCP session, and every service connection — screenshot,
instruments, installation proxy — rides on it. If `tunneld` stops, the device's
RSD address goes away, `get_tunneld_device_by_udid` returns `None`, and
`IOSDeviceManager.get_status()` reports `'offline'`. So the daemon has to be
alive for the whole time a script is running, not just at connection time.

What it does *not* need is a fresh tunnel per use: `tunneld` keeps one tunnel per
device and hands the same one to every caller, and it has a `/start-tunnel?udid=`
endpoint for creating one on demand. One long-lived `tunneld` serves every iOS
device on the host for as long as the host is up.

Creating a `utun` interface requires root. There is no way around that: it is a
kernel network interface, and macOS gates it on uid 0. So the question is not
how to avoid root, it is **how to pay for root once instead of every time.**

iOS 16 and below need none of this — plain usbmux lockdown, no root, no tunnel.
The tunnel check is skipped for those devices.

### 8.2 The design: install a daemon once, never ask again

A root-owned launchd **system daemon** that runs `tunneld` and nothing else,
installed once with a single visible authorization, started by launchd at boot
with no user present from then on.

1. **One fixed job, no parameters.** The daemon's whole body is
   `TunneldRunner.create('127.0.0.1', 49151)`. It takes no input from the app —
   not a device, not a path, not a flag. The app's only interaction with it is
   `GET http://127.0.0.1:49151/`, which lists tunnels. This is the property that
   makes the whole thing defensible: **the privileged code path is fixed at
   install time and takes no runtime parameters**, so nothing the renderer, the
   controller or a compromised script can send changes what runs as root. Do not
   build a general "run this command as root" bridge; that is a root shell with
   extra steps.

2. **`RunAtLoad` + `KeepAlive`.** It comes back after a crash and after a
   reboot, so the user thinks about it exactly once.

3. **The escalation trap: a root daemon must not execute anything the user can
   write.** If the plist pointed at `venv/bin/python` in the user's home, then any
   process running as that user could drop a file into that venv's
   `site-packages` and get root on the next launch — strictly worse than `sudo`,
   which at least asks.

   **`SMAppService` answers this with signature validation instead of file
   ownership, which is why it is the design that was built.** The daemon's
   executable stays *inside the app bundle*, named by a bundle-relative
   `BundleProgram`, and macOS validates it against the containing app's code
   signature before launching it. A tampered engine binary does not run as root;
   it does not run at all. Nothing is copied to `/Library`, so there is no
   root-owned tree to install, keep in step with updates, or get the permissions
   wrong on.

   The consequence is that this **only works on a signed build**. In a dev
   checkout there is no bundle and no signature, so `installTunnelDaemon()`
   refuses with a message naming `sudo pymobiledevice3 remote tunneld` rather
   than pretending. A `/Library`-copy fallback was considered for unsigned builds
   and rejected: it is the weaker mechanism, and shipping both would mean the
   weaker one is what gets exercised.

4. **How the one authorization is obtained: `SMAppService.daemon(plistName:)`.**
   Registering a *daemon* asks the user to authorize it once — macOS's own
   dialog, naming the app — and then it is theirs to enable or disable from
   System Settings → Login Items & Extensions without being asked again.
   (Agents, unlike daemons, need no authorization at all; a daemon runs as root,
   so it does.) `CODE_SIGNING_SETUP.md` covers the signing this depends on, and
   `npm run make:signed` already produces it.

   `SMAppService` has no Electron binding and is deliberately bundle-relative —
   `daemon(plistName:)` resolves the plist against the *calling executable's*
   `Bundle.main` — so the call lives in a small Swift helper at
   `Contents/MacOS/screenplan-ios-tunnel-setup`. It has to be in `Contents/MacOS`
   specifically: an executable anywhere else in the bundle, `Contents/Resources`
   included, does not resolve to the `.app`, and `SMAppService` then reports the
   service as `notFound`.

5. **No stored password, ever.** Not in the Keychain, not piped to `sudo -S`,
   not cached beyond the install. It is the user's login and FileVault password;
   a replayable copy of it is the worst outcome on this page, and it buys nothing
   that launchd does not give for free.

6. **Report the state, never fail silently.** The Add Device form already
   distinguishes "the tunnel service is not running" from "this device is
   offline", and the device's own status check should too — "tunnel down" and
   "phone unplugged" need different actions from the user, and today both read as
   offline.

### 8.3 Rejected alternatives, and why

- **A `/etc/sudoers.d` NOPASSWD entry for the tunnel command.** One admin prompt
  too, but it then lets *any* process running as that user take root by that
  command, with no prompt and no record — and the command's own arguments become
  an attack surface. The daemon is narrower, survives reboots, and cannot be
  invoked with different arguments.
- **An `osascript ... with administrator privileges` install that copies the
  binary and plist to `/Library` and runs `launchctl bootstrap system`.** This
  was the planned fallback for unsigned builds. Rejected once `SMAppService`
  worked: it replaces signature validation with file-ownership discipline that
  has to be got right on every update, and keeping it as a fallback would mean
  the weaker of the two mechanisms is the one that gets exercised in
  development.
- **Prompting for the password each time, relying on sudo's five-minute
  timestamp.** This is the thing being replaced. It also trains the user to type
  their login password into application dialogs, which is the habit every
  credential-phishing attack depends on.
- **Storing the admin password in the Keychain and replaying it to `sudo -S`.**
  Never. See 8.2(5).
- **Running the whole device controller as root so it can make its own tunnel.**
  Then every script action, every image match and every `pyautogui` call runs as
  root. The tunnel is one fixed job; the engine is not.

### 8.4 What this is, in files

| | |
|---|---|
| `ScriptEngine/ios_tunnel_server.py` | What root runs. Imports pymobiledevice3 and nothing from ScriptEngine; refuses to start unprivileged; defaults to loopback and the USB monitors only. |
| `script_engine.spec` | Builds it as its own executable, `ios_tunnel_server`, excluding the vision stack. |
| `build/ios-tunnel-daemon.plist` | The launchd job. `BundleProgram`, `RunAtLoad`, `KeepAlive`, and no `ProgramArguments` at all. |
| `build/ios-tunnel-setup.swift` | The `SMAppService` call, as `register` / `status` / `unregister`, reporting one line of JSON. |
| `forge.config.js` (`packageAfterCopy`) | Puts the plist in `Contents/Library/LaunchDaemons` and compiles the helper into `Contents/MacOS`, before signing, so both are covered by the bundle signature. |
| `src/iosTunnelDaemon.mjs` | Finds and runs the helper; returns the dev-checkout refusal when there is no bundle. |
| `src/iosSetup.mjs` | Routes the `ios_start_tunnel` action here rather than to the engine. |

It replaced `managers/pymobile_tunnel_server_manager.py`, which is deleted.

### 8.5 What registration actually does, measured

Verified against a Developer ID-signed build (team `7RGRST92BF`) copied into
`/Applications`. Two things are worth knowing because neither is in Apple's
documentation and both would otherwise read as failures:

**`register()` throws while succeeding.** On the approval path it raises
`Operation not permitted` *and* moves the service to `.requiresApproval`, having
registered it. The first version of the helper treated the throw as fatal and
told the user their app was not signed — which was wrong, and the opposite of
what they needed to hear. **Read `service.status` after `register()`, not whether
it threw**; the thrown message is only useful in the `default` branch, where the
service is neither running nor waiting.

**`sfltool dumpbtm` is how to check it without root.** After registration the
Background Task Management record reads:

```
Name: ios_tunnel_server
Team Identifier: 7RGRST92BF
Type: daemon (0x10)
Disposition: [enabled, disallowed, visible, not notified] (0x1)
Identifier: 16.com.screenplan.script-engine-controller.ios-tunnel
URL: Contents/Library/LaunchDaemons/com.screenplan.script-engine-controller.ios-tunnel.plist
Executable Path: Contents/Resources/app.asar.unpacked/bin/ScriptEngine/ios_tunnel_server
Assoc. Bundle IDs: [ com.screenplan.script-engine-controller ]
Parent Identifier: 2.com.screenplan.script-engine-controller
```

`disallowed` is the pending-approval state, and the one thing the user still has
to do: allow it in System Settings → Login Items & Extensions. `openSystemSettingsLoginItems()`
puts them there. Until then nothing listens on `127.0.0.1:49151`, so the engine's
tunnel check keeps reporting the service as not running — correctly, but
unhelpfully: on its own it would tell someone who had just pressed the button to
press it again. `describeTunnelCheck()` in `src/iosSetup.mjs` closes that gap, by
asking the daemon what state it is actually in whenever the engine reports the
tunnel down, and rewriting the check to say "allow it" (with an **Open Settings**
button) or, in a development build, that this build cannot install it at all.
The engine cannot make that distinction: all it can see is the port.

`unregister()` leaves the BTM record in place with `Disposition: [disabled, ...]`
and the generation bumped, rather than deleting it; macOS reaps it in its own
time once the app is gone. The daemon stops immediately, which is what matters.
`notRegistered` is the status after an unregister, as against `notFound` for one
never registered.

Also measured: an **unsigned or ad-hoc-signed** bundle reports `notFound` rather
than failing informatively, even with the plist in place. There is no way to
make the button work in a dev checkout, which is why it refuses with the manual
command instead of trying.

### 8.6 One upstream caveat

`tunneld`'s loopback API is unauthenticated and includes `/shutdown` and
`/clear_tunnels`. Anything that can reach `127.0.0.1:49151` — any process on the
host, as any user — can therefore stop the tunnels. That is upstream
pymobiledevice3's design, not something this daemon introduces, and `KeepAlive`
restarts the daemon afterwards. Worth knowing; not worth forking over.
