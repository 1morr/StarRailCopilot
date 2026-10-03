from dataclasses import dataclass

from module.base.button import ClickButton
from module.exception import RequestHumanTakeover
from module.logger import logger
from module.ocr.ocr import Digit, DigitCounter, Ocr
from tasks.base.page import page_currency_wars
from tasks.currency_wars.assets.assets_currency_wars_entry import *
from tasks.currency_wars.run import CurrencyWarsRun
from tasks.dungeon.keywords import KEYWORDS_DUNGEON_NAV, KEYWORDS_DUNGEON_TAB
from tasks.dungeon.ui.ui import DungeonUI

# Back arrow on upper-right of mode select and difficulty page
MODE_BACK = ClickButton((1212, 22, 1250, 56), name='MODE_BACK')


@dataclass
class CurrencyWarsStatus:
    score: int
    score_total: int
    weekly_extra: int
    weekly_extra_total: int
    promotion_level: int
    # Weekly extra points are no longer given
    promotion_max: bool = False

    @property
    def weekly_full(self) -> bool:
        extra_full = self.weekly_extra_total > 0 and self.weekly_extra >= self.weekly_extra_total
        return self.score_total > 0 and self.score >= self.score_total and (extra_full or self.promotion_max)


class CurrencyWarsEntry(CurrencyWarsRun, DungeonUI):
    def lobby_enter(self, skip_first_screenshot=True):
        """
        Pages:
            in: Any known page
            out: page_currency_wars
        """
        logger.hr('Currency wars enter', level=1)
        self.ui_get_current_page(skip_first_screenshot=skip_first_screenshot)
        if self.ui_current == page_currency_wars:
            logger.info('Already at currency wars lobby')
            return
        self.dungeon_tab_goto(KEYWORDS_DUNGEON_TAB.Simulated_Universe)
        self.dungeon_nav_goto(KEYWORDS_DUNGEON_NAV.Currency_Wars)

        for _ in self.loop():
            if self.ui_page_appear(page_currency_wars):
                break
            # Season announcements on first visit
            if self.appear_then_click(ANNOUNCE_CLOSE, interval=2):
                continue
            if self.appear_then_click(CLICK_BLANK_CLOSE, interval=2):
                continue
            if self.appear_then_click(GUIDE_PARTICIPATE, interval=3):
                continue

    def is_mode_select(self) -> bool:
        """
        Mode select page (either mode selected, or an unfinished run to continue) or difficulty page,
        all of them have MODE_BACK on the upper-right.
        """
        return (self.appear(ENTER_OVERCLOCK) or self.appear(ENTER_STANDARD)
                or self.appear(CONTINUE_PROGRESS) or self.appear(DIFFICULTY_START))

    def lobby_to_mode(self, skip_first_screenshot=True):
        """
        Pages:
            in: page_currency_wars, mode select
            out: mode select, overclock selected
        """
        for _ in self.loop(skip_first=skip_first_screenshot):
            if self.appear(ENTER_OVERCLOCK) or self.appear(CONTINUE_PROGRESS):
                break
            if self.appear(ENTER_STANDARD, interval=2):
                self.device.click(MODE_OVERCLOCK)
                continue
            if self.appear_then_click(page_currency_wars.check_button, interval=3):
                continue

    def mode_to_lobby(self, skip_first_screenshot=True):
        """
        Pages:
            in: mode select, difficulty
            out: page_currency_wars
        """
        for _ in self.loop(skip_first=skip_first_screenshot):
            if self.ui_page_appear(page_currency_wars):
                break
            if self.is_mode_select() and self.interval_is_reached(MODE_BACK, interval=2):
                self.device.click(MODE_BACK)
                self.interval_reset(MODE_BACK, interval=2)
                continue

    def get_status(self) -> CurrencyWarsStatus:
        """
        Pages:
            in: page_currency_wars
            out: mode select, overclock selected
        """
        logger.hr('Currency wars status', level=2)
        # Numbers count up when arriving at lobby after a run, wait until they are stable
        score_ocr, level_ocr = DigitCounter(OCR_LOBBY_SCORE), Digit(OCR_PROMOTION_LEVEL)
        previous = None
        for _ in self.loop(skip_first=False, timeout=10):
            current = (score_ocr.ocr_single_line(self.device.image), level_ocr.ocr_single_line(self.device.image))
            if current == previous:
                break
            previous = current
            self.device.sleep(1)
        else:
            logger.warning('Lobby numbers not stable')
        (score, _, score_total), level = previous
        self.lobby_to_mode()
        # Weekly extra points are replaced by "当前晋升等级已满级" once promotion level is maxed
        promotion_max = '满级' in Ocr(OCR_WEEKLY_EXTRA).ocr_single_line(self.device.image)
        if promotion_max:
            extra, extra_total = 0, 0
        else:
            extra, _, extra_total = DigitCounter(OCR_WEEKLY_EXTRA).ocr_single_line(self.device.image)
        status = CurrencyWarsStatus(
            score=score, score_total=score_total,
            weekly_extra=extra, weekly_extra_total=extra_total,
            promotion_level=level, promotion_max=promotion_max,
        )
        logger.attr('CurrencyWarsStatus', status)
        return status

    def run_start(self, skip_first_screenshot=True):
        """
        Pages:
            in: mode select, overclock selected
            out: Any page inside a run
        """
        logger.hr('Currency wars start', level=2)
        for _ in self.loop(skip_first=skip_first_screenshot):
            if self.is_in_run():
                break
            # An unfinished run, from disconnection or game restart. Never click "结束并结算" next to it
            if self.appear_then_click(CONTINUE_PROGRESS, interval=3):
                continue
            if self.appear(DIFFICULTY_START, interval=3):
                # Only the default lowest difficulty is allowed
                difficulty = Digit(OCR_DIFFICULTY).ocr_single_line(self.device.image)
                if difficulty != 1:
                    logger.critical(f'Enemy difficulty is {difficulty}, expected 1')
                    raise RequestHumanTakeover
                self.device.click(DIFFICULTY_START)
                continue
            if self.appear_then_click(ENTER_OVERCLOCK, interval=3):
                continue
            if self.appear(ENTER_STANDARD, interval=2):
                self.device.click(MODE_OVERCLOCK)
                continue


if __name__ == '__main__':
    self = CurrencyWarsEntry('dev', task='CurrencyWars')
    self.device.screenshot()
    self.lobby_enter()
    print(self.get_status())
