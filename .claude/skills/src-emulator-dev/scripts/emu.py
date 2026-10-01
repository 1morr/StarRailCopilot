"""
Thin CLI over SRC's own device / Button / Ocr / UI layers, for development.

Run from repo root with the repo venv:
    .venv/Scripts/python.exe .claude/skills/src-emulator-dev/scripts/emu.py <command> ...

Commands:
    shot [NAME]                      screenshot -> screenshots/<NAME or timestamp>.png
    click X Y | click BUTTON         click a point, or the `button` area of an asset
    swipe X1 Y1 X2 Y2 [DURATION]     swipe, duration in seconds (default 0.3)
    drag X1 Y1 X2 Y2                 press-hold-move-release, for drag and drop
    match BUTTON [--image F]         similarity of every variant of an asset on screen
    ocr BUTTON|X1,Y1,X2,Y2 [--image F] [--digit|--counter]
                                     OCR an asset area or an arbitrary area
    page [--image F]                 which pages in tasks/base/page.py match now
    goto PAGE                        ui_ensure(PAGE), e.g. goto page_main
    asset OUT X1 Y1 X2 Y2 [--image F]
                                     write a 1280x720 asset PNG keeping only the area,
                                     OUT like assets/share/currency_wars/lobby/FOO.png

Add -v to any command to keep SRC's INFO log.
BUTTON is either an asset name (resolved by scanning tasks/*/assets/*.py)
or `module.path:NAME`.
Env: SRC_DEV_CONFIG (default "dev"), ANDROID_ADB_SERVER_PORT (default 5038).
"""
import os
import re
import sys
import time
from datetime import datetime
from importlib import import_module

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
# Own adb server port, so the SDK adb on 5037 won't kill ours (different adb versions)
os.environ.setdefault('ANDROID_ADB_SERVER_PORT', '5038')
CONFIG = os.environ.get('SRC_DEV_CONFIG', 'dev')
SHOT_DIR = os.path.join(ROOT, 'screenshots')

import cv2
import numpy as np


def die(msg):
    print(f'ERROR: {msg}')
    sys.exit(1)


def pop_opt(args, name, has_value=True):
    if name not in args:
        return None
    i = args.index(name)
    if has_value:
        value = args[i + 1]
        del args[i:i + 2]
        return value
    del args[i]
    return True


def find_button(ref):
    if ':' in ref:
        mod, name = ref.split(':', 1)
        return getattr(import_module(mod), name)
    regex = re.compile(rf'^{re.escape(ref)} = ButtonWrapper\(', re.M)
    for folder, _, files in os.walk('tasks'):
        if not folder.replace('\\', '/').endswith('/assets'):
            continue
        for file in files:
            if not file.endswith('.py'):
                continue
            path = os.path.join(folder, file)
            with open(path, encoding='utf-8') as f:
                if regex.search(f.read()):
                    mod = path[:-3].replace('\\', '/').replace('/', '.')
                    return getattr(import_module(mod), ref)
    die(f'Asset not found: {ref}')


def area_button(area):
    from module.base.button import Button, ButtonWrapper
    area = tuple(int(v) for v in area.split(','))
    return ButtonWrapper(name='AREA', share=Button(
        file='', area=area, search=area, color=(0, 0, 0), button=area))


def load_rgb(file):
    from module.base.utils import load_image
    return load_image(file)


def config():
    from module.config.config import AzurLaneConfig
    from module.config import server
    c = AzurLaneConfig(CONFIG, task=None)
    server.set_lang(c.Emulator_GameLanguage if c.Emulator_GameLanguage != 'auto' else 'cn')
    return c


def device(c):
    from module.device.device import Device
    return Device(c)


def image_or_screenshot(args):
    file = pop_opt(args, '--image')
    c = config()
    if file:
        return c, None, load_rgb(file)
    d = device(c)
    d.screenshot()
    return c, d, d.image


def save_rgb(image, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cv2.imwrite(path, cv2.cvtColor(image, cv2.COLOR_RGB2BGR))


def cmd_shot(args):
    c = config()
    d = device(c)
    d.screenshot()
    name = args[0] if args else datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
    path = os.path.join(SHOT_DIR, f'{name}.png')
    save_rgb(d.image, path)
    print(path)


def cmd_click(args):
    c = config()
    d = device(c)
    if len(args) == 2 and all(a.isdigit() for a in args):
        x, y = int(args[0]), int(args[1])
        from module.base.button import ClickButton
        d.click(ClickButton((x, y, x + 1, y + 1), name=f'POINT_{x}_{y}'), control_check=False)
    else:
        button = find_button(args[0])
        d.screenshot()
        # Load offset if the asset is movable
        button.match_template(d.image)
        d.click(button, control_check=False)
    time.sleep(0.3)


def cmd_swipe(args):
    c = config()
    d = device(c)
    x1, y1, x2, y2 = (int(v) for v in args[:4])
    duration = float(args[4]) if len(args) > 4 else 0.3
    d.swipe((x1, y1), (x2, y2), duration=(duration, duration), distance_check=False)
    time.sleep(0.3)


def cmd_drag(args):
    c = config()
    d = device(c)
    x1, y1, x2, y2 = (int(v) for v in args[:4])
    d.drag((x1, y1), (x2, y2), point_random=(0, 0, 0, 0))
    time.sleep(0.3)


def _sim(template, image):
    res = cv2.matchTemplate(template, image, cv2.TM_CCOEFF_NORMED)
    _, sim, _, point = cv2.minMaxLoc(res)
    return sim, point


def cmd_match(args):
    from module.base.utils import crop, get_color, rgb2luma
    _, _, image = image_or_screenshot(args)
    wrapper = find_button(args[0])
    for button in wrapper.buttons:
        area = crop(image, button.search, copy=False)
        sim, point = _sim(button.image, area)
        luma, _ = _sim(button.image_luma, rgb2luma(area))
        offset = np.array(point) + button.search[:2] - button.area[:2]
        color = np.round(get_color(image, button.area)).astype(int).tolist()
        print(f'{button.file}\n'
              f'  template={sim:.3f} luma={luma:.3f} (pass >0.85) offset={tuple(offset.tolist())}\n'
              f'  color now={color} asset={list(button.color)} (match_color threshold 10)\n'
              f'  area={button.area} search={button.search} button={button._button}')


def cmd_ocr(args):
    from module.ocr.ocr import Ocr, Digit, DigitCounter
    cls = Ocr
    if pop_opt(args, '--digit', has_value=False):
        cls = Digit
    if pop_opt(args, '--counter', has_value=False):
        cls = DigitCounter
    c, _, image = image_or_screenshot(args)
    ref = args[0]
    button = area_button(ref) if re.match(r'^\d+,\d+,\d+,\d+$', ref) else find_button(ref)
    ocr = cls(button, lang=c.LANG)
    print('single_line:', repr(ocr.ocr_single_line(image)))
    if cls is Ocr:
        for r in ocr.detect_and_ocr(image):
            print(f'  box={tuple(int(v) for v in r.box)} score={r.score:.2f} text={r.ocr_text!r}')


def cmd_page(args):
    from tasks.base.page import Page
    c, d, image = image_or_screenshot(args)
    hits = [p.name for p in Page.iter_pages()
            if p.check_button is not None and p.check_button.match_template(image)]
    print('pages:', hits or 'none')


def cmd_goto(args):
    from tasks.base.ui import UI
    import tasks.base.page as page
    destination = getattr(page, args[0])
    c = config()
    ui = UI(c, device=device(c))
    ui.device.screenshot()
    ui.ui_ensure(destination)


def cmd_asset(args):
    _, _, image = image_or_screenshot(args)
    out = args[0]
    x1, y1, x2, y2 = (int(v) for v in args[1:5])
    if not re.match(r'^assets/(share|cn|en|jp|cht|es)/[\w/]+/[A-Z0-9_]+(\.\d+)?(\.(BUTTON|SEARCH|AREA|COLOR))?\.png$', out):
        die('OUT must look like assets/<share|cn|...>/<module>/<sub>/<NAME>.png')
    canvas = np.zeros_like(image)
    canvas[y1:y2, x1:x2] = image[y1:y2, x1:x2]
    save_rgb(canvas, out)
    print(out)


COMMANDS = {k[4:]: v for k, v in globals().items() if k.startswith('cmd_')}

if __name__ == '__main__':
    argv = sys.argv[1:]
    verbose = pop_opt(argv, '-v', has_value=False)
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    # SRC logs are noisy for one-shot commands, keep warnings only unless -v
    # `goto` is always verbose since its log is the useful output
    if not verbose and argv[0] != 'goto':
        import logging
        from module.logger import logger
        logger.setLevel(logging.WARNING)
        logger.hr = lambda *args, **kwargs: None
    COMMANDS[argv[0]](argv[1:])
