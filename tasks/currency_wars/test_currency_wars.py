"""
Screenshot regression tests for Currency Wars detectors.
Fixtures in test_data/ are 1280x720 screenshots from CN client, JPEG compressed.

    python -m pytest tasks/currency_wars/test_currency_wars.py
"""
import os
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from module.base.utils import load_image
from module.config import server

server.set_lang('cn')

from tasks.base.assets.assets_base_page import CURRENCY_WARS_CHECK
from tasks.currency_wars.assets.assets_currency_wars_entry import *
from tasks.currency_wars.assets.assets_currency_wars_run import *
from tasks.currency_wars.choice import CurrencyWarsChoice
from tasks.currency_wars.currency_wars import CurrencyWars
from tasks.currency_wars.entry import CurrencyWarsStatus
from tasks.currency_wars.invest import CurrencyWarsInvest, ENV_CARDS_X, STRATEGY_CARDS_X
from tasks.currency_wars.prep import CurrencyWarsPrep

DATA = os.path.join(os.path.dirname(__file__), 'test_data')


def image(name):
    return load_image(os.path.join(DATA, f'{name}.jpg'))


def bare(cls, name):
    """Instance without config or device, only `device.image` is used by detectors"""
    self = cls.__new__(cls)
    self.device = SimpleNamespace(image=image(name), stuck_record_add=lambda button: None)
    self.interval_timer = {}
    return self


@pytest.mark.parametrize('button, positive, negative', [
    (CURRENCY_WARS_CHECK, 'cw_95', 'cw_96'),
    (ENTER_OVERCLOCK, 'cw_05', 'cw_96'),
    (PREP_CHECK, 'cw_30', 'cw_36'),
    (SUPPLY_CHECK, 'cw_36', 'cw_30'),
    (INVEST_ENV_CHECK, 'cw_11', 'cw_28'),
    (INVEST_STRATEGY_CHECK, 'cw_28', 'cw_11'),
    # Unfinished run after disconnection, it replaces the enter button
    (CONTINUE_PROGRESS, 'cw_continue', 'cw_05'),
    (ENTER_OVERCLOCK, 'cw_05', 'cw_continue'),
    (MAX_LEVEL, 'cw_84', 'cw_30'),
    (NO_FRONT_CHECK, 'cw_nofront', 'cw_deploy0'),
    # Character detail with a sell button, opened by clicking a bench character
    (CHARACTER_DETAIL, 'cw_detail', 'cw_30'),
])
def test_page_check(button, positive, negative):
    assert button.match_template(image(positive))
    assert not button.match_template(image(negative))


@pytest.mark.parametrize('name, cards, expected', [
    ('cw_11', ENV_CARDS_X, [255, 1023]),
    ('cw_28', STRATEGY_CARDS_X, []),
    ('cw_52', STRATEGY_CARDS_X, [270, 1012]),
    ('cw_76', STRATEGY_CARDS_X, [270, 1012]),
])
def test_unrecorded_cards(name, cards, expected):
    assert bare(CurrencyWarsInvest, name)._unrecorded_cards(cards) == expected


def test_unrecorded_cards_ignores_blank_icon_area():
    # Mutation: wipe the book icon, the card must no longer count as unrecorded
    self = bare(CurrencyWarsInvest, 'cw_52')
    self.device.image = self.device.image.copy()
    self.device.image[110:180, 340:420] = 0
    assert self._unrecorded_cards(STRATEGY_CARDS_X) == [1012]


def test_bench_characters():
    # cw_27: bench slot 5 front-only, slot 6 back-only, others empty
    characters = bare(CurrencyWarsPrep, 'cw_27')._bench_characters()
    assert [(c.index, c.front, c.back) for c in characters] == [(5, True, False), (6, False, True)]


def test_bench_boxes():
    # cw_benchfull: 6 characters and 3 equipment boxes fill the bench, FIGHT is blocked
    self = bare(CurrencyWarsPrep, 'cw_benchfull')
    assert self._bench_boxes() == [2, 5, 7]
    assert [c.index for c in self._bench_characters()] == [0, 1, 3, 4, 6, 8]
    # Hiring book is opened the same way as equipment boxes
    assert bare(CurrencyWarsPrep, 'cw_hire')._bench_boxes() == [6]


@pytest.mark.parametrize('name, expected', [
    ('cw_30', True),
    # Wish trial panel covers the board, but the shop button underneath still matches PREP_CHECK
    ('cw_wish', False),
    # Hack effect panel, confirm button at a different height
    ('cw_hack', False),
    # Star of the gala panel, dimmed, confirm template doesn't match
    ('cw_star', False),
    # Investment strategy from orbs
    ('cw_28', False),
    # Equipment box panel
    ('cw_box', False),
    # Expert invitation, covers the deploy counter
    ('cw_expert', False),
    ('cw_hire', False),
    ('cw_detail', False),
    # Red warning of full bench doesn't cover anything
    ('cw_benchfull', True),
])
def test_is_prep_ready(name, expected):
    assert bare(CurrencyWarsPrep, name).is_prep_ready() is expected


@pytest.mark.parametrize('name, x_range', [
    # 5 cards, leftmost name at x 61-105
    ('cw_36', (40, 130)),
    # 3 cards centered, leftmost name at x ~310-350
    ('cw_supply3', (290, 370)),
])
def test_supply_card(name, x_range):
    from tasks.currency_wars.run import CurrencyWarsRun
    x1, _, x2, _ = bare(CurrencyWarsRun, name).supply_card().button
    assert x_range[0] <= (x1 + x2) // 2 <= x_range[1]


# Every choice panel seen so far. A new panel usually needs only a screenshot here, not new code.
# (name, first option card area x1, y1, x2, y2)
CHOICE_PANELS = [
    ('cw_wish', (230, 140, 590, 410)),
    ('cw_hack', (310, 120, 690, 330)),
    # Dimmed by network lag
    ('cw_star', (522, 122, 704, 290)),
    ('cw_box', (285, 97, 500, 243)),
    ('cw_box2', (285, 97, 500, 243)),
    ('cw_hire', (258, 97, 458, 320)),
    # The first card is locked until 1-6 but still selectable
    ('cw_expert', (147, 97, 347, 320)),
]


@pytest.mark.parametrize('name, expected', [(name, True) for name, _ in CHOICE_PANELS] + [
    ('cw_30', False),
    ('cw_36', False),
    ('cw_11', False),
    ('cw_benchfull', False),
    ('cw_detail', False),
])
def test_is_choice_panel(name, expected):
    assert bare(CurrencyWarsChoice, name).is_choice_panel() is expected


@pytest.mark.parametrize('name', [name for name, _ in CHOICE_PANELS])
def test_choice_panel_over_board(name):
    # run_once only looks for choice panels when PREP_CHECK appears, to skip OCR during battle
    assert PREP_CHECK.match_template(image(name))


@pytest.mark.parametrize('name, card', CHOICE_PANELS)
def test_choice_option(name, card):
    self = bare(CurrencyWarsChoice, name)
    x1, y1, x2, y2 = self._choice_option(self._choice_ocr()).button
    x, y = (x1 + x2) // 2, (y1 + y2) // 2
    assert card[0] <= x <= card[2] and card[1] <= y <= card[3]


@pytest.mark.parametrize('name, confirm_y', [
    # Confirm button center y, "确认选择" under the red hint on the right
    ('cw_wish', 517),
    ('cw_hack', 482),
    # Confirm text unreadable before selecting, located from the hint
    ('cw_star', 453),
    # Closed once selected, no confirm
    ('cw_box', None),
    ('cw_hire', None),
    ('cw_expert', None),
])
def test_choice_confirm(name, confirm_y):
    self = bare(CurrencyWarsChoice, name)
    confirm = self._choice_confirm(self._choice_ocr())
    if confirm_y is None:
        assert confirm is None
    else:
        x1, y1, x2, y2 = confirm.button
        assert 1000 <= (x1 + x2) // 2 <= 1180
        assert abs((y1 + y2) // 2 - confirm_y) <= 10


def test_empty_slots():
    # cw_33: front slot 1 empty, back row slot 1,2 occupied
    self = bare(CurrencyWarsPrep, 'cw_33')
    assert self._empty_slots('front', deploy_total=5) == [(488, 258)]
    assert [x for x, _ in self._empty_slots('back', deploy_total=5)] == [389, 690, 790, 890]
    # cw_82: deploy limit 10 switches back row to 7 slots, only the last one is empty
    self = bare(CurrencyWarsPrep, 'cw_82')
    assert self._empty_slots('back', deploy_total=10) == [(940, 448)]


@pytest.mark.parametrize('ocr_class, button, name, expected', [
    ('DigitCounter', OCR_LOBBY_SCORE, 'cw_95', (18000, 0, 18000)),
    ('DigitCounter', OCR_WEEKLY_EXTRA, 'cw_05', (0, 3000, 3000)),
    ('DigitCounter', OCR_WEEKLY_EXTRA, 'cw_96', (3000, 0, 3000)),
    ('Digit', OCR_PROMOTION_LEVEL, 'cw_95', 116),
    ('Digit', OCR_GOLD, 'cw_30', 8),
])
def test_ocr(ocr_class, button, name, expected):
    from module.ocr import ocr
    assert getattr(ocr, ocr_class)(button).ocr_single_line(image(name)) == expected


@pytest.mark.parametrize('name, expected', [
    ('cw_12', (0, 3, 3)),
    ('cw_30', (3, 1, 4)),
    # Fixed areas failed on these: icon read as "1" in "0/4", "8" cut into "3", leading "1" of "10" cut
    ('cw_deploy0', (0, 4, 4)),
    ('cw_benchfull', (8, 2, 10)),
    ('cw_82', (10, 0, 10)),
    ('cw_84', (10, 1, 11)),
])
def test_deploy_counter(name, expected):
    assert bare(CurrencyWarsPrep, name)._deploy_counter() == expected


def test_deploy_counter_fixed_area_fails():
    # Why _deploy_counter() locates the icon: any fixed left edge fails one of the counters above
    from module.base.button import ClickButton
    from module.ocr.ocr import DigitCounter
    for x1 in [570, 590]:
        button = ClickButton((x1, 128, 730, 180), name='OCR_DEPLOY')
        results = [DigitCounter(button).ocr_single_line(image(name)) for name in ['cw_deploy0', 'cw_benchfull', 'cw_82']]
        assert results != [(0, 4, 4), (8, 2, 10), (10, 0, 10)]


def status(score=18000, extra=3000, level=100):
    return CurrencyWarsStatus(score=score, score_total=18000, weekly_extra=extra, weekly_extra_total=3000,
                              promotion_level=level)


def task(max_runs=3, target_level=0):
    self = CurrencyWars.__new__(CurrencyWars)
    self.config = SimpleNamespace(CurrencyWars_MaxRunsPerTask=max_runs,
                                  CurrencyWars_TargetPromotionLevel=target_level)
    return self


@pytest.mark.parametrize('kwargs, st, runs, expected', [
    # Weekly caps not full, always continue regardless of run count
    ({}, status(score=0, extra=0), 5, False),
    ({}, status(extra=1000), 5, False),
    # Weekly full, limited by run count
    ({'max_runs': 3}, status(), 2, False),
    ({'max_runs': 3}, status(), 3, True),
    # Target promotion level, 0 for no limit
    ({'target_level': 120}, status(level=119), 0, False),
    ({'target_level': 120}, status(level=120), 0, True),
    ({'target_level': 0}, status(level=999), 0, False),
    # OCR failure gives total=0, must not be treated as full
    ({}, CurrencyWarsStatus(0, 0, 0, 0, 0), 5, False),
])
def test_should_stop(kwargs, st, runs, expected):
    assert task(**kwargs).should_stop(st, runs) is expected


class FakeDevice:
    """Records clicks with the real too-many-click check, other device calls are no-op"""

    def __init__(self, name):
        import collections
        self.image = image(name)
        self.click_record = collections.deque(maxlen=30)
        self.clicks = []

    def click(self, button):
        from module.device.device import Device
        self.clicks.append(button.name)
        self.click_record.append(button.name)
        Device.click_record_check(self)

    def click_record_clear(self):
        self.click_record.clear()

    def screenshot(self):
        return self.image

    def sleep(self, second):
        pass

    def stuck_record_add(self, button):
        pass

    def image_save(self):
        pass


def test_buy_exp_with_plenty_of_gold(monkeypatch):
    # 70 gold buys exp 12+ times, every click takes effect so it must not be treated as stuck
    golds = iter(range(70, 0, -4))
    monkeypatch.setattr('tasks.currency_wars.prep.Digit',
                        lambda button: SimpleNamespace(ocr_single_line=lambda image: next(golds)))
    self = bare(CurrencyWarsPrep, 'cw_30')
    self.device = FakeDevice('cw_30')
    self.prep_buy_exp()
    assert self.device.clicks.count('BUY_EXP') >= 12


def test_buy_exp_stops_when_gold_unchanged(monkeypatch):
    # Clicks not taking effect, stop after 2 unchanged reads
    golds = iter([40, 36, 36, 36, 36])
    monkeypatch.setattr('tasks.currency_wars.prep.Digit',
                        lambda button: SimpleNamespace(ocr_single_line=lambda image: next(golds)))
    self = bare(CurrencyWarsPrep, 'cw_30')
    self.device = FakeDevice('cw_30')
    self.prep_buy_exp()
    assert self.device.clicks.count('BUY_EXP') == 3


@pytest.mark.parametrize('name, expected', [
    # (index, cost, front, back), cost 3 is red when unaffordable but still readable
    ('cw_shop', [(0, 1, True, True), (1, 2, True, True), (2, 2, True, False), (3, 3, True, False),
                 (4, 2, True, False)]),
    # Bought card leaves an empty slot
    ('cw_shop_bought', [(1, 2, True, True), (2, 2, True, False), (3, 3, True, False), (4, 2, True, False)]),
])
def test_shop_cards(name, expected):
    cards = bare(CurrencyWarsPrep, name)._shop_cards()
    assert [(c.index, c.cost, c.front, c.back) for c in cards] == expected


def test_empty_board_needs_characters():
    # All characters turned into gold by an investment strategy, prep must buy from shop
    self = bare(CurrencyWarsPrep, 'cw_empty_board')
    assert self._deploy_counter() == (0, 9, 9)
    assert self._bench_characters() == []
    assert len(self._empty_slots('front', 9)) == 4


def test_open_boxes_clicks_each_slot_once():
    # Screen never changes, like a hired character still flying into its slot without a position marker.
    # Clicking the same slot again would open character detail.
    self = bare(CurrencyWarsPrep, 'cw_benchfull')
    self.device = FakeDevice('cw_benchfull')
    self.prep_open_boxes()
    assert self.device.clicks == ['BOX_2', 'BOX_5', 'BOX_7']


def test_choice_panel_ignores_board_purchase():
    # "购买经验" on the board under the panel is not a cost of the panel
    self = bare(CurrencyWarsChoice, 'cw_expert')
    self.device = FakeDevice('cw_expert')
    assert self.handle_choice_panel()
    assert self.device.clicks == ['CHOICE_OPTION']


def test_choice_panel_stops_on_cost(monkeypatch):
    from module.exception import RequestHumanTakeover
    self = bare(CurrencyWarsChoice, 'cw_box')
    self.device = FakeDevice('cw_box')
    results = self._choice_ocr()
    # Mutation: an option that costs stellar jade
    option = next(result for result in results if '请选择' not in result.ocr_text)
    option.ocr_text, option.box = '消耗星琼', (300, 200, 400, 230)
    monkeypatch.setattr(self, '_choice_ocr', lambda: results)
    with pytest.raises(RequestHumanTakeover):
        self.handle_choice_panel()
    assert self.device.clicks == []
