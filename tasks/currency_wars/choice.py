from module.base.button import ClickButton
from module.exception import RequestHumanTakeover
from module.logger import logger
from module.ocr.ocr import Ocr, OcrResultButton
from tasks.base.ui import UI

# Choice panels pop up during preparation: equipment boxes, hiring books, expert invitation,
# and talents of some characters (wish trial, hack effects, star of the gala, ...).
# They vary in layout, but all of them have a "请选择..." hint and option cards with text inside.
CHOICE_PANEL = ClickButton((0, 0, 1280, 720), name='CHOICE_PANEL')
CHOICE_HINT = '请选择'
# Option texts are inside this area, the left column of synergies and the board below are excluded
CHOICE_OPTION_AREA = (130, 90, 1280, 420)
# Texts that are not options: buttons, tags, toasts, board labels
CHOICE_NOT_OPTION = ['详情', '试用', '解锁', '收起', '出战', '确认', '未选择', '区域', '备战席', '等级']
# Panels with a confirm button have a red hint on the right, the button is under it
CHOICE_HINT_RIGHT = 900
CHOICE_HINT_TO_CONFIRM = 46
# Never click anything on a panel mentioning these, it costs something or ends the run
CHOICE_DANGER = ['星琼', '开拓力', '购买', '结束并结算', '放弃', '退出']


class CurrencyWarsChoice(UI):
    def _choice_ocr(self) -> list[OcrResultButton]:
        return Ocr(CHOICE_PANEL).detect_and_ocr(self.device.image)

    @staticmethod
    def _choice_hint(results) -> OcrResultButton | None:
        for result in results:
            if CHOICE_HINT in result.ocr_text:
                return result
        return None

    def is_choice_panel(self) -> bool:
        return self._choice_hint(self._choice_ocr()) is not None

    @staticmethod
    def _in_option_area(result) -> bool:
        x1, y1, x2, y2 = CHOICE_OPTION_AREA
        return x1 <= result.box[0] and result.box[2] <= x2 and y1 <= result.box[1] and result.box[3] <= y2

    @staticmethod
    def _choice_option(results) -> ClickButton | None:
        """
        Returns:
            The leftmost option. Any text inside an option card selects it.
        """
        options = [
            result for result in results
            if CurrencyWarsChoice._in_option_area(result)
            and CHOICE_HINT not in result.ocr_text
            and not any(word in result.ocr_text for word in CHOICE_NOT_OPTION)
        ]
        if not options:
            return None
        option = min(options, key=lambda result: result.box[0])
        return ClickButton(tuple(int(v) for v in option.box), name='CHOICE_OPTION')

    @staticmethod
    def _choice_confirm(results) -> ClickButton | None:
        """
        Returns:
            Confirm button, or None if the panel closes once an option is selected.
        """
        for result in results:
            if result.ocr_text.startswith('确认'):
                return ClickButton(tuple(int(v) for v in result.box), name='CHOICE_CONFIRM')
        # Confirm button is dimmed before selecting, its text may be unreadable
        for hint in results:
            if CHOICE_HINT in hint.ocr_text and hint.box[0] > CHOICE_HINT_RIGHT:
                x1, y1, x2, y2 = (int(v) for v in hint.box)
                y = (y1 + y2) // 2 + CHOICE_HINT_TO_CONFIRM
                return ClickButton((x1, y - 10, x2, y + 10), name='CHOICE_CONFIRM')
        return None

    def handle_choice_panel(self) -> bool:
        """
        Pick the leftmost option of any choice panel, then confirm if needed.

        Returns:
            bool: If handled

        Raises:
            RequestHumanTakeover: If the panel mentions any cost
        """
        results = self._choice_ocr()
        hint = self._choice_hint(results)
        if hint is None:
            return False
        logger.info(f'Choice panel: {hint.ocr_text}')
        # Board under the panel has "购买经验", only check the panel
        for result in results:
            if self._in_option_area(result) and any(word in result.ocr_text for word in CHOICE_DANGER):
                logger.critical(f'Choice panel mentions "{result.ocr_text}", it may cost something')
                self.device.image_save()
                raise RequestHumanTakeover

        option = self._choice_option(results)
        if option is None:
            logger.warning('No option found on choice panel')
            return False
        self.device.click(option)
        self.device.sleep(0.5)
        self.device.screenshot()
        results = self._choice_ocr()
        if self._choice_hint(results) is None:
            # Closed once selected, such as equipment boxes
            return True
        confirm = self._choice_confirm(results)
        if confirm is not None:
            self.device.click(confirm)
        return True


if __name__ == '__main__':
    self = CurrencyWarsChoice('dev', task='CurrencyWars')
    self.device.screenshot()
    self.handle_choice_panel()
