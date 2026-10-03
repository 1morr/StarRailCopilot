from dataclasses import dataclass, field

import cv2
import numpy as np

from module.base.button import ClickButton
from module.ocr.ocr import DigitCounter
from tasks.currency_wars.assets.assets_currency_wars_run import OCR_DEPLOY
from tasks.currency_wars.choice import CurrencyWarsChoice

# Board geometry at 1280x720, slots don't move between runs
BENCH_X = [205 + 104 * i for i in range(9)]
BENCH_Y = 595
FRONT_X = [488, 590, 690, 792]
FRONT_Y = 258
# Back row has 6 or 7 slots. Not decided by deploy limit, both are seen at limit 10.
BACK_X_6 = [389, 489, 590, 690, 790, 890]
BACK_X_7 = [336, 440, 540, 640, 740, 840, 940]
BACK_Y = 448
# Left edge of the first slot in 7-slot layout, it's plain floor in 6-slot layout (edge ~1, slot edge ~20+)
BACK_7_EDGE_X = 290
BACK_7_EDGE = 8
# Std of slot center, empty slot ~35, character card ~60+
SLOT_OCCUPIED_STD = 47
# "0/3" is ~70px wide, the shortest counter
DEPLOY_TEXT_MIN_WIDTH = 40
# Shop has 5 character cards, opened by clicking PREP_CHECK ("商店") and closed by SHOP_OPEN ("收起")
SHOP_CARDS_LEFT = [147 + 224 * i for i in range(5)]

# Quality is the color of the stripe at card bottom, same colors on bench and board.
# Shop cost equals quality, its odds are listed as grey/green/blue/purple/gold.
TIER_COLORS = {
    1: (130, 131, 145),
    2: (55, 112, 105),
    3: (90, 112, 222),
    4: (144, 110, 243),
    5: (203, 168, 95),
}
TIER_MAX_DISTANCE = 70
# Stripe rows, board cards are drawn with perspective so their stripe height varies a little
STRIPE_Y = {'bench': (638, 650), 'front': (294, 305), 'back': (486, 497)}
# Rows of star icons above the stripe, 1 to 3 stars side by side
STARS_Y = {'bench': (615, 645), 'front': (270, 302), 'back': (468, 494)}
# Portrait core of a bench card, below position marker and above star and stripe
PORTRAIT_Y = (565, 620)
PORTRAIT_HALF_WIDTH = 28
# The same core on a shop card, 1.4x larger
SHOP_PORTRAIT_Y = (74, 151)
SHOP_PORTRAIT_X = (71, 149)
# Equipment grid on the right, filled from the upper-right and expands to the left
EQUIPMENT_X = [1218 - 66 * i for i in range(5)]
EQUIPMENT_Y = [189, 253, 317, 380]
# Equipped items are shown under board cards, ~29px each, at most 3
EQUIPPED_Y = {'front': (306, 330), 'back': (497, 522)}
EQUIPPED_WIDTH = 29
EQUIPPED_MAX = 3
# Board cards are slightly smaller than bench cards
PORTRAIT_SCALES = {'bench': [1.0], 'front': [0.88, 0.94, 1.0], 'back': [0.88, 0.94, 1.0]}
# Same character ~0.85+, different characters ~0.5-
PORTRAIT_SIMILARITY = 0.7


@dataclass
class Card:
    row: str
    x: int
    tier: int
    stars: int = 1
    # Where it can stand, from position marker. Equipment boxes have neither.
    front: bool = True
    back: bool = True
    # Equipments under a board card
    equipped: int = 0

    @property
    def value(self):
        # Quality first, a 1-star green beats a 2-star grey since it will be starred up later
        return self.tier, self.stars

    @property
    def y(self):
        return {'bench': BENCH_Y, 'front': FRONT_Y, 'back': BACK_Y}[self.row]

    @property
    def point(self):
        return self.x, self.y

    @property
    def index(self):
        return BENCH_X.index(self.x) if self.row == 'bench' else None

    @property
    def area(self):
        return {
            'bench': (self.x - 45, 545, self.x + 45, 650),
            'front': (self.x - 50, 205, self.x + 50, 310),
            'back': (self.x - 50, 395, self.x + 50, 500),
        }[self.row]


@dataclass
class ShopCard:
    index: int
    tier: int
    front: bool
    back: bool
    # Portrait core scaled to bench size, to find owned copies
    portrait: np.ndarray = field(default=None, repr=False, compare=False)

    @property
    def cost(self):
        # Shop cards are 1-star, their cost equals quality
        return self.tier

    @property
    def button(self):
        x = SHOP_CARDS_LEFT[self.index] + 100
        return ClickButton((x - 30, 100, x + 30, 160), name=f'SHOP_CARD_{self.index}')


def tier_of(color) -> int:
    """
    Returns:
        1 grey to 5 gold, 0 if unknown
    """
    distances = {tier: np.linalg.norm(np.subtract(color, ref)) for tier, ref in TIER_COLORS.items()}
    tier = min(distances, key=distances.get)
    return tier if distances[tier] < TIER_MAX_DISTANCE else 0


class CurrencyWarsBoard(CurrencyWarsChoice):
    def _slot_occupied(self, x, y) -> bool:
        patch = self.device.image[y - 30:y + 30, x - 25:x + 25]
        return patch.std() > SLOT_OCCUPIED_STD

    def _card_tier(self, row, x) -> int:
        y1, y2 = STRIPE_Y[row]
        rows = self.device.image[y1:y2, x - 25:x + 25].astype(int).mean(axis=1)
        # Stripe is the brightest row
        return tier_of(rows[rows.sum(axis=1).argmax()])

    def _card_stars(self, row, x) -> int:
        """
        Star icons are 4-pointed sparkles, the brightest thing at card bottom.
        Count their vertical arms on the rows 3px above and below their center.
        """
        y1, y2 = STARS_Y[row]
        area = self.device.image[y1:y2, x - 25:x + 25].astype(int)
        value = (area[..., 0] + area[..., 1]) // 2
        bright = value > max(value.max() - 40, 150)
        cy = bright.sum(axis=1).argmax()
        if cy < 4 or cy + 4 >= len(value):
            return 1
        columns = np.flatnonzero(bright[cy - 3] & bright[cy + 3])
        if not columns.size:
            return 1
        stars = 0
        for group in np.split(columns, np.flatnonzero(np.diff(columns) > 4) + 1):
            c = int(group.mean())
            # Horizontal arms on center row, but not on the rows of vertical arms
            if 4 <= c < 46 and bright[cy, c - 4] and bright[cy, c + 4] \
                    and not bright[cy - 3, c - 4] and not bright[cy + 3, c + 4]:
                stars += 1
        return min(max(stars, 1), 3)

    def _bench_cards(self) -> list[Card]:
        """
        Characters and equipment boxes on bench.
        Position marker on card top-right: upper square lit = can stand front, lower square lit = can stand back.
        Equipment box has no position marker, so it's front=False and back=False.
        """
        image = self.device.image
        cards = []
        for x in BENCH_X:
            if image[548:645, x - 42:x + 42].std() < 30:
                continue
            top = np.mean(image[553:560, x + 29:x + 36])
            bottom = np.mean(image[562:569, x + 29:x + 36])
            cards.append(Card('bench', x, self._card_tier('bench', x), self._card_stars('bench', x),
                              front=top > 200, back=bottom > 200))
        return cards

    def _bench_characters(self) -> list[Card]:
        return [card for card in self._bench_cards() if card.front or card.back]

    def _bench_boxes(self) -> list[int]:
        return [card.index for card in self._bench_cards() if not card.front and not card.back]

    def _back_x(self) -> list[int]:
        band = self.device.image[BACK_Y - 38:BACK_Y + 42].astype(int)
        x = BACK_7_EDGE_X
        edge = np.abs(band[:, x - 4:x + 5] - band[:, x - 6:x + 3]).mean(axis=(0, 2)).max()
        return BACK_X_7 if edge > BACK_7_EDGE else BACK_X_6

    def _board_cards(self) -> list[Card]:
        cards = []
        for row, xs, y in [('front', FRONT_X, FRONT_Y), ('back', self._back_x(), BACK_Y)]:
            for x in xs:
                if self._slot_occupied(x, y):
                    cards.append(Card(row, x, self._card_tier(row, x), self._card_stars(row, x),
                                      front=row == 'front', back=row == 'back', equipped=self._equipped(row, x)))
        return cards

    def _empty_slots(self, row: str) -> list[tuple[int, int]]:
        if row == 'front':
            xs, y = FRONT_X, FRONT_Y
        else:
            xs, y = self._back_x(), BACK_Y
        return [(x, y) for x in xs if not self._slot_occupied(x, y)]

    def _bench_portrait(self, card: Card):
        y1, y2 = PORTRAIT_Y
        return self.device.image[y1:y2, card.x - PORTRAIT_HALF_WIDTH:card.x + PORTRAIT_HALF_WIDTH]

    def _portrait_in(self, portrait, other: Card) -> bool:
        x1, y1, x2, y2 = other.area
        search = self.device.image[y1:y2, x1:x2]
        for scale in PORTRAIT_SCALES[other.row]:
            template = cv2.resize(portrait, None, fx=scale, fy=scale)
            similarity = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED).max()
            if similarity > PORTRAIT_SIMILARITY:
                return True
        return False

    def _same_character(self, bench: Card, other: Card) -> bool:
        """
        Characters with the same name can't be deployed together, but merge into a higher star at 3 copies.
        """
        return self._portrait_in(self._bench_portrait(bench), other)

    def _copies(self, card: ShopCard, owned: list[Card]) -> int:
        """
        Returns:
            How many copies of a shop card are owned, on board or bench
        """
        return sum(self._portrait_in(card.portrait, other) for other in owned)

    def _deployable(self, bench: list[Card], board: list[Card]) -> list[Card]:
        """
        Bench characters that can be deployed, excluding ones already on board and duplicates on bench.
        """
        deployable = []
        for card in bench:
            if any(self._same_character(card, other) for other in board + deployable):
                continue
            deployable.append(card)
        return deployable

    def _shop_cards(self) -> list[ShopCard]:
        """
        Cards remaining in shop, bought ones become empty slots.
        Position marker is the same as bench cards.
        Quality is the color of the name bar, OCR of the cost digit reads "1" as "一".
        """
        image = self.device.image
        cards = []
        for index, left in enumerate(SHOP_CARDS_LEFT):
            tier = tier_of(image[244:250, left + 110:left + 150].reshape(-1, 3).mean(axis=0))
            if not tier:
                continue
            top = np.mean(image[47:54, left + 176:left + 182])
            bottom = np.mean(image[62:69, left + 176:left + 182])
            y1, y2 = SHOP_PORTRAIT_Y
            x1, x2 = SHOP_PORTRAIT_X
            size = (PORTRAIT_HALF_WIDTH * 2, PORTRAIT_Y[1] - PORTRAIT_Y[0])
            portrait = cv2.resize(image[y1:y2, left + x1:left + x2], size)
            cards.append(ShopCard(index=index, tier=tier, front=top > 200, back=bottom > 200, portrait=portrait))
        return cards

    @staticmethod
    def _not_floor(area):
        """
        Board floor is bright blue, items have dark or colorful backgrounds.
        """
        area = area.astype(int)
        return area[..., 2] - (area[..., 0] + area[..., 1]) / 2 < 60

    def _equipments(self) -> list[tuple[int, int]]:
        """
        Grid is filled column by column from the upper-right, so it ends at the first empty cell.
        Golden orbs on the board are not equipments, they are never right after a filled cell.
        """
        image = self.device.image
        equipments = []
        for x in EQUIPMENT_X:
            for y in EQUIPMENT_Y:
                if self._not_floor(image[y - 22:y + 22, x - 22:x + 22]).mean() <= 0.75:
                    return equipments
                equipments.append((x, y))
        return equipments

    def _equipped(self, row, x) -> int:
        y1, y2 = EQUIPPED_Y[row]
        columns = np.flatnonzero(self._not_floor(self.device.image[y1:y2, x - 48:x + 48]).mean(axis=0) > 0.4)
        if not columns.size:
            return 0
        count = 0
        for group in np.split(columns, np.flatnonzero(np.diff(columns) > 2) + 1):
            if len(group) >= 10:
                # Adjacent icons may touch each other
                count += max(1, round(len(group) / EQUIPPED_WIDTH))
        return min(count, EQUIPPED_MAX)

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
        # Something else at the right edge, not the counter. OCR crashes on an empty crop.
        if x2 - text_x1 < DEPLOY_TEXT_MIN_WIDTH:
            return 0, 0, 0
        return DigitCounter(ClickButton((text_x1, y1, x2, y2), name='OCR_DEPLOY')).ocr_single_line(self.device.image)
