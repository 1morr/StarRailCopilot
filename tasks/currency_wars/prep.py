import cv2

from module.base.button import ClickButton
from module.logger import logger
from module.ocr.ocr import Digit
from tasks.currency_wars.assets.assets_currency_wars_run import *
from tasks.currency_wars.board import BENCH_X, BENCH_Y, Card, CurrencyWarsBoard, EQUIPPED_MAX

EXP_COST = 4
# Orbs spawn on the right side of the board, in various colors and sizes.
# They are opened by slowly swiping over them, swipes start on the left to avoid dragging equipments.
ORB_AREA = (850, 90, 1100, 330)
ORB_SWEEP_X = (850, 1110)
# Dragging a character onto the shop button sells it
SELL_AREA = (1190, 610)
# Bench has 9 slots, keep some room for orb rewards
BENCH_SELL_THRESHOLD = 8
BENCH_SELL_COUNT = 3
# Buy at most this many characters per prep for upgrades or copies, the rest of gold goes to exp for more slots
SHOP_BUY_LIMIT = 3
# Characters to try for an equipment before leaving it, some equipments only fit some characters
EQUIP_TRIES = 3
# Mean pixel change of a slot after dragging, below it the drag didn't take effect
SLOT_CHANGED = 10


class CurrencyWarsPrep(CurrencyWarsBoard):
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

    @staticmethod
    def _deploy_target(bench: list[Card], board: list[Card], empty: dict[str, list], current: int, total: int):
        """
        Returns:
            tuple[Card, tuple[int, int]] | None: Bench character and where to drop it.
                Highest value first, into an empty slot if any,
                otherwise onto a lower value character, which swaps them.
                Among equal ones, the unequipped is replaced, equipments of a benched character are idle.
        """
        for card in sorted(bench, key=lambda c: (-c.tier, -c.stars, c.x)):
            rows = [row for row in ('front', 'back') if getattr(card, row)]
            if current < total:
                for row in rows:
                    if empty[row]:
                        return card, empty[row][0]
            # Unknown quality is not replaced, a misread one would be swapped back and forth
            lower = [other for other in board if other.row in rows and other.tier and other.value < card.value]
            if lower:
                return card, min(lower, key=lambda c: (c.value, c.equipped, c.x)).point
        return None

    def _wait_deploy_counter(self) -> tuple[int, int, int]:
        """
        Deploy counter is covered by toasts and level up animation for a while.

        Returns:
            current, remain, total. total is 0 if unreadable.
        """
        for _ in range(5):
            self.device.screenshot()
            counter = self._deploy_counter()
            if counter[2]:
                return counter
            # Covered by a reward or panel, let the run loop handle it
            if not self.is_prep_ready():
                return 0, 0, 0
            self.device.sleep(1)
        logger.warning('Deploy counter unreadable')
        return 0, 0, 0

    def _slot_patch(self, point):
        x, y = point
        return self.device.image[y - 30:y + 30, x - 25:x + 25].astype(int)

    def prep_deploy(self):
        """
        Deploy bench characters into empty slots, then replace lower quality ones on board.
        Characters already on board are skipped, the game refuses duplicates with a toast covering the counter.

        Pages:
            in: PREP_CHECK
            out: PREP_CHECK
        """
        logger.hr('Prep deploy', level=2)
        skipped = set()
        replaced = set()
        unreadable = 0
        for _ in range(20):
            self.device.screenshot()
            if not self.is_prep_ready():
                logger.info('Left prep page, stop deploying')
                break
            current, _, total = self._deploy_counter()
            if total == 0:
                # Counter covered by level up animation or a toast
                unreadable += 1
                if unreadable >= 5:
                    logger.warning('Deploy counter unreadable, stop deploying')
                    break
                self.device.sleep(1)
                continue
            unreadable = 0
            board = self._board_cards()
            bench = [card for card in self._deployable(self._bench_characters(), board) if card.x not in skipped]
            empty = {row: self._empty_slots(row) for row in ('front', 'back')}
            target = self._deploy_target(bench, board, empty, current, total)
            if target is None:
                logger.info(f'Deploy done, {current}/{total}')
                break
            card, point = target
            # Each slot is replaced once at most, a misread card would be swapped back and forth
            if point in replaced:
                logger.info(f'Slot {point} already replaced, deploy done')
                break
            if current >= total:
                replaced.add(point)
            logger.info(f'Deploy {card} -> {point}')
            before = self._slot_patch(point)
            self.device.drag(card.point, point, point_random=(0, 0, 0, 0), name=f'DEPLOY_{card.index}')
            self.device.sleep(0.8)
            self.device.screenshot()
            if abs(self._slot_patch(point) - before).mean() < SLOT_CHANGED:
                logger.info(f'Bench {card.index} not deployed')
                skipped.add(card.x)
        self.device.click_record_clear()

    @staticmethod
    def _shop_priority(card, copies: int, lowest, need: int, need_front: bool):
        """
        Returns:
            tuple | None: Sort key of a shop card, smaller is better. None if not worth buying.
                Copies of owned characters first, 3 copies merge into a higher star.
                Then characters to fill empty slots, then higher quality than the lowest deployed.
        """
        if copies:
            return 0, -copies, -card.tier
        if need > 0:
            return 1, need_front and not card.front, -card.tier
        if lowest is not None and (card.tier, 1) > lowest:
            return 2, -card.tier
        return None

    def prep_buy_characters(self, fill_only=False):
        """
        Buy copies of owned characters, characters to fill empty slots, and higher quality ones.
        Without this, the board can't recover after losing all characters,
        some investment strategies turn all characters into gold.

        Args:
            fill_only: Only buy characters to fill empty slots

        Pages:
            in: PREP_CHECK
            out: PREP_CHECK
        """
        current, _, total = self._wait_deploy_counter()
        # Shop button still matches PREP_CHECK under panels, but clicking it does nothing
        if total == 0 or not self.is_prep_ready():
            return
        board = self._board_cards()
        bench = self._bench_characters()
        deployable = self._deployable(bench, board)
        need = total - current - len(deployable)
        # The lowest value among the characters that will be deployed, worth replacing
        deployed = sorted(card.value for card in board + deployable)[-total:]
        lowest = deployed[0] if len(deployed) >= total else None
        if fill_only and need <= 0:
            return
        logger.hr('Prep buy characters', level=2)
        # FIGHT is blocked without any front character
        need_front = not any(card.row == 'front' for card in board) and not any(c.front for c in deployable)
        owned = board + bench
        extra = 0 if fill_only else SHOP_BUY_LIMIT

        opened = False
        for _ in self.loop(timeout=30):
            if self.appear(PREP_CHECK, interval=2):
                # Panels may pop up late, such as Black Swan's fortune teller
                if not self.is_prep_ready():
                    logger.info('Shop covered by a panel, stop buying')
                    break
                self.device.click(PREP_CHECK)
                continue
            if not self.appear(SHOP_OPEN):
                continue
            if not opened:
                # Cards slide in after the button switches to "收起"
                opened = True
                self.device.sleep(0.5)
                continue
            if len(self._bench_cards()) >= len(BENCH_X):
                logger.info('Bench full, stop buying')
                break
            gold = Digit(OCR_GOLD).ocr_single_line(self.device.image)
            candidates = []
            for card in self._shop_cards():
                if card.cost > gold:
                    continue
                # Only star up deployed characters, copies of bench ones would be sold soon
                copies = 0 if fill_only or not self._copies(card, board) else self._copies(card, owned)
                priority = self._shop_priority(card, copies, lowest, need, need_front)
                if priority is not None:
                    candidates.append((priority, card))
            if need <= 0 and extra <= 0:
                break
            if not candidates:
                break
            priority, card = min(candidates, key=lambda c: (c[0], c[1].index))
            if priority[0] > 1 and extra <= 0:
                break
            logger.info(f'Buy {card}, priority {priority}')
            self.device.click(card.button)
            if priority[0] == 1:
                need -= 1
                need_front = need_front and not card.front
            else:
                extra -= 1
            self.device.sleep(0.8)

        for _ in self.loop(timeout=10):
            if self.appear(PREP_CHECK):
                break
            if self.appear_then_click(SHOP_OPEN, interval=2):
                continue
        self.device.click_record_clear()

    def _orb_rows(self) -> list[int]:
        """
        Returns:
            Y of orbs on the board, orbs on the same row are merged
        """
        x1, y1, x2, y2 = ORB_AREA
        gray = cv2.cvtColor(self.device.image[y1:y2, x1:x2], cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 1.5)
        circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1, minDist=15,
                                   param1=80, param2=22, minRadius=11, maxRadius=26)
        if circles is None:
            return []
        rows = []
        for y in sorted(int(y1 + y) for _, y, _ in circles[0]):
            if not rows or y - rows[-1] > 12:
                rows.append(y)
        return rows

    def prep_collect_orbs(self):
        """
        Orbs on the right of the board give gold, characters, equipments.
        They are collected by slowly swiping over them, clicking or fast swipes don't work.
        Orbs can't be opened with a full bench, and their rewards may fill it, so sell and swipe again.

        Pages:
            in: PREP_CHECK
            out: PREP_CHECK, or INVEST_STRATEGY_CHECK if an orb gives an investment strategy
        """
        logger.hr('Prep collect orbs', level=2)
        for _ in range(3):
            self.device.screenshot()
            # Shop opens itself after some nodes, its cards would be swiped
            if not self.is_prep_ready():
                return
            rows = self._orb_rows()
            logger.attr('OrbRows', rows)
            if not rows:
                return
            if len(self._bench_cards()) >= len(BENCH_X):
                self.prep_sell_undeployable()
                self.device.screenshot()
                if len(self._bench_cards()) >= len(BENCH_X):
                    logger.info('Bench full, leave orbs')
                    return
            for y in rows:
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

    def prep_equip(self):
        """
        Drag every equipment onto board characters, highest value first, 3 at most for each.

        Pages:
            in: PREP_CHECK
            out: PREP_CHECK
        """
        self.device.screenshot()
        if not self._equipments():
            return
        logger.hr('Prep equip', level=2)
        # Some equipments only fit some characters. Try each one on a few characters, then leave it.
        # Items don't move while they stay, so they are tracked by position.
        tried = {}
        for _ in range(20):
            if not self.is_prep_ready():
                break
            cards = [card for card in sorted(self._board_cards(), key=lambda c: (c.value, -c.x), reverse=True)
                     if card.equipped < EQUIPPED_MAX]
            equipments = self._equipments()
            target = None
            for item in equipments:
                if len(tried.get(item, [])) >= EQUIP_TRIES:
                    continue
                for card in cards:
                    if card.point not in tried.get(item, []):
                        target = item, card
                        break
                if target:
                    break
            if target is None:
                break
            item, card = target
            logger.info(f'Equip {item} -> {card}')
            self.device.drag(item, card.point, point_random=(0, 0, 0, 0), name='EQUIP')
            self.device.sleep(1)
            self.device.screenshot()
            if len(self._equipments()) >= len(equipments):
                logger.info(f'Equipment not taken by {card}')
                tried.setdefault(item, []).append(card.point)
            else:
                tried.clear()
            # Each drag is verified above, they are not blind repeated clicks
            self.device.click_record_clear()
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

    def _sell_order(self, characters: list[Card], board: list[Card]) -> list[Card]:
        """
        Lowest value first, copies of board characters last as they merge into a higher star.
        Copies of bench characters are sold, more of them won't be bought.
        """
        def key(card):
            copy = any(self._same_character(card, other) for other in board)
            # Selling from the right, so positions of the remaining ones won't shift
            return copy, card.value, -card.x

        return sorted(characters, key=key)

    def prep_sell_undeployable(self):
        """
        Sell bench characters that can't be deployed, so bench won't block orbs and supplies.
        Selling is free and gives gold back.

        Pages:
            in: PREP_CHECK
            out: PREP_CHECK
        """
        self.device.screenshot()
        # Board is hidden under panels, copies on it can't be checked
        if not self.is_prep_ready():
            return
        characters = self._bench_characters()
        if len(characters) < BENCH_SELL_THRESHOLD:
            return
        logger.hr('Prep sell', level=2)
        sell = self._sell_order(characters, self._board_cards())[:BENCH_SELL_COUNT]
        for character in sorted(sell, key=lambda c: c.x, reverse=True):
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
        # Better characters on bench take their slots first, instead of being sold to make room for orbs
        self.prep_deploy()
        self.prep_collect_orbs()
        self.device.screenshot()
        if not self.is_prep_ready():
            logger.info('Prep interrupted')
            return False
        self.prep_open_boxes()
        self.prep_buy_characters()
        self.prep_deploy()
        self.prep_buy_exp()
        # Level up adds a slot, fill it
        self.prep_buy_characters(fill_only=True)
        self.prep_deploy()
        self.prep_equip()
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
