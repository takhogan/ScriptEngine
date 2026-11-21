# ScriptEngine - Backend engine for ScreenPlan Scripts
# Copyright (C) 2024  ScriptEngine Contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""A device that replays recorded runs (UI_MAPPER.md §4).

It reads a sim pack that ScreenPlanUIMapper writes (`ui_mapper sim-pack`):
the screenshots of earlier real runs of an app, each with the screen (state)
the mapper put it in and the time it was taken, and the inputs those runs
sent. The device is always at a moment of one recorded run:

- a screenshot is that run's latest frame at the moment, so a loading screen
  plays out, a popup comes up, as it did on the device, with the real frames;
- the moment moves with the run's clock (sim_clock), and stops just before
  the run's next input, since what came after it depended on that input;
- an input looks for recorded inputs of the same kind made on the same
  screen, at the same point (inside the box the recorded click was chosen
  from), by the same action if it can (the calling action, from the run's
  logger); it takes one, the run's own next input when that is one of them,
  and goes on from that moment of that run, so latency, transitions and
  what the input led to are the recorded ones;
- a key input matches only recorded inputs that typed the same keys (the
  whole text of the keyboard action, which the engine hands the device first,
  prepare_typed_keys), or, for a secret, recorded inputs that typed a secret;
  a recording whose keys were not recorded (result version 1) is used only
  when none typed the same: what follows a code depends on the code, and a
  value no run typed is not given another value's outcome;
- with no such input it is a low-evidence input: by the default policy
  ('stay') nothing happens, as for most dead clicks; 'fail' ends the run;
- held at an input the script does not make, for more than `hold_s` of run
  time, the device carries on from another recorded moment of the same
  screen that went on without input (a loading screen that finished).

Detects, OCR and colour compares run for real on the recorded frames. Every
decision goes to `sim-log.jsonl` in the run folder, with the seed, so a run
replays exactly; a secret's keys are never written there, only that one was
typed. Not yet: hit models for points the logs never clicked,
fault injection, experiences (§4).
"""
import bisect
import hashlib
import json
import os
import random
import re
import threading
from collections import OrderedDict, defaultdict

import cv2

from ScriptEngine.common import sim_clock
from ScriptEngine.common.logging.script_logger import ScriptLogger
from ScriptEngine.managers.device_manager import DeviceManager

script_logger = ScriptLogger()

PACK_FILE = 'sim-pack.json'
FOLDER_RE = re.compile(r'^\d+-(.+)-\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}$')


def seed_engine(seed):
    """Seeds the engine's own randomness for a run on the sim: where in a
    matched box a click lands, a drag's path, a random-variable action. Left
    unseeded, a click lands a few pixels elsewhere on each run, inside other
    recorded clicks' boxes, and the same seed takes another path."""
    import numpy as np
    random.seed(int(seed))
    np.random.seed(int(seed) % (2 ** 32))


def _plain(o):
    """numpy numbers (a click's point comes as one) as plain ones, for the log."""
    return o.item() if hasattr(o, 'item') else str(o)


class SimulatedDeviceError(Exception):
    """An input the sim was told to refuse ('fail' policy), or a sim it cannot set up."""


class SimulatedDeviceManager(DeviceManager):
    """params: path (the sim pack folder), script (the run's root script),
    seed, start (a recorded run id, host/folder; else a good run of the
    script with at least min_frames screenshots), policy (stay | fail),
    screenshot_s (what a screenshot costs on the run clock; default the
    pack's), hold_s, slack (pixels around a recorded click's box), change_at."""

    def __init__(self, props, params):
        self.props = props
        self.params = params
        self.path = params.get('path')
        if not self.path or not os.path.exists(os.path.join(self.path, PACK_FILE)):
            raise SimulatedDeviceError("SIMULATED DEVICE: no sim pack at '{}' ({} missing)".format(self.path, PACK_FILE))
        with open(os.path.join(self.path, PACK_FILE), encoding='utf-8') as f:
            self.pack = json.load(f)
        self.frames_dir = os.path.join(self.path, self.pack.get('frames_dir', 'frames'))
        self.width = int(self.pack['width'])
        self.height = int(self.pack['height'])
        # Device input coordinates are screen pixels here (adb's are 0..32726).
        self.xmax, self.ymax = self.width, self.height
        self.dummy_mode = False
        self.seed = int(params.get('seed', 0))
        self.rng = random.Random(self.seed)
        self.policy = params.get('policy', 'stay')
        self.screenshot_s = float(params.get('screenshot_s', self.pack.get('screenshot_s', 0.5)))
        self.hold_s = float(params.get('hold_s', 3.0))
        self.slack = float(params.get('slack', max(12, 0.02 * self.width)))
        self.radius = float(params.get('radius', 0.04 * self.width))
        self._lock = threading.RLock()
        self._images = OrderedDict()
        self._mouse_down_at = None
        self._last_caller = None
        self._typed = None  # (action log id, keys or None for a secret): the text the current keyboard action types
        self._swallow = 0   # keys still to come of a keyboard action already matched as a whole
        self.counts = defaultdict(int)

        self.runs = self.pack['runs']
        self._run_index = {r['id']: i for i, r in enumerate(self.runs)}
        # change_at: when a recorded frame is shown. A frame says only that the
        # screen looked so by the time it was taken; it changed some time after
        # the frame before it, or after the input in between. 'mid' (the
        # default) shows it from the middle of that gap, 'capture' only from
        # when it was taken, which is late: a script that looks again 3 s after
        # a key press, where the recorded screenshot came 3.2 s after it, would
        # never see what the key did.
        self.change_at = params.get('change_at', 'mid')
        for r in self.runs:
            r['_it'] = [i['t'] for i in r['inputs']]
            r['_ft'] = self._shown_from(r)
        # (kind, state) -> [(run index, input index)]
        self.by_state = defaultdict(list)
        for ri, r in enumerate(self.runs):
            for ii, inp in enumerate(r['inputs']):
                if inp.get('state') is not None:
                    self.by_state[(inp['kind'], inp['state'])].append((ri, ii))
        # state -> [(run index, start, end)]: visits, stretches of a run on one
        # screen with no input, that ended with the screen changing by itself
        # (not with an input, or with the end of the recording).
        self.visits = defaultdict(list)
        for ri, r in enumerate(self.runs):
            frames, ft = r['frames'], r['_ft']
            k = 0
            while k < len(frames):
                state, start = frames[k][2], ft[k]
                nxt_in = self._next_input_after(ri, start, strictly=False)
                limit = r['inputs'][nxt_in]['t'] if nxt_in is not None else float('inf')
                m = k + 1
                while m < len(frames) and frames[m][2] == state and ft[m] < limit:
                    m += 1
                if state is not None and m < len(frames) and ft[m] < limit:
                    self.visits[state].append((ri, start, ft[m]))
                k = m
        self._shown_state, self._state_since = None, None
        self._draws = defaultdict(int)

        # The run folder (script_manager passes it); else the logger's folder.
        folder = params.get('log_folder')
        if not folder:
            try:
                folder = ScriptLogger.get_instance().get_log_folder()
            except Exception:
                folder = None
        self.log_path = os.path.join(folder, 'sim-log.jsonl') if folder else None
        sim_clock.make_virtual()
        self._start()

    # ---- position -------------------------------------------------------

    def _start(self):
        start = self.params.get('start')
        if start:
            if start not in self._run_index:
                raise SimulatedDeviceError("SIMULATED DEVICE: no recorded run '{}' in the sim pack".format(start))
            ri = self._run_index[start]
        else:
            root = self.params.get('script')
            # Runs with few screenshots are mostly partial backups: little to replay.
            least = int(self.params.get('min_frames', 10))
            mine = [i for i, r in enumerate(self.runs) if r.get('root') == root and len(r['frames']) >= least]
            good = [i for i in mine if self.runs[i].get('return_code') == 0]
            pool = good or mine
            if not pool:
                raise SimulatedDeviceError(
                    "SIMULATED DEVICE: the sim pack has no recorded run of '{}' to start from; "
                    "pass start (a recorded run id) in the device params".format(root))
            ri = self.rng.choice(sorted(pool))
        r = self.runs[ri]
        self._at(ri, r['_ft'][0], None)
        self._log('start', run=r['id'], seed=self.seed, pack=self.path, policy=self.policy,
                  screenshot_s=self.screenshot_s, frame=r['frames'][0][1], state=r['frames'][0][2])

    def _at(self, ri, t, input_index):
        """Be at recorded time t of run ri, from now on the run clock; input_index
        is the input made there (the hold looks for the next one after it)."""
        self.ri, self.t0, self.clock0 = ri, t, sim_clock.time()
        self.after_input = input_index

    def _shown_from(self, r):
        times = [f[0] for f in r['frames']]
        if self.change_at == 'capture':
            return times
        out = []
        for k, t in enumerate(times):
            if k == 0:
                out.append(t)
                continue
            a = times[k - 1]
            j = bisect.bisect_right(r['_it'], t) - 1
            if j >= 0 and r['_it'][j] > a:
                a = r['_it'][j]
            out.append(max(out[-1], a + (t - a) / 2))
        return out

    def _next_input_after(self, ri, t, strictly=True):
        it = self.runs[ri]['_it']
        j = bisect.bisect_right(it, t) if strictly else bisect.bisect_left(it, t)
        return j if j < len(it) else None

    def _held_input(self):
        """The index of the recorded input the device waits at: the run's
        next input after where the device came in, or None at its end."""
        r = self.runs[self.ri]
        j = self.after_input + 1 if self.after_input is not None else bisect.bisect_left(r['_it'], self.t0)
        return j if j < len(r['inputs']) else None

    def _now(self):
        """(run index, recorded time, seconds held): where the device is now."""
        r = self.runs[self.ri]
        t = self.t0 + (sim_clock.time() - self.clock0)
        j = self._held_input()
        if j is not None and t >= r['inputs'][j]['t']:
            return self.ri, r['inputs'][j]['t'] - 1e-6, t - r['inputs'][j]['t']
        if j is None and t > r['frames'][-1][0]:
            # past the end of the recording: as stuck as at an input
            return self.ri, t, t - r['frames'][-1][0]
        return self.ri, t, 0.0

    def _frame(self, ri, t):
        r = self.runs[ri]
        fi = max(0, bisect.bisect_right(r['_ft'], t) - 1)
        return fi, r['frames'][fi]

    def _image(self, name):
        img = self._images.get(name)
        if img is None:
            img = cv2.imread(os.path.join(self.frames_dir, name + '.png'), cv2.IMREAD_COLOR)
            if img is None:
                raise SimulatedDeviceError('SIMULATED DEVICE: frame {} is missing from {}'.format(name, self.frames_dir))
            if img.shape[1] != self.width or img.shape[0] != self.height:
                img = cv2.resize(img, (self.width, self.height), interpolation=cv2.INTER_AREA)
            self._images[name] = img
            if len(self._images) > 64:
                self._images.popitem(last=False)
        else:
            self._images.move_to_end(name)
        return img

    # ---- the caller -----------------------------------------------------

    @staticmethod
    def _caller():
        """(script, actionGroup, action log id) of the action calling the device, as far as the logger knows."""
        try:
            lg = ScriptLogger.get_logger()
            log = lg.get_action_log()
            folder = os.path.basename((lg.get_log_folder() or '').rstrip('/\\'))
            m = FOLDER_RE.match(folder)
            script = m.group(1) if m else None
            group = int(log.name.rsplit('-', 1)[1]) if log is not None else None
            return script, group, (log.id if log is not None else None)
        except Exception:
            return None, None, None

    def _draw(self, n, *what):
        """A choice of n, drawn from the seed and what is being decided (the
        n-th time it is), not from one running stream: a change to a script
        that shifts its timing, or adds an action elsewhere, leaves the draws
        of the decisions it did not change as they were, so two versions of a
        script on one seed differ only where the change made them."""
        self._draws[what] += 1
        key = json.dumps([self.seed, list(what), self._draws[what]], default=str).encode()
        return int.from_bytes(hashlib.sha256(key).digest()[:8], 'big') % n

    # ---- inputs ---------------------------------------------------------

    def _point_ok(self, inp, x, y):
        if inp.get('x') is None or x is None:
            return True
        box = inp.get('box')
        if box:
            s = self.slack
            return box['x'] - s <= x <= box['x'] + box['width'] + s and box['y'] - s <= y <= box['y'] + box['height'] + s
        return (inp['x'] - x) ** 2 + (inp['y'] - y) ** 2 <= self.radius ** 2

    def _input(self, kind, x=None, y=None, to=None, keys=None):
        with self._lock:
            script, group, log_id = self._caller()
            if kind == 'key' and self._swallow > 0:
                self._swallow -= 1
                return  # the rest of a keyboard action matched by its whole text
            if kind == 'key' and log_id is not None and self._last_caller == (log_id, kind):
                return  # the rest of one keyboard action's keys
            self._last_caller = (log_id, kind)
            ri, t, held = self._now()
            fi, (_, frame, state) = self._frame(ri, t)
            typed = self._typed if kind == 'key' and self._typed is not None and self._typed[0] == log_id else None
            if kind == 'key' and typed is None and keys is not None:
                typed = (log_id, [str(k) for k in keys])  # a hotkey, or an engine without prepare_typed_keys
            if kind == 'key':
                if self._typed is not None and typed is self._typed:
                    self._swallow = max(0, self._typed_n - 1)
                self._typed = None  # used once: the next keyboard action hands its own
            cands = []
            for rj, ij in self.by_state.get((kind, state), []):
                inp = self.runs[rj]['inputs'][ij]
                if not self._point_ok(inp, x, y):
                    continue
                if kind == 'drag' and to is not None and inp.get('to') is not None:
                    if (inp['to']['x'] - to[0]) ** 2 + (inp['to']['y'] - to[1]) ** 2 > (2 * self.radius) ** 2:
                        continue
                value = self._value_match(inp, typed) if kind == 'key' else 'same'
                if value == 'other':
                    continue
                same = script is not None and inp.get('script') == script and inp.get('group') == group
                cands.append((rj, ij, same, value == 'same'))
            # Same value first (a recording whose keys are unknown only when none
            # typed the same), then the same action first.
            cands = [c for c in cands if c[3]] or cands
            tier = [c for c in cands if c[2]] or cands
            shown_keys = None if kind != 'key' else ('(a secret)' if typed is not None and typed[1] is None
                                                     else typed[1] if typed is not None else keys)
            entry = {'kind': kind, 'x': x, 'y': y, 'to': to, 'keys': shown_keys, 'caller': '{}:{}'.format(script, group),
                     'run': self.runs[ri]['id'], 'frame': frame, 'state': state, 'held_s': round(held, 3)}
            if not tier:
                self.counts['low evidence'] += 1
                self._log('low evidence', **entry, policy=self.policy)
                if self.policy == 'fail':
                    raise SimulatedDeviceError(
                        'SIMULATED DEVICE: no recorded {} on screen {} at ({}, {}) (low-evidence input, policy fail)'.format(
                            kind, state, x, y))
                return
            own = self._held_input()
            pick = next(((rj, ij) for rj, ij, _, _ in tier if rj == ri and ij == own), None)
            how = 'continued'
            if pick is None:
                rj, ij, _, _ = tier[self._draw(len(tier), 'input', kind, state, script, group)]
                pick, how = (rj, ij), 'switched'
            rj, ij = pick
            inp = self.runs[rj]['inputs'][ij]
            self._at(rj, inp['t'], ij)
            self.counts[how] += 1
            self._log('input', **entry, how=how, matched=len(tier), by_action=tier[0][2],
                      by_value=(tier[0][3] if kind == 'key' else None),
                      to_run=self.runs[rj]['id'], to_t=round(inp['t'], 3), recorded='{}:{}'.format(inp.get('script'), inp.get('group')))

    @staticmethod
    def _value_match(inp, typed):
        """'same', 'other' or 'unknown': whether a recorded key input typed
        what the current keyboard action types. typed is (log id, keys), keys
        None for a secret; None when the text is not known."""
        if typed is None:
            return 'unknown'
        if inp.get('masked'):
            return 'same' if typed[1] is None else 'other'
        if inp.get('keys') is None:
            return 'unknown'
        if typed[1] is None:
            return 'other'
        return 'same' if [str(k) for k in inp['keys']] == list(typed[1]) else 'other'

    def prepare_typed_keys(self, keys, secret_flags):
        """Called by the engine with a keyboard action's whole text before its
        keys are sent one by one: kept for matching recorded inputs on what
        they typed. A secret's keys are not kept, only that it was one. The
        keys go on unchanged."""
        _, _, log_id = self._caller()
        self._typed = (log_id, None if any(secret_flags) else [str(k) for k in keys])
        self._typed_n = len(keys)
        return keys, secret_flags

    def _unhold(self):
        """Held at an input the script does not make (or at the end of a
        recording) for more than hold_s: go on as a recorded visit to the same
        screen went on without input. The visit is one that lasted at least as
        long as the device has shown this screen, entered that far in, so a
        screen that usually changes after 20 s does so here too, and a long
        stuck load is drawn as often as visits that long happened, not in
        proportion to its length."""
        ri, t, held = self._now()
        if held <= self.hold_s:
            return
        fi, (_, frame, state) = self._frame(ri, t)
        on_screen = sim_clock.time() - self._state_since if self._state_since is not None else held
        pool = [v for v in self.visits.get(state, []) if v[2] - v[1] > on_screen and v[0] != ri]
        if not pool:
            if not getattr(self, '_told_no_visit', None) == (ri, fi):
                self._told_no_visit = (ri, fi)
                self.counts['no visit this long'] += 1
                self._log('no visit this long', run=self.runs[ri]['id'], frame=frame, state=state,
                          on_screen_s=round(on_screen, 3), visits=len(self.visits.get(state, [])))
            return
        rj, start, end = pool[self._draw(len(pool), 'went on', state)]
        r = self.runs[rj]
        tf = start + on_screen
        self._at(rj, tf, bisect.bisect_right(r['_it'], tf) - 1)
        self.counts['went on without input'] += 1
        self._log('went on without input', run=self.runs[ri]['id'], frame=frame, state=state, held_s=round(held, 3),
                  on_screen_s=round(on_screen, 3), to_run=r['id'], to_t=round(tf, 3), visits=len(pool))

    # ---- DeviceManager --------------------------------------------------

    def ensure_device_initialized(self):
        return True

    def get_status(self):
        return 'online'

    def screenshot(self, *args, **kwargs):
        with self._lock:
            self._unhold()
            ri, t, _ = self._now()
            fi, (_, frame, state) = self._frame(ri, t)
            if state != self._shown_state:
                self._shown_state, self._state_since = state, sim_clock.time()
            self.counts['screenshots'] += 1
            img = self._image(frame).copy()
        sim_clock.advance(self.screenshot_s)
        return img

    def click(self, x, y, button='left', important=True, mouse_up=True):
        self._input('click', x, y)

    def mouse_down(self, x, y, *args, **kwargs):
        self._mouse_down_at = (x, y)

    def mouse_up(self, x, y, *args, **kwargs):
        down, self._mouse_down_at = self._mouse_down_at, None
        if down is None or (down[0] - x) ** 2 + (down[1] - y) ** 2 <= self.radius ** 2:
            self._input('click', x, y)
        else:
            self._input('drag', down[0], down[1], to=(x, y))

    def smooth_move(self, *args, **kwargs):
        return None

    def click_and_drag(self, source_x, source_y, target_x, target_y, mouse_down=True, mouse_up=True):
        self._input('drag', source_x, source_y, to=(target_x, target_y))
        return [source_x, target_x], [source_y, target_y]

    def live_drag(self, source_x, source_y, target_x, target_y, duration_ms):
        return self.click_and_drag(source_x, source_y, target_x, target_y)

    def scroll(self, x, y, scroll_distance, *args, **kwargs):
        self._input('drag', x, y, to=(x, y - scroll_distance))

    def key_press(self, key):
        self._input('key', keys=[key])

    def key_down(self, key):
        self._input('key', keys=[key])

    def key_up(self, key):
        return None

    def hotkey(self, keys):
        self._input('key', keys=list(keys))

    def start_device(self):
        self._log('start_device')

    def stop_device(self):
        self._log('stop_device')

    def list_applications(self):
        return dict(self.pack.get('applications') or {})

    def start_application(self, application_path, args=None):
        self._log('start_application', application=application_path)

    def stop_application(self, application_name):
        self._log('stop_application', application=application_name)

    # ---- log ------------------------------------------------------------

    def _log(self, event, **fields):
        line = {'event': event, 'clock': round(sim_clock.time(), 3)}
        line.update(fields)
        text = json.dumps(line, default=_plain)
        script_logger.log('SIMULATED DEVICE:', text, level='debug')
        if self.log_path:
            try:
                with open(self.log_path, 'a', encoding='utf-8') as f:
                    f.write(text + '\n')
            except OSError:
                pass

    def summary(self):
        return dict(self.counts)
