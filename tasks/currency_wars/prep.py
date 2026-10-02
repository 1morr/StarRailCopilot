from dataclasses import dataclass

import numpy as np

from module.base.button import ClickButton
from module.logger import logger
from module.ocr.ocr import Digit, DigitCounter
from tasks.currency_wars.choice import CurrencyWarsChoice
from tasks.currency_wars.assets.assets_currency_wars_run import *

# Board geometry at 1280x720, slots don't move between runs
BENCH_X = [205 + 104 * i for i in range(9)]
BENCH_Y = 595
FRONT_X = [488, 590, 690, 792]
FRONT_Y = 258
# Back row has 6 slots, and expands to 7 when deploy limit reaches 10
BACK_X_6 = [389, 489, 590, 690, 790, 890]
BACK_X_7 = [336, 440, 540, 640, 740, 840, 940]
BACK_Y = 448
# Std of slot center, empty slot ~35, character card ~60+
SLOT_OCCUPIED_STD = 47
EXP_COST = 4
# Orbs spawn on the right side of the board
ORB_SWEEP_X = (850, 1110)
ORB_SWEEP_Y = [90, 140, 190, 240, 290]
# Dragging a character onto the shop button sells it
SELL_AREA = (1190, 610)
# Bench has 9 slots, keep some room for orb rewards
BENCH_SELL_THRESHOLD = 8
BENCH_SELL_COUNT = 3
# Shop has 5 character cards, opened by clicking PREP_CHECK ("商店") and closed by SHOP_OPEN ("收起")
SHOP_CARDS_LEFT = [147 + 224 * i for i in range(5)]


@dataclass
class BenchCharacter:
    index: int
    front: bool
    back: bool

    @property
    def point(self):
        return BENCH_X[self.index], BENCH_Y


@dataclass
class ShopCard:
    index: int
    cost: int
    front: bool
    back: bool

    @property
    def button(self):
        x = SHOP_CARDS_LEFT[self.index] + 100
        return ClickButton((x - 30, 100, x + 30, 160), name=f'SHOP_CARD_{self.index}')


class CurrencyWarsPrep(CurrencyWarsChoice):
    def _slot_occupied(self, x, y) -> bool:
        patch = self.device.image[y - 30:y + 30, x - 25:x + 25]
        return patch.std() > SLOT_OCCUPIED_STD

    def _bench_cards(self) -> list[BenchCharacter]:
        """
        Characters and equipment boxes on bench.
        Position marker on card top-right: upper square lit = can stand front, lower square lit = can stand back.
        Equipment box has no position marker, so it's front=False and back=False.
        """
        image = self.device.image
        cards = []
        for index, x in enumerate(BENCH_X):
            card = image[548:645, x - 42:x + 42]
            if card.std() < 30:
                continue
            top = np.mean(image[553:560, x + 29:x + 36])
            bottom = np.mean(image[562:569, x + 29:x + 36])
            cards.append(BenchCharacter(index=index, front=top > 200, back=bottom > 200))
        return cards

    def _bench_characters(self) -> list[BenchCharacter]:
        return [card for card in self._bench_cards() if card.front or card.back]

    def _bench_boxes(self) -> list[int]:
        return [card.index for card in self._bench_cards() if not card.front and not card.back]

    def _shop_cards(self) -> list[ShopCard]:
        """
        Cards remaining in shop, bought ones become empty slots.
        Position marker is the same as bench cards.
        """
        image = self.device.image
        cards = []
        for index, left in enumerate(SHOP_CARDS_LEFT):
            if image[40:250, left + 10:left + 190].std() < 30:
                continue
            # Cost digit only, coin icon on its left is read as "9"
            button = ClickButton((left + 172, 222, left + 202, 254), name=f'SHOP_COST_{index}')
            cost = Digit(button).ocr_single_line(image)
            top = np.mean(image[47:54, left + 176:left + 182])
            bottom = np.mean(image[62:69, left + 176:left + 182])
            cards.append(ShopCard(index=index, cost=cost, front=top > 200, back=bottom > 200))
        return cards

    def _empty_slots(self, row: str, deploy_total: int) -> list[tuple[int, int]]:
        if row == 'front':
            xs, y = FRONT_X, FRONT_Y
        else:
            xs, y = (BACK_X_7 if deploy_total >= 10 else BACK_X_6), BACK_Y
        return [(x, y) for x in xs if not self._slot_occupied(x, y)]

    def _deploy_counter(self) -> tuple[int, int, int]:
        """
        Deploy counter "current/total" is centered with a person icon on its left,
        so the icon moves with digit count and a fixed OCR area either cuts digits or reads the icon as "1".
        Find the icon as the first column run that differs from background, and OCR on its right.
        """
        x1, y1, x2, y2 = OCR_DEPLOY.area
        crop = self.device.image[y1 + 4:y2 - 4, x1:x2].astype(int)
        background = np.median(crop.reshape(-1, 3), axis=0)
        ink = np.abs(crop - background).sum(axis=2).max(axis=0) > 150
        columns = np.flatnonzero(ink)
        if not columns.size:
            return 0, 0, 0
        # End of the icon, the first gap after the first ink column
        gaps = np.flatnonzero(~ink[columns[0]:])
        if not gaps.size:
            return 0, 0, 0
        text_x1 = x1 + columns[0] + gaps[0] + 3
        return DigitCounter(ClickButton((text_x1, y1, x2, y2), name='OCR_DEPLOY')).ocr_single_line(self.device.image)

    def prep_buy_exp(self):
        """
        Pages:
            in: PREP_CHECK
            out: PREP_CHECK
        """
        logger.hr('Prep buy exp', level=2)
        ocr = Digit(OCR_GOLD)
        previous = None
        no_change = 0
        for _ in range(12):
            self.device.screenshot()
            if self.appear(MAX_LEVEL):
                logger.info('Max level reached')
                break
            gold = ocr.ocr_single_line(self.device.image)
            if gold < EXP_COST:
                break
            # Click didn't take effect, probably during a transition
            if gold == previous:
                no_change += 1
                if no_change >= 2:
                    logger.warning('Gold not decreasing, stop buying exp')
                    break
            elif previous is not None:
                # Gold decreased, last click took effect. Buying 12+ times is not stuck
                self.device.click_record_clear()
            previous = gold
            self.device.click(BUY_EXP)
            # Gold number animates after buying, and level up plays a ~2s animation
            self.device.sleep(1.5)
        # Exp is bought by repeated clicks, don't let them count as stuck
        self.device.click_record_clear()

    def prep_deploy(self):
        """
        Drag characters from bench to empty slots until deploy limit.

        Pages:
            in: PREP_CHECK
            out: PREP_CHECK
        """
        logger.hr('Prep deploy', level=2)
        skipped = set()
        last = None
        unreadable = 0
        for _ in range(20):
            self.device.screenshot()
            if not self.is_prep_ready():
                logger.info('Left prep page, stop deploying')
                break
            current, _, total = self._deploy_counter()
            if total == 0:
                # Counter covered by level up animation or a toast (deploying a duplicate character)
                unreadable += 1
                if unreadable >= 5:
                    logger.warning('Deploy counter unreadable, stop deploying')
                    break
                self.device.sleep(1)
                continue
            unreadable = 0
            if last is not None:
                last_index, last_count = last
                if current <= last_count:
                    logger.info(f'Bench {last_index} not deployed, probably a duplicate')
                    skipped.add(last_index)
            if current >= total:
                logger.info('Deploy full')
                break
            candidates = [c for c in self._bench_characters() if c.index not in skipped]
            if not candidates:
                logger.info('No character to deploy')
                break
            character = candidates[0]
            target = None
            if character.front:
                slots = self._empty_slots('front', total)
                if slots:
                    target = slots[0]
            if target is None and character.back:
                slots = self._empty_slots('back', total)
                if slots:
                    target = slots[0]
            if target is None:
                logger.info(f'No empty slot for bench {character}')
                skipped.add(character.index)
                last = None
                continue
            logger.info(f'Deploy bench {character} -> {target}')
            self.device.drag(character.point, target, point_random=(0, 0, 0, 0),
                             name=f'DEPLOY_{character.index}')
            last = (character.index, current)
            self.device.sleep(0.8)
        self.device.click_record_clear()

    def prep_buy_characters(self):
        """
        Buy characters from shop if there aren't enough to fill deploy slots.
        Without this, the board can't recover after losing all characters,
        some investment strategies turn all characters into gold.

        Pages:
            in: PREP_CHECK
            out: PREP_CHECK
        """
        self.device.screenshot()
        current, _, total = self._deploy_counter()
        characters = self._bench_characters()
        need = total - current - len(characters)
        if total == 0 or need <= 0:
            return
        logger.hr('Prep buy characters', level=2)
        # FIGHT is blocked without any front character
        need_front = len(self._empty_slots('front', total)) == len(FRONT_X) and not any(c.front for c in characters)

        bought = 0
        for _ in self.loop(timeout=30):
            if self.appear(PREP_CHECK, interval=2):
                self.device.click(PREP_CHECK)
                continue
            if not self.appear(SHOP_OPEN):
                continue
            gold = Digit(OCR_GOLD).ocr_single_line(self.device.image)
            cards = [card for card in self._shop_cards() if 0 < card.cost <= gold]
            if bought >= need or not cards or len(self._bench_cards()) >= len(BENCH_X):
                break
            # Front characters first if needed, then the leftmost
            card = sorted(cards, key=lambda c: (need_front and not c.front, c.index))[0]
            logger.info(f'Buy {card}')
            self.device.click(card.button)
            bought += 1
            need_front = need_front and not card.front
            self.device.sleep(0.8)

        for _ in self.loop(timeout=10):
            if self.appear(PREP_CHECK):
                break
            if self.appear_then_click(SHOP_OPEN, interval=2):
                continue
        self.device.click_record_clear()

    def prep_collect_orbs(self):
        """
        Orbs on the right of the board give gold, characters, equipments.
        They are collected by slowly swiping over them, clicking or fast swipes don't work.

        Pages:
            in: PREP_CHECK
            out: PREP_CHECK, or INVEST_STRATEGY_CHECK if an orb gives an investment strategy
        """
        logger.hr('Prep collect orbs', level=2)
        for y in ORB_SWEEP_Y:
            self.device.swipe((ORB_SWEEP_X[0], y), (ORB_SWEEP_X[1], y), duration=(0.8, 0.8),
                              name='ORB_SWEEP', distance_check=False)
            self.device.sleep(0.3)
        self.device.click_record_clear()
        # Rewards fly to bench and investment strategy panel pops up after ~2s
        self.device.sleep(2.5)

    def prep_open_boxes(self):
        """
        Equipment boxes and hiring books take bench slots, a full bench blocks FIGHT.
        Open them and take the leftmost option, equipment area expands when full so it never fails.

        Pages:
            in: PREP_CHECK
            out: PREP_CHECK
        """
        logger.hr('Prep open boxes', level=2)
        # A hired character flies into the slot of its book, its card has no position marker during the animation.
        # Clicking it again opens character detail, so each slot is opened once.
        opened = set()
        for _ in range(10):
            self.device.screenshot()
            if self.handle_character_detail():
                continue
            if not self.is_prep_ready():
                # Box opened, pick an option
                if self.handle_choice_panel():
                    self.device.sleep(1)
                    continue
                break
            boxes = [index for index in self._bench_boxes() if index not in opened]
            if not boxes:
                break
            x = BENCH_X[boxes[0]]
            self.device.click(ClickButton((x - 20, BENCH_Y - 20, x + 20, BENCH_Y + 20), name=f'BOX_{boxes[0]}'))
            opened.add(boxes[0])
            self.device.sleep(1)
        self.device.click_record_clear()

    def handle_character_detail(self) -> bool:
        """
        Character detail panel pops up after clicking a character, it has a sell button.
        Close it with Android back key, the in-game back arrow on upper-left exits currency wars.

        Returns:
            bool: If handled
        """
        if self.appear(CHARACTER_DETAIL, interval=2):
            logger.info('Close character detail')
            self.device.adb_shell(['input', 'keyevent', '4'])
            return True
        return False

    def prep_sell_undeployable(self):
        """
        Sell bench characters that can't be deployed, so bench won't block orbs and supplies.
        Selling is free and gives gold back.

        Pages:
            in: PREP_CHECK
            out: PREP_CHECK
        """
        self.device.screenshot()
        characters = self._bench_characters()
        if len(characters) < BENCH_SELL_THRESHOLD:
            return
        logger.hr('Prep sell', level=2)
        # Sell from the rightmost, so indexes of the remaining ones won't shift
        for character in sorted(characters, key=lambda c: c.index, reverse=True)[:BENCH_SELL_COUNT]:
            logger.info(f'Sell bench {character}')
            self.device.drag(character.point, SELL_AREA, point_random=(0, 0, 0, 0),
                             name=f'SELL_{character.index}')
            self.device.sleep(0.8)
        self.device.click_record_clear()

    def is_prep_ready(self) -> bool:
        """
        Returns:
            bool: True if at prep page with nothing covering it
        """
        if not self.appear(PREP_CHECK):
            return False
        for panel in [INVEST_STRATEGY_CHECK, UNDERFILLED_CHECK, CHARACTER_DETAIL]:
            if self.appear(panel):
                return False
        return not self.is_choice_panel()

    def prep_once(self) -> bool:
        """
        Returns:
            bool: True if ready to fight,
                False if interrupted by a panel (investment strategy from orbs, wish trial),
                let the run loop handle it and come back.

        Pages:
            in: PREP_CHECK
            out: PREP_CHECK
        """
        self.prep_collect_orbs()
        self.device.screenshot()
        if not self.is_prep_ready():
            logger.info('Prep interrupted')
            return False
        self.prep_open_boxes()
        self.prep_buy_characters()
        self.prep_buy_exp()
        self.prep_deploy()
        self.prep_sell_undeployable()
        # Selling or deploying may also trigger panels
        self.device.screenshot()
        if not self.is_prep_ready():
            logger.info('Prep interrupted')
            return False
        return True


if __name__ == '__main__':
    self = CurrencyWarsPrep('dev', task='CurrencyWars')
    self.device.screenshot()
    print(self._bench_characters())
