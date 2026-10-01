import cv2

from module.base.button import ClickButton
from module.base.utils import crop
from module.logger import logger
from tasks.base.ui import UI
from tasks.currency_wars.assets.assets_currency_wars_run import *

# Card center x, the "unrecorded" book icon sits on card top-right
ENV_CARDS_X = [255, 640, 1023]
STRATEGY_CARDS_X = [270, 640, 1012]
ICON_SEARCH_Y = (110, 180)
ICON_SEARCH_HALF_WIDTH = 180
ICON_SIMILARITY = 0.8

ENV_REFRESH = ClickButton((382, 640, 418, 676), name='INVEST_ENV_REFRESH')
ENV_CONFIRM = ClickButton((700, 645, 780, 672), name='INVEST_ENV_CONFIRM')
STRATEGY_CONFIRM = ClickButton((600, 645, 680, 672), name='INVEST_STRATEGY_CONFIRM')


def strategy_refresh(x):
    return ClickButton((x - 78, 576, x - 52, 604), name='INVEST_STRATEGY_REFRESH')


def card(x):
    return ClickButton((x - 80, 200, x + 80, 420), name='INVEST_CARD')


class CurrencyWarsInvest(UI):
    def _unrecorded_cards(self, cards_x) -> list[int]:
        """
        Returns:
            Center x of cards having the "unrecorded" book icon.
            Picking them unlocks collection entries, which give rewards outside runs.
        """
        template = INVEST_UNUSED.buttons[0].image
        found = []
        for x in cards_x:
            area = (x - ICON_SEARCH_HALF_WIDTH, ICON_SEARCH_Y[0], x + ICON_SEARCH_HALF_WIDTH, ICON_SEARCH_Y[1])
            res = cv2.matchTemplate(crop(self.device.image, area, copy=False), template, cv2.TM_CCOEFF_NORMED)
            _, sim, _, _ = cv2.minMaxLoc(res)
            if sim > ICON_SIMILARITY:
                found.append(x)
        logger.attr('UnrecordedCards', found)
        return found

    def _invest_pick(self, cards_x, refreshes, confirm, check):
        """
        Pick an unrecorded card, use refreshes to look for one, otherwise pick the middle card.

        Args:
            cards_x: Center x of cards
            refreshes (list[ClickButton]): Free refreshes to try in order
            confirm: Confirm button
            check: Page check button
        """
        refreshes = list(refreshes)
        target = cards_x[1]
        while 1:
            self.device.screenshot()
            if not self.appear(check):
                return
            unrecorded = self._unrecorded_cards(cards_x)
            if unrecorded:
                target = unrecorded[0]
                break
            if not refreshes:
                break
            button = refreshes.pop(0)
            logger.info(f'No unrecorded card, {button}')
            self.device.click(button)
            self.device.sleep(1.5)

        logger.info(f'Invest pick card at x={target}')
        self.device.click(card(target))
        self.device.sleep(0.5)
        self.device.click(confirm)

    def invest_env_pick(self):
        """
        Investment environment, refreshes all cards at once, 1 time.

        Pages:
            in: INVEST_ENV_CHECK
        """
        logger.hr('Invest environment', level=2)
        self._invest_pick(ENV_CARDS_X, [ENV_REFRESH], confirm=ENV_CONFIRM, check=INVEST_ENV_CHECK)

    def invest_strategy_pick(self):
        """
        Investment strategy, each card has its own refresh, 1 time each.

        Pages:
            in: INVEST_STRATEGY_CHECK
        """
        logger.hr('Invest strategy', level=2)
        self._invest_pick(STRATEGY_CARDS_X, [strategy_refresh(x) for x in STRATEGY_CARDS_X],
                          confirm=STRATEGY_CONFIRM, check=INVEST_STRATEGY_CHECK)
