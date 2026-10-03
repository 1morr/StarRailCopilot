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
from tasks.currency_wars.board import BENCH_X, FRONT_X
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
    # Black Swan's fortune teller, options cost in-run gold
    ('cw_fortune', (210, 125, 532, 327)),
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
    ('cw_fortune', 482),
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
    assert self._empty_slots('front') == [(488, 258)]
    assert [x for x, _ in self._empty_slots('back')] == [389, 690, 790, 890]
    # cw_82: back row in 7 slots, only the last one is empty
    self = bare(CurrencyWarsPrep, 'cw_82')
    assert self._empty_slots('back') == [(940, 448)]


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
    ('cw_maxed', True),
    ('cw_05', False),
    ('cw_96', False),
])
def test_promotion_max(name, expected):
    assert bare(CurrencyWars, name).is_promotion_max() is expected


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


def status_maxed(score=18000):
    # Weekly extra counter shows "当前晋升等级已满级" instead of numbers
    return CurrencyWarsStatus(score=score, score_total=18000, weekly_extra=0, weekly_extra_total=0,
                              promotion_level=170, promotion_max=True)


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
    # Promotion level maxed, no more promotion points to farm once score is full
    ({'max_runs': 9999}, status_maxed(), 0, True),
    ({'max_runs': 9999}, status_maxed(score=8000), 5, False),
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
        self.drags = []

    def click(self, button):
        from module.device.device import Device
        self.clicks.append(button.name)
        self.click_record.append(button.name)
        Device.click_record_check(self)

    def click_record_clear(self):
        self.click_record.clear()

    def drag(self, p1, p2, point_random=None, name=None):
        self.drags.append((p1, p2))
        self.click(SimpleNamespace(name=name))

    def swipe(self, p1, p2, **kwargs):
        self.drags.append((p1, p2))

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
    # All grey at low level, OCR read the narrow "1" as "一"
    ('cw_shop_grey', [(0, 1, True, False), (1, 1, True, True), (2, 1, False, True), (3, 1, True, True),
                      (4, 1, True, False)]),
])
def test_shop_cards(name, expected):
    cards = bare(CurrencyWarsPrep, name)._shop_cards()
    assert [(c.index, c.cost, c.front, c.back) for c in cards] == expected


def test_empty_board_needs_characters():
    # All characters turned into gold by an investment strategy, prep must buy from shop
    self = bare(CurrencyWarsPrep, 'cw_empty_board')
    assert self._deploy_counter() == (0, 9, 9)
    assert self._bench_characters() == []
    assert len(self._empty_slots('front')) == 4


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


@pytest.mark.parametrize('name, slots', [
    ('cw_30', 6),
    ('cw_dup_bench', 6),
    # Deploy limit 10 in both, the layout is not decided by the limit
    ('cw_benchfull', 6),
    ('cw_82', 7),
    ('cw_84', 7),
    # Empty board, limit 9
    ('cw_empty_board', 7),
])
def test_back_layout(name, slots):
    assert len(bare(CurrencyWarsPrep, name)._back_x()) == slots


@pytest.mark.parametrize('name, bench, board', [
    # Tiers 1 grey, 2 green, 3 blue, 4 purple, 5 gold, by bench index and board slot x
    ('cw_benchfull', {0: 3, 1: 2, 3: 3, 4: 4, 6: 4, 8: 4},
     {488: 1, 590: 2, 690: 2, 792: 3, 389: 1, 489: 3, 590.5: 4, 690.5: 4}),
    ('cw_82', {0: 1, 1: 5, 2: 5, 3: 1, 4: 4, 5: 4, 6: 1, 7: 1}, {488: 4, 590: 3, 690: 1, 792: 1, 740: 4}),
])
def test_card_tier(name, bench, board):
    self = bare(CurrencyWarsPrep, name)
    assert {c.index: c.tier for c in self._bench_characters()} == bench
    # Back row x may equal a front row x, keys of back slots in the same x get +0.5
    tiers = {}
    for card in self._board_cards():
        tiers[card.x + (0.5 if card.row == 'back' and card.x in FRONT_X else 0)] = card.tier
    for x, tier in board.items():
        assert tiers[x] == tier


@pytest.mark.parametrize('name, deployable', [
    # Bench 2 and 3 are the same character
    ('cw_dup_bench', [0, 1, 2]),
    # Bench 3 is the same as the one in front slot 1
    ('cw_dup_board', [0, 1]),
    # Swapped: front slot 1 now has bench 0 before swapping, bench 0 and 3 are the same
    ('cw_swap', [0, 1]),
])
def test_deployable(name, deployable):
    self = bare(CurrencyWarsPrep, name)
    cards = self._deployable(self._bench_characters(), self._board_cards())
    assert [c.index for c in cards] == deployable


def card(row, x, tier, front=None, back=None):
    from tasks.currency_wars.board import Card
    front = row == 'front' if front is None else front
    back = row == 'back' if back is None else back
    return Card(row, x, tier, front=front, back=back)


def test_deploy_target_empty_slot_first():
    bench = [card('bench', 205, 1, True, True), card('bench', 309, 3, True, False)]
    empty = {'front': [(590, 258)], 'back': [(389, 448)]}
    target = CurrencyWarsPrep._deploy_target(bench, [], empty, current=0, total=3)
    assert (target[0].x, target[1]) == (309, (590, 258))


def test_deploy_target_replaces_lowest():
    # Board full, the purple one replaces the grey one in its row, not the green one
    bench = [card('bench', 205, 4, True, False)]
    board = [card('front', 488, 2), card('front', 590, 1), card('back', 389, 1)]
    target = CurrencyWarsPrep._deploy_target(bench, board, {'front': [], 'back': []}, current=3, total=3)
    assert target[1] == (590, 258)


def test_deploy_target_no_downgrade():
    bench = [card('bench', 205, 2, True, True)]
    board = [card('front', 488, 2), card('back', 389, 3)]
    assert CurrencyWarsPrep._deploy_target(bench, board, {'front': [], 'back': []}, current=2, total=2) is None


@pytest.mark.parametrize('name, expected', [
    # (row, x): stars, other occupied cards are 1-star
    ('cw_82', {('back', 440): 2, ('back', 540): 2}),
    ('cw_hire', {('back', 840): 2}),
    ('cw_benchfull', {}),
    ('cw_detail', {}),
    ('cw_30', {}),
])
def test_card_stars(name, expected):
    self = bare(CurrencyWarsPrep, name)
    for c in self._bench_characters() + self._board_cards():
        assert c.stars == expected.get((c.row, c.x), 1), (c.row, c.x)


@pytest.mark.parametrize('name, rows', [
    # Big orb and a small orb, the small one was missed by fixed sweeps at y 240 and 290
    ('cw_orbs', [(225, 245), (275, 292)]),
    ('cw_dup_bench', [(265, 285)]),
    ('cw_deploy0', []),
])
def test_orb_rows(name, rows):
    found = bare(CurrencyWarsPrep, name)._orb_rows()
    assert len(found) == len(rows)
    for y, (y1, y2) in zip(found, rows):
        assert y1 <= y <= y2


def test_shop_copies():
    # cw_shop_copy: shop card 0 is the character on bench slot 0
    self = bare(CurrencyWarsPrep, 'cw_shop_copy')
    owned = self._bench_characters()
    assert [self._copies(card, owned) for card in self._shop_cards()] == [1, 0, 0, 0, 0]
    self = bare(CurrencyWarsPrep, 'cw_shop_grey')
    owned = self._bench_characters()
    assert [self._copies(card, owned) for card in self._shop_cards()] == [0, 0, 0, 0, 0]


def shop_card(tier, front=True):
    from tasks.currency_wars.board import ShopCard
    return ShopCard(index=0, tier=tier, front=front, back=not front)


@pytest.mark.parametrize('card, copies, lowest, need, need_front, worth', [
    # Copies first, even a grey one
    (shop_card(1), 2, (3, 1), 0, False, True),
    # Fill empty slots with anything
    (shop_card(1), 0, None, 1, False, True),
    # Upgrade only above the lowest deployed
    (shop_card(3), 0, (2, 2), 0, False, True),
    (shop_card(2), 0, (2, 1), 0, False, False),
    (shop_card(2), 0, None, 0, False, False),
])
def test_shop_priority(card, copies, lowest, need, need_front, worth):
    assert (CurrencyWarsPrep._shop_priority(card, copies, lowest, need, need_front) is not None) is worth


def test_shop_priority_order():
    copy = CurrencyWarsPrep._shop_priority(shop_card(1), 1, (3, 1), 1, True)
    fill_front = CurrencyWarsPrep._shop_priority(shop_card(1, front=True), 0, (3, 1), 1, True)
    fill_back = CurrencyWarsPrep._shop_priority(shop_card(5, front=False), 0, (3, 1), 1, True)
    upgrade = CurrencyWarsPrep._shop_priority(shop_card(5), 0, (3, 1), 0, False)
    assert copy < fill_front < fill_back < upgrade


def test_deploy_target_replaces_lower_star():
    # Same quality, the 1-star one is replaced, not the 2-star one
    bench = [card('bench', 205, 3, True, False)]
    board = [card('front', 488, 2), card('front', 590, 2)]
    board[0].stars = 2
    target = CurrencyWarsPrep._deploy_target(bench, board, {'front': [], 'back': []}, current=2, total=2)
    assert target[1] == (590, 258)


def test_deploy_target_quality_over_stars():
    # A 1-star green replaces a 2-star grey, it will be starred up later
    bench = [card('bench', 205, 2, True, False)]
    board = [card('front', 488, 1)]
    board[0].stars = 2
    target = CurrencyWarsPrep._deploy_target(bench, board, {'front': [], 'back': []}, current=1, total=1)
    assert target[1] == (488, 258)


def test_deploy_target_higher_star_same_quality():
    # A merged 2-star on bench replaces a 1-star of the same quality
    bench = [card('bench', 205, 2, True, False)]
    bench[0].stars = 2
    board = [card('front', 488, 2)]
    target = CurrencyWarsPrep._deploy_target(bench, board, {'front': [], 'back': []}, current=1, total=1)
    assert target[1] == (488, 258)


@pytest.mark.parametrize('name, count', [
    # 4 columns of 4 plus a red gem in the 5th column
    ('cw_equipments', 17),
    ('cw_orbs', 0),
    # Front row card at x 792 is not an equipment
    ('cw_30', 0),
    # Golden orbs at the left of the grid are not equipments
    ('cw_orbs_benchfull', 0),
])
def test_equipments(name, count):
    assert len(bare(CurrencyWarsPrep, name)._equipments()) == count


def test_equipped():
    self = bare(CurrencyWarsPrep, 'cw_82')
    equipped = {(c.row, c.x): c.equipped for c in self._board_cards()}
    assert equipped == {
        ('front', 488): 0, ('front', 590): 2, ('front', 690): 1, ('front', 792): 2,
        # Two icons touching each other under 540
        ('back', 336): 1, ('back', 440): 1, ('back', 540): 2, ('back', 640): 1, ('back', 740): 0, ('back', 840): 0,
    }


def test_choice_panel_confirm_after_hint_gone(monkeypatch):
    # "选择伙伴": after selecting, the hint is replaced by the selected one, only "确认选择" remains
    def result(text, box):
        return SimpleNamespace(ocr_text=text, box=box)

    pages = iter([
        [result('请选择伙伴', (1020, 396, 1148, 419)), result('列车同行', (300, 250, 380, 275)),
         result('确认选择', (1045, 440, 1132, 466))],
        [result('本已选择', (300, 400, 380, 420)), result('确认选择', (1045, 440, 1132, 466))],
    ])
    self = bare(CurrencyWarsChoice, 'cw_30')
    self.device = FakeDevice('cw_30')
    monkeypatch.setattr(self, '_choice_ocr', lambda: next(pages))
    assert self.handle_choice_panel()
    assert self.device.clicks == ['CHOICE_OPTION', 'CHOICE_CONFIRM']


def test_choice_panel_already_selected(monkeypatch):
    # Resumed on a panel with an option selected, confirm without clicking the option again
    self = bare(CurrencyWarsChoice, 'cw_30')
    self.device = FakeDevice('cw_30')
    selected = [SimpleNamespace(ocr_text='确认选择', box=(1045, 440, 1132, 466))]
    monkeypatch.setattr(self, '_choice_ocr', lambda: selected)
    assert self.handle_choice_panel()
    assert self.device.clicks == ['CHOICE_CONFIRM']


def test_equip_leaves_unwanted_equipments():
    # Screen never changes, every equipment is refused by everyone.
    # Each one is tried on 3 characters at most, and it never trips the too-many-click check.
    from tasks.currency_wars.prep import EQUIP_TRIES
    self = bare(CurrencyWarsPrep, 'cw_equipments')
    self.device = FakeDevice('cw_equipments')
    self.prep_equip()
    drags = self.device.drags
    assert len(drags) == len(set(drags))
    assert all(sum(item == p1 for p1, _ in drags) <= EQUIP_TRIES for item in self._equipments())
    # Moves on to other equipments instead of giving up
    assert len({p1 for p1, _ in drags}) > 1


def test_deploy_counter_ink_at_right_edge():
    # Only something at the right edge of the counter area, the text crop would be empty and crash OCR
    self = bare(CurrencyWarsPrep, 'cw_30')
    self.device.image = self.device.image.copy()
    self.device.image[128:180, 530:730] = self.device.image[150, 400]
    self.device.image[140:170, 715:722] = 255
    assert self._deploy_counter() == (0, 0, 0)


def test_buy_characters_skips_covered_shop(monkeypatch):
    # Panel pops up after the counter is read, the shop button underneath still matches PREP_CHECK.
    # Clicking it does nothing, never click it.
    self = bare(CurrencyWarsPrep, 'cw_fortune')
    self.device = FakeDevice('cw_fortune')
    monkeypatch.setattr(self, '_wait_deploy_counter', lambda: (3, 5, 8))
    self.prep_buy_characters()
    assert self.device.clicks == []
    # Panel pops up even later, after the check before opening the shop
    ready = iter([True])
    monkeypatch.setattr(self, 'is_prep_ready', lambda: next(ready, False))
    self.prep_buy_characters()
    assert self.device.clicks == []


def test_deploy_target_keeps_unknown_quality():
    # Quality unreadable on board, never replace it
    bench = [card('bench', 205, 4, True, False)]
    board = [card('front', 590, 0)]
    assert CurrencyWarsPrep._deploy_target(bench, board, {'front': [], 'back': []}, current=1, total=1) is None


def test_deploy_replaces_slot_once(monkeypatch):
    # A misread pair would be swapped back and forth, each slot is replaced once at most
    self = bare(CurrencyWarsPrep, 'cw_30')
    self.device = FakeDevice('cw_30')
    swap = (card('bench', 205, 4, True, False), (590, 258))
    monkeypatch.setattr(self, 'is_prep_ready', lambda: True)
    monkeypatch.setattr(self, '_deploy_counter', lambda: (4, 0, 4))
    monkeypatch.setattr(self, '_deploy_target', lambda *args: swap)
    monkeypatch.setattr(self, '_slot_patch', lambda point: np.random.randint(0, 255, (60, 50, 3)))
    self.prep_deploy()
    assert len(self.device.drags) == 1


def test_deploy_target_prefers_unequipped():
    # Two equal greys, the unequipped one is replaced, equipments of a benched character are idle
    bench = [card('bench', 205, 4, True, False)]
    board = [card('front', 488, 1), card('front', 590, 1), card('front', 690, 2)]
    board[0].equipped = 3
    target = CurrencyWarsPrep._deploy_target(bench, board, {'front': [], 'back': []}, current=3, total=3)
    assert target[1] == (590, 258)
    # Quality still comes first, an equipped grey is replaced before an unequipped green
    board[1].equipped = 1
    target = CurrencyWarsPrep._deploy_target(bench, board, {'front': [], 'back': []}, current=3, total=3)
    assert target[1] == (590, 258)


def test_sell_skips_covered_board(monkeypatch):
    # Wish trial panel covers the board, copies on board can't be seen, never sell under it
    self = bare(CurrencyWarsPrep, 'cw_fortune')
    self.device = FakeDevice('cw_fortune')
    bench = [card('bench', x, 4, True, False) for x in BENCH_X]
    monkeypatch.setattr(self, '_bench_characters', lambda: bench)
    monkeypatch.setattr(self, '_board_cards', lambda: [])
    self.prep_sell_undeployable()
    assert self.device.drags == []
    # The same bench is sold once the panel is gone
    monkeypatch.setattr(self, 'is_prep_ready', lambda: True)
    self.prep_sell_undeployable()
    assert len(self.device.drags) == 3


def test_collect_orbs_skips_open_shop():
    # Shop opens itself after some nodes, shop cards look like orbs
    self = bare(CurrencyWarsPrep, 'cw_shop_grey')
    self.device = FakeDevice('cw_shop_grey')
    assert self._orb_rows()
    self.prep_collect_orbs()
    assert self.device.drags == []


def test_collect_orbs_sells_full_bench():
    # Orbs can't be opened with a full bench. Screen never changes, so selling doesn't free a slot,
    # orbs are left instead of being swiped in vain.
    from tasks.currency_wars.prep import SELL_AREA
    self = bare(CurrencyWarsPrep, 'cw_orbs_benchfull')
    self.device = FakeDevice('cw_orbs_benchfull')
    assert self._orb_rows()
    self.prep_collect_orbs()
    assert self.device.drags
    assert all(p2 == SELL_AREA for _, p2 in self.device.drags)


@pytest.mark.parametrize('name, order', [
    # Bench 413 and 517 are the same grey, not on board, more copies won't be bought
    ('cw_dup_bench', [517, 413, 309, 205]),
    # Bench 517 is the same as front slot 1, kept to merge
    ('cw_dup_board', [309, 205, 517]),
])
def test_sell_order(name, order):
    self = bare(CurrencyWarsPrep, name)
    cards = self._sell_order(self._bench_characters(), self._board_cards())
    assert [c.x for c in cards] == order


def test_buy_characters_leaves_strategy_panel(monkeypatch):
    # Investment strategy pops up after the shop button is clicked, neither shop nor prep page shows up
    import time
    self = bare(CurrencyWarsPrep, 'cw_28')
    self.device = FakeDevice('cw_28')
    monkeypatch.setattr(self, '_wait_deploy_counter', lambda: (3, 5, 8))
    monkeypatch.setattr(self, 'is_prep_ready', lambda: True)
    start = time.time()
    self.prep_buy_characters()
    assert time.time() - start < 5
    assert self.device.clicks == []
