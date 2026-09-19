"""Screenshot + OmniParser V2 (the official omniparser/util code, in process).

The shell's windows (floating input, cursor badge) are excluded from screen
capture (SetWindowDisplayAffinity), so the screenshot shows what is behind
them and OmniParser never parses omni-all itself.
"""
import base64
import io
import os
import sys
import threading
import time

import mss
import mss.exception
from PIL import Image

import config

sys.path.insert(0, str(config.OMNIPARSER_DIR))
os.chdir(config.OMNIPARSER_DIR)  # utils.py opens some files relative to it

_parser = None
_load_lock = threading.Lock()


def load():
    """Loads the detector + captioner once (a few seconds, ~2-4 GB VRAM)."""
    global _parser
    with _load_lock:
        if _parser is None:
            import easyocr
            import util.utils
            from util.omniparser import Omniparser  # heavy import: torch, OCR models

            # Upstream reads English only; accents (ã, ç, é) matter here.
            util.utils.reader = easyocr.Reader(["pt", "en"])
            _parser = Omniparser({
                "som_model_path": str(config.WEIGHTS_DIR / "icon_detect" / "model.pt"),
                "caption_model_name": "florence2",
                "caption_model_path": str(config.WEIGHTS_DIR / "icon_caption_florence"),
                "BOX_TRESHOLD": config.BOX_THRESHOLD,
            })
    return _parser


def screenshot():
    # BitBlt fails now and then (e.g. while a window animates); retry.
    for attempt in range(5):
        try:
            with mss.MSS() as sct:
                shot = sct.grab(sct.monitors[1])  # primary monitor, physical pixels
                return Image.frombytes("RGB", shot.size, shot.rgb)
        except mss.exception.ScreenShotError:
            if attempt == 4:
                raise
            time.sleep(0.4)


def parse(image):
    """Returns (elements, labeled_png_base64, seconds). Each element:
    {id, type: text|icon, content, interactive, box: (x1,y1,x2,y2), center: (x,y)}
    in screen pixels."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    t0 = time.perf_counter()
    labeled, items = load().parse(base64.b64encode(buf.getvalue()).decode())
    w, h = image.size
    elements = []
    for i, it in enumerate(items):
        x1, y1, x2, y2 = it["bbox"]  # ratios
        box = (round(x1 * w), round(y1 * h), round(x2 * w), round(y2 * h))
        elements.append({
            "id": i,
            "type": it["type"],
            "content": (it.get("content") or "").strip(),
            "interactive": bool(it.get("interactivity")),
            "box": box,
            "center": ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2),
        })
    return elements, labeled, time.perf_counter() - t0


def read_text(image):
    """OCR of a small region, with the same easyocr reader OmniParser uses."""
    import numpy as np
    import util.utils

    return " ".join(util.utils.reader.readtext(np.array(image), detail=0))


def _diff(before, after):
    import numpy as np

    return np.abs(np.asarray(before, dtype=np.int16) - np.asarray(after, dtype=np.int16)).max(axis=2) > 30


def changed(before, after):
    """Did anything visible change? (the cursor isn't in screenshots)"""
    return bool(_diff(before, after).any())


def changed_text(before, after):
    """OCR of the bounding box of the pixels that differ between two
    screenshots; None when nothing changed."""
    import numpy as np

    ys, xs = np.nonzero(_diff(before, after))
    if len(xs) == 0:
        return None
    box = (max(0, xs.min() - 6), max(0, ys.min() - 6), xs.max() + 7, ys.max() + 7)
    return read_text(after.crop(box))


def for_model(labeled_b64, width=1280):
    """OmniParser's labeled screenshot (numbered boxes), downscaled for the LLM."""
    img = Image.open(io.BytesIO(base64.b64decode(labeled_b64)))
    return img.resize((width, round(img.height * width / img.width)))


def around(shot, box, pad=(260, 160)):
    """A crop of the screen around a target, with the target outlined, so
    the certainty check looks at the element itself and its surroundings."""
    from PIL import ImageDraw

    x1, y1, x2, y2 = box
    crop = shot.crop((max(0, x1 - pad[0]), max(0, y1 - pad[1]), x2 + pad[0], y2 + pad[1])).copy()
    ox, oy = max(0, x1 - pad[0]), max(0, y1 - pad[1])
    ImageDraw.Draw(crop).rectangle((x1 - ox - 3, y1 - oy - 3, x2 - ox + 3, y2 - oy + 3), outline="red", width=3)
    return crop
