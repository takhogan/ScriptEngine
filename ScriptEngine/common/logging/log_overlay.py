"""Log overlays: annotated log images stored as drawing instructions.

An action's annotated log image (match boxes, click points, drag paths, ...) is
not written as pixels. The action's input screenshot is written once as a plain
PNG, and the annotations are written as an overlay document that says how to
redraw them on top of it. The screenshot stays usable as a test input, and a
run stores one image per screenshot instead of two.

The overlay is written as a self-rendering HTML file (`*.overlay.html`):
opening it in a browser draws the annotated image using log_overlay_renderer.js,
which is inlined into the page. The instructions themselves live in a
`<script type="application/json" id="screenplan-overlay">` block, so readers
(this module, script-studio, the log video) parse that block and never need to
run the page's script.

Document shape (version 1):

    {
      "format": "screenplan.overlay", "version": 1,
      "kind": "detectObject",                # producing action, informational
      "width": W, "height": H,               # output canvas, starts black
      "images": {                            # named source images, stored as PNGs
        "capture": {"path": "<data-root-relative>", "href": "<relative to the html>"}
      },
      "pre": "capture",                      # the image that is the action's input
      "layers": [ ... ]                      # drawn in order
    }

An overlay only says how to draw. The numbers behind it (match boxes and
scores, click points, drag paths) are the action's result fields, in its
result.json (see action_result.py): builders return them as `Overlay.result`
and log_overlay merges them into the action's result.

Layer ops. Coordinates are integer pixels and every op follows the OpenCV call
it replaces, so the Python renderer reproduces the old images exactly:

    image    {"image": k, "at": [x, y], "src": [sx, sy, w, h]?}
             paste (no blending), clipped to the canvas; `src` limits the part
             of the image that is pasted
    blur     {"kernel": n}  GaussianBlur(n x n, sigma 0, BORDER_REPLICATE) of the canvas
    group    {"opacity": a, "layers": [...]}
             draw the layers on a copy of the canvas, then
             canvas = addWeighted(copy, a, canvas, 1 - a)
    frame    {"at": [x, y], "width": w, "height": h, "layers": [...]}
             draw the layers on a new black w x h canvas (local coordinates,
             clipped to it), then paste it at `at`
    rect     {"p1": [x, y], "p2": [x, y], "color": "#rrggbb", "thickness": t}
             cv2.rectangle: corners inclusive, thickness -1 fills
    circle   {"center": [x, y], "radius": r, "color": "#rrggbb", "thickness": t}
    polyline {"points": [[x, y], ...], "color": "#rrggbb", "thickness": t}
             one cv2.line per consecutive pair of points
    mask     {"image": k, "at": [x, y], "color": "#rrggbb"}
             a radius-1 filled circle at every pixel of the mask that is > 1,
             offset by `at`. Mask images are stored as BGRA PNGs with the mask
             in the alpha channel (see mask_image), so a browser can draw them
             without reading pixels.

Colors are RGB hex. OpenCV's BGR tuples are converted with bgr_to_hex.

The action's pre_file is always the image it consumed, the same pixels the
action ran on. For an action without an input expression that is the
screenshot. When the input is another action's output (a detect inside an
earlier match, a detect or OCR on an imageTransformation result), it is that
output, and the screenshot is still referenced for context. Images are written
through LOG_IMAGE_STORE, so when an action consumes the exact array an earlier
action logged (an imageTransformation output, say), its pre_file is that
earlier file rather than a copy.
"""
import json
import os
import re
import threading
import weakref

import cv2
import numpy as np

from ScriptEngine.common.constants.script_engine_constants import LOGS_FOLDER, relative_data_path, resolve_data_path

OVERLAY_FORMAT = 'screenplan.overlay'
OVERLAY_VERSION = 1
OVERLAY_FILE_TYPE = 'overlay'
OVERLAY_EXTENSION = '.overlay.html'

_RENDERER_JS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log_overlay_renderer.js')
_DATA_BLOCK_RE = re.compile(
    r'<script type="application/json" id="screenplan-overlay">(.*?)</script>',
    re.DOTALL
)


def bgr_to_hex(bgr):
    b, g, r = (int(channel) for channel in bgr)
    return '#{:02x}{:02x}{:02x}'.format(r, g, b)


def hex_to_bgr(color):
    color = color.lstrip('#')
    return (int(color[4:6], 16), int(color[2:4], 16), int(color[0:2], 16))


def int_point(point):
    return [int(point[0]), int(point[1])]


def mask_image(mask):
    """A mask in the form mask layers store: BGRA, mask pixels (> 1) opaque."""
    stored = np.zeros(mask.shape[:2] + (4,), np.uint8)
    stored[:, :, 3][mask > 1] = 255
    return stored


class Overlay:
    """An overlay document under construction, plus the pixel arrays it names.

    `images` maps keys to ndarrays, written as PNGs when the overlay is saved.
    `pre_image_key` names the image the action consumed, which becomes its
    pre_file. `result` holds result fields (action_result.py) the builder
    worked out while drawing; they go to the action's result file, not into
    the overlay.
    """

    def __init__(self, kind, width, height, pre_image_key='capture'):
        self.kind = kind
        self.width = int(width)
        self.height = int(height)
        self.pre_image_key = pre_image_key
        self.images = {}
        self.layers = []
        self.result = {}

    def to_document(self, image_refs):
        return {
            'format': OVERLAY_FORMAT,
            'version': OVERLAY_VERSION,
            'kind': self.kind,
            'width': self.width,
            'height': self.height,
            'images': image_refs,
            'pre': self.pre_image_key,
            'layers': self.layers,
        }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _to_bgr(image):
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image


def _paste(canvas, image, x, y):
    """canvas[y:y+h, x:x+w] = image, clipped to the canvas on every side."""
    h, w = image.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, canvas.shape[1]), min(y + h, canvas.shape[0])
    if x1 <= x0 or y1 <= y0:
        return
    canvas[y0:y1, x0:x1] = image[y0 - y:y1 - y, x0 - x:x1 - x]


_MASK_STAMP = cv2.circle(np.zeros((3, 3), np.uint8), (1, 1), 1, 1, -1)


def _draw_layers(canvas, layers, images):
    for layer in layers:
        op = layer['op']
        if op == 'image':
            image = _to_bgr(images[layer['image']])
            if 'src' in layer:
                sx, sy, sw, sh = layer['src']
                image = image[sy:sy + sh, sx:sx + sw]
            _paste(canvas, image, *layer['at'])
        elif op == 'blur':
            kernel = int(layer['kernel'])
            canvas[:] = cv2.GaussianBlur(canvas, (kernel, kernel), 0, borderType=cv2.BORDER_REPLICATE)
        elif op == 'group':
            overlay = canvas.copy()
            _draw_layers(overlay, layer['layers'], images)
            opacity = float(layer['opacity'])
            canvas[:] = cv2.addWeighted(overlay, opacity, canvas, 1 - opacity, 0)
        elif op == 'frame':
            frame = np.zeros((int(layer['height']), int(layer['width']), 3), np.uint8)
            _draw_layers(frame, layer['layers'], images)
            _paste(canvas, frame, *layer['at'])
        elif op == 'rect':
            cv2.rectangle(canvas, tuple(layer['p1']), tuple(layer['p2']),
                          hex_to_bgr(layer['color']), int(layer['thickness']))
        elif op == 'circle':
            cv2.circle(canvas, tuple(layer['center']), int(layer['radius']),
                       hex_to_bgr(layer['color']), int(layer['thickness']))
        elif op == 'polyline':
            points = layer['points']
            for start, end in zip(points, points[1:]):
                cv2.line(canvas, tuple(start), tuple(end),
                         hex_to_bgr(layer['color']), int(layer['thickness']))
        elif op == 'mask':
            # Stamping a radius-1 circle at every mask pixel is a dilation of
            # the mask by that circle's footprint.
            mask = images[layer['image']]
            if mask.ndim == 3:
                mask = mask[:, :, 3] if mask.shape[2] == 4 else mask[:, :, 0]
            # A 1px margin keeps mask pixels just off the canvas, whose
            # stamps still reach onto it.
            stamped = np.zeros((canvas.shape[0] + 2, canvas.shape[1] + 2), np.uint8)
            _paste(stamped, (mask > 1).astype(np.uint8), layer['at'][0] + 1, layer['at'][1] + 1)
            stamped = cv2.dilate(stamped, _MASK_STAMP, borderType=cv2.BORDER_CONSTANT, borderValue=0)
            canvas[stamped[1:-1, 1:-1] > 0] = hex_to_bgr(layer['color'])
        else:
            raise ValueError('unknown overlay op: ' + str(op))


def render(width, height, layers, images):
    canvas = np.zeros((int(height), int(width), 3), np.uint8)
    _draw_layers(canvas, layers, images)
    return canvas


def render_overlay(overlay):
    """Render an in-memory Overlay (its images are still ndarrays)."""
    return render(overlay.width, overlay.height, overlay.layers, overlay.images)


def read_overlay_document(html_path):
    with open(html_path, 'r', encoding='utf-8') as overlay_file:
        match = _DATA_BLOCK_RE.search(overlay_file.read())
    if match is None:
        raise ValueError('no overlay data block in ' + html_path)
    document = json.loads(match.group(1))
    if document.get('format') != OVERLAY_FORMAT:
        raise ValueError('not a screenplan overlay: ' + html_path)
    if document.get('version', 0) > OVERLAY_VERSION:
        raise ValueError('overlay version {} is newer than this reader'.format(document.get('version')))
    return document


def render_overlay_file(html_path, resolve_path=None):
    """Render a saved overlay. `resolve_path` maps a recorded data-root-relative
    path to a readable one (defaults to resolve_data_path)."""
    if resolve_path is None:
        resolve_path = resolve_data_path
    document = read_overlay_document(html_path)

    def load(key, entry):
        flags = cv2.IMREAD_UNCHANGED if entry.get('mask') else cv2.IMREAD_COLOR
        image = cv2.imread(resolve_path(entry['path']), flags)
        if image is None:
            raise FileNotFoundError('overlay image {} not readable: {}'.format(key, entry['path']))
        return image

    images = {key: load(key, entry) for key, entry in document['images'].items()}
    return render(document['width'], document['height'], document['layers'], images)


def is_overlay_path(path):
    return str(path).endswith(OVERLAY_EXTENSION)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

class LogImageStore:
    """Writes each in-memory image to a run's log folder at most once.

    A detect and the click that follows it usually share one screenshot array;
    recording it under its first file lets every later overlay and pre_file in
    the same run point at that file instead of writing it again. Entries are
    keyed by array identity (held weakly, so a freed array's id cannot alias a
    new one) and only reused within the top-level run folder they were written
    in, so a run never references a file another run's retention could delete.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._entries = {}

    @staticmethod
    def _run_root(path):
        relative = os.path.relpath(os.path.abspath(path), os.path.abspath(LOGS_FOLDER))
        root = relative.replace('\\', '/').split('/')[0]
        if root == '..':
            # Outside the logs folder: only share within the same folder.
            return os.path.dirname(os.path.abspath(path))
        return root

    def write(self, image, path):
        """Path of a file holding `image`: an earlier one from this run, or `path` after writing it."""
        run_root = self._run_root(path)
        with self._lock:
            # Drop entries whose arrays are gone so the map stays small.
            for key in [key for key, value in self._entries.items() if value[0]() is None]:
                del self._entries[key]
            entry = self._entries.get(id(image))
            if entry is not None:
                image_ref, existing_path, existing_root = entry
                if image_ref() is image and existing_root == run_root:
                    return existing_path
            # Never overwrite a file an earlier overlay still points at.
            taken = {value[1] for value in self._entries.values()}
            stem, extension = os.path.splitext(path)
            suffix = 1
            while path in taken:
                suffix += 1
                path = '{}-{}{}'.format(stem, suffix, extension)
            cv2.imwrite(path, image)
            self._entries[id(image)] = (weakref.ref(image), path, run_root)
            return path


LOG_IMAGE_STORE = LogImageStore()


def _href(target_path, html_path):
    return os.path.relpath(os.path.abspath(target_path), os.path.dirname(os.path.abspath(html_path))).replace('\\', '/')


_renderer_js_source = None


def _renderer_js():
    # A missing renderer (a build that left the .js out) must not lose the
    # log: the data block is complete without it, and only the in-browser
    # view is affected.
    global _renderer_js_source
    if _renderer_js_source is None:
        try:
            with open(_RENDERER_JS_PATH, 'r', encoding='utf-8') as renderer_file:
                _renderer_js_source = renderer_file.read()
        except OSError:
            _renderer_js_source = (
                "document.getElementById('screenplan-overlay-error').textContent = "
                "'This engine build is missing log_overlay_renderer.js, so this overlay cannot be shown here.';"
            )
    return _renderer_js_source


def overlay_html(document, title):
    data = json.dumps(document, separators=(',', ':')).replace('</', '<\\/')
    return (
        '<!doctype html>\n'
        '<html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>' + title.replace('&', '&amp;').replace('<', '&lt;') + '</title>'
        '<style>body{margin:0;background:#202020;color:#ddd;font:13px sans-serif}'
        'canvas{display:block;max-width:100%;height:auto;margin:0 auto}'
        '#screenplan-overlay-error{padding:16px}</style></head>\n'
        '<body><canvas id="screenplan-overlay-canvas"></canvas>'
        '<div id="screenplan-overlay-error"></div>\n'
        '<script type="application/json" id="screenplan-overlay">' + data + '</script>\n'
        '<script>\n' + _renderer_js() + '\n</script>\n'
        '</body></html>\n'
    )


def write_overlay(overlay, html_path, image_paths, store=LOG_IMAGE_STORE):
    """Write `overlay` to `html_path`, writing its pixel images first.

    `image_paths` maps each image key to the PNG path to use if the store has
    not already written that array. Returns {key: path} for every image, so
    callers can point pre_file at the one the action consumed.
    """
    mask_keys = {layer['image'] for layer in _walk(overlay.layers) if layer['op'] == 'mask'}
    written = {}
    image_refs = {}
    for key, image in overlay.images.items():
        path = store.write(image, image_paths[key])
        written[key] = path
        image_refs[key] = {'path': relative_data_path(path), 'href': _href(path, html_path)}
        if key in mask_keys:
            image_refs[key]['mask'] = True
    title = os.path.basename(html_path)[:-len(OVERLAY_EXTENSION)]
    with open(html_path, 'w', encoding='utf-8') as html_file:
        html_file.write(overlay_html(overlay.to_document(image_refs), title))
    return written


def _walk(layers):
    for layer in layers:
        yield layer
        if 'layers' in layer:
            yield from _walk(layer['layers'])


def log_overlay(overlay, name):
    """Save `overlay` as the current action's post file.

    The overlay's images are written next to the action's other log files as
    `<prefix><key>.png` (unless this run already wrote that array), its pre
    image becomes the action's pre_file (the input to load in the editor or
    replay the action against), and its result fields go to the action's
    result file.
    """
    from ScriptEngine.common.logging.script_logger import ScriptLogger
    script_logger = ScriptLogger.get_logger()
    prefix = script_logger.get_log_path_prefix()
    action_log = script_logger.get_action_log()
    image_paths = {key: prefix + key + '.png' for key in overlay.images}
    written = write_overlay(overlay, prefix + name + OVERLAY_EXTENSION, image_paths)
    if overlay.pre_image_key in written:
        action_log.set_pre_file('image', written[overlay.pre_image_key], absolute_path=True)
    action_log.set_post_file(OVERLAY_FILE_TYPE, name + OVERLAY_EXTENSION)
    if overlay.result:
        action_log.update_result(overlay.result)


def log_image_file(script_logger, image, relative_path, role):
    """Record a plain image as the current action's pre or post file.

    Goes through LOG_IMAGE_STORE, so an image some earlier action in the run
    already logged is referenced rather than written again: an
    imageTransformation output consumed by the next action is one file that is
    both the first action's post_file and the second's pre_file.
    """
    path = LOG_IMAGE_STORE.write(image, script_logger.get_log_path_prefix() + relative_path)
    action_log = script_logger.get_action_log()
    if role == 'pre':
        action_log.set_pre_file('image', path, absolute_path=True)
    else:
        action_log.set_post_file('image', path, absolute_path=True)
    return path
