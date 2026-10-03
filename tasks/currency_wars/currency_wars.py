from module.logger import logger
from tasks.base.page import page_currency_wars, page_main
from tasks.currency_wars.assets.assets_currency_wars_entry import CONTINUE_PROGRESS
from tasks.currency_wars.entry import CurrencyWarsEntry, CurrencyWarsStatus


class CurrencyWars(CurrencyWarsEntry):
    def should_stop(self, status: CurrencyWarsStatus, runs: int) -> bool:
        """
        Weekly capped rewards (score and extra promotion points) always come first.
        After that, keep farming promotion points until run count or target level is reached.
        """
        if not status.weekly_full:
            logger.info('Weekly rewards not full, continue')
            return False
        if runs >= self.config.CurrencyWars_MaxRunsPerTask:
            logger.info(f'Reached max runs per task: {runs}')
            return True
        target = self.config.CurrencyWars_TargetPromotionLevel
        if target and status.promotion_level >= target:
            logger.info(f'Reached target promotion level: {status.promotion_level}')
            return True
        return False

    def resume(self) -> bool:
        """
        Continue from wherever the game is.

        Returns:
            bool: True if an ongoing run was finished

        Pages:
            in: Any
            out: page_currency_wars
        """
        # Battle animations darken the screen for a few seconds, wait before treating it as outside a run
        for _ in self.loop(skip_first=False, timeout=10):
            if self.is_in_run():
                logger.info('Run ongoing, continue it')
                self.run_once()
                return True
            if self.is_mode_select():
                logger.info('At mode select, back to lobby')
                self.mode_to_lobby()
                return False
            if self.ui_page_appear(page_currency_wars) or self.ui_page_appear(page_main):
                break
        self.lobby_enter()
        return False

    def run(self):
        runs = 1 if self.resume() else 0
        while 1:
            status = self.get_status()
            if self.appear(CONTINUE_PROGRESS):
                # Always finish an unfinished run, leaving it may lose rewards
                logger.info('Unfinished run found, continue it')
            elif self.should_stop(status, runs):
                break
            self.run_start()
            self.run_once()
            runs += 1
            logger.attr('CurrencyWarsRuns', runs)
            if self.config.task_switched():
                logger.info('Task switched, pause currency wars')
                self.config.task_stop()

        self.mode_to_lobby()
        self.ui_ensure(page_main)
        self.config.task_delay(server_update=True)


if __name__ == '__main__':
    self = CurrencyWars('dev', task='CurrencyWars')
    self.device.screenshot()
    self.run()
