from module.base.button import ClickButton
from module.exception import RequestHumanTakeover
from module.logger import logger
from module.ocr.ocr import Ocr
from tasks.base.assets.assets_base_popup import POPUP_CONFIRM
from tasks.base.page import page_currency_wars
from tasks.currency_wars.assets.assets_currency_wars_run import *
from tasks.currency_wars.invest import CurrencyWarsInvest
from tasks.currency_wars.prep import CurrencyWarsPrep

# Cards and buttons that are not worth a template
FIGHT = ClickButton((1160, 462, 1230, 500), name='FIGHT')
SUPPLY_CONFIRM = ClickButton((1000, 642, 1180, 672), name='SUPPLY_CONFIRM')
# Panels that pop up after deploying some characters, such as wish trial, hack effects, star of the gala.
# They have 2 options and a "确认选择" button whose height varies, options are picked by select_panel_option().
# Red hint "请选择..." above the confirm button, its text is clearer than the dimmed button
SELECT_HINT_TO_CONFIRM = 46
# Expert invitation, 4 characters and a gold option, the picked character joins shop
EXPERT_OPTION = ClickButton((215, 150, 275, 210), name='EXPERT_OPTION')

# Every page inside a run, used to tell if a run is ongoing
RUN_CHECKS = [
    BOSS_PREVIEW_CHECK, CLICK_BLANK, INVEST_ENV_CHECK, INVEST_STRATEGY_CHECK, SUPPLY_CHECK,
    PREP_CHECK, SHOP_OPEN, UNDERFILLED_CHECK, NO_FRONT_CHECK, CHARACTER_DETAIL, BATTLE_CHECK,
    RESULT_CONTINUE, RESULT_SETTLE, SETTLE_NEXT_STEP, SETTLE_NEXT_PAGE, SETTLE_RETURN,
]


class CurrencyWarsRun(CurrencyWarsPrep, CurrencyWarsInvest):
    def is_in_run(self) -> bool:
        for button in RUN_CHECKS:
            if self.appear(button):
                return True
        return self.is_select_panel()

    def is_select_panel(self) -> bool:
        """
        OCR instead of template, the confirm button is dimmed before selecting and its height varies.
        """
        if self.appear(SELECT_CONFIRM):
            return True
        return self._select_hint() is not None

    def _select_hint(self):
        for result in Ocr(OCR_SELECT_CONFIRM).detect_and_ocr(self.device.image):
            if result.ocr_text.startswith('请选择'):
                return result
        return None

    def select_panel_confirm(self) -> ClickButton:
        if self.appear(SELECT_CONFIRM):
            return SELECT_CONFIRM
        hint = self._select_hint()
        if hint is None:
            return SELECT_CONFIRM
        x1, y1, x2, y2 = (int(v) for v in hint.box)
        y = (y1 + y2) // 2 + SELECT_HINT_TO_CONFIRM
        return ClickButton((x1, y - 10, x2, y + 10), name='SELECT_CONFIRM')

    def supply_card(self) -> ClickButton:
        """
        Supply has 3 to 5 cards centered on screen, locate them by the character name under each card.

        Returns:
            The leftmost card
        """
        names = Ocr(OCR_SUPPLY_NAME).detect_and_ocr(self.device.image)
        if not names:
            logger.warning('No supply card name found, click the middle')
            return ClickButton((600, 240, 680, 340), name='SUPPLY_CARD')
        x1, _, x2, _ = min((name.box for name in names), key=lambda box: box[0])
        x = (x1 + x2) // 2
        # Card portrait is above the name
        return ClickButton((x - 30, 240, x + 30, 340), name='SUPPLY_CARD')

    def fight(self):
        """
        Click FIGHT and wait until the board is gone, so the run loop won't prep again during battle loading.

        Pages:
            in: PREP_CHECK
            out: UNDERFILLED_CHECK, or battle loading
        """
        self.device.click(FIGHT)
        for _ in self.loop(skip_first=False, timeout=10):
            if self.appear(UNDERFILLED_CHECK):
                return
            if not self.appear(PREP_CHECK):
                return
        logger.warning('Board still there after clicking FIGHT')

    def run_once(self, skip_first_screenshot=True):
        """
        Play a run until settlement is finished.

        Pages:
            in: Any page inside a run
            out: page_currency_wars
        """
        logger.hr('Currency wars run', level=1)
        settled = False
        for _ in self.loop(skip_first=skip_first_screenshot):
            # End
            if settled and self.ui_page_appear(page_currency_wars):
                logger.info('Run finished')
                break

            # Popups
            # UNDERFILLED is a POPUP_CONFIRM as well, handle it before the generic one
            if self.appear(UNDERFILLED_CHECK):
                if self.interval_is_reached(UNDERFILLED_CHECK, interval=3):
                    logger.info('Deploy not full, skip reminder in this run')
                    self.device.click(UNDERFILLED_SKIP)
                    self.device.sleep(0.3)
                    self.device.click(UNDERFILLED_CONFIRM)
                    self.interval_reset(UNDERFILLED_CHECK, interval=3)
                continue
            # FIGHT with no front character, deploy again
            if self.appear(NO_FRONT_CHECK, interval=3):
                logger.warning('No front character, deploy again')
                self.device.click(NO_FRONT_CONFIRM)
                continue
            if self.appear(POPUP_CONFIRM):
                # Unknown confirm popup inside a run may cost something, never confirm blindly
                logger.critical('Unknown popup in currency wars run')
                self.device.image_save()
                raise RequestHumanTakeover

            # Settlement
            if self.appear_then_click(RESULT_SETTLE, interval=3):
                continue
            if self.appear_then_click(SETTLE_NEXT_STEP, interval=3):
                continue
            if self.appear_then_click(SETTLE_NEXT_PAGE, interval=3):
                continue
            if self.appear_then_click(SETTLE_RETURN, interval=3):
                settled = True
                continue

            # Node transitions
            if self.appear_then_click(RESULT_CONTINUE, interval=3):
                continue
            if self.appear(BOSS_PREVIEW_CHECK, interval=3):
                self.device.click(BOSS_PREVIEW_NEXT)
                continue
            if self.appear_then_click(CLICK_BLANK, interval=3):
                continue
            if self.appear(INVEST_STRATEGY_CHECK, interval=3):
                self.invest_strategy_pick()
                continue
            if self.appear(INVEST_ENV_CHECK, interval=3):
                self.invest_env_pick()
                continue
            if self.appear(SUPPLY_CHECK, interval=3):
                self.device.click(self.supply_card())
                self.device.sleep(0.5)
                self.device.click(SUPPLY_CONFIRM)
                continue

            # OCR costs ~0.4s, check at most every 3s, panels stay until selected.
            # Panels only pop up during preparation, the shop button underneath still matches PREP_CHECK
            if self.appear(PREP_CHECK) and self.interval_is_reached(SELECT_CONFIRM, interval=3):
                self.interval_reset(SELECT_CONFIRM, interval=3)
                if self.is_select_panel():
                    logger.info('Select panel, pick an option')
                    self.device.click(self.select_panel_option())
                    self.device.sleep(0.5)
                    self.device.screenshot()
                    self.device.click(self.select_panel_confirm())
                    continue

            if self.appear(EXPERT_CHECK, interval=3):
                self.device.click(EXPERT_OPTION)
                continue

            if self.handle_character_detail():
                continue

            # Equipment box left open, usually opened by prep_open_boxes()
            if self.appear(BOX_CHECK, interval=3):
                self.device.click(self.select_panel_option())
                continue

            # Prepare and fight
            if self.appear_then_click(SHOP_OPEN, interval=2):
                continue
            if self.appear(PREP_CHECK, interval=5):
                if self.prep_once():
                    self.fight()
                continue

            # Auto battle may last minutes
            if self.appear(BATTLE_CHECK):
                self.device.stuck_record_clear()
                continue


if __name__ == '__main__':
    self = CurrencyWarsRun('dev', task='CurrencyWars')
    self.device.screenshot()
    self.run_once()
