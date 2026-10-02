---
name: src-emulator-dev
description: 用模擬器開發與除錯 SRC 功能的實測手冊 —— 連線、截圖、點擊滑動、裁素材產生按鈕、驗證模板比對與 OCR、單獨跑任務邏輯、讀 log 與錯誤截圖、導航回指定頁面。開發或除錯任何需要碰模擬器的 SRC 功能時載入。
---

# 用模擬器開發 SRC

所有操作都走 repo 自己的 device / Button / Ocr / UI 層；`scripts/emu.py` 只是把它們包成一次性指令。

## 開工前檢查（每個 session 一次）

1. **確認沒有別的 SRC 在操作同一台模擬器。** 使用者平時用的攜帶版 SRC 連的是同一台 MuMu。
   ```powershell
   Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ? CommandLine -match 'Portable\\StarRailCopilot' | select ProcessId,CommandLine
   Get-Content D:\Apps\Portable\StarRailCopilot\log\<今天>_src.txt -Tail 20
   ```
   只剩 `gui.py` 與 multiprocessing 子程序、log 停在 `Wait until ...` 表示排程器在等待，還沒碰模擬器。**要注意它等到的時間點**：`WhenTaskQueueEmpty=close_emulator` 會在那一刻自己開模擬器跑任務。如果它正在操作或即將操作，就停下來告訴使用者。攜帶版的設定與檔案一律不改。
2. 環境：`.venv`（Python 3.10）＋ `config/dev.json`（gitignored）。缺少時照「環境重建」補。

## 指令

從 repo 根目錄執行（Bash）：

```bash
E=".venv/Scripts/python.exe .claude/skills/src-emulator-dev/scripts/emu.py"
$E shot NAME                 # -> screenshots/NAME.png（gitignored），再用 Read 工具親眼看圖
$E page [--image F]          # tasks/base/page.py 的哪些 page 目前匹配
$E goto page_main            # ui_ensure，任意已知頁面 -> 目標頁面
$E click X Y | click ASSET   # ASSET 點的是它的 button 區，先比對以載入偏移
$E swipe X1 Y1 X2 Y2 [秒]
$E drag X1 Y1 X2 Y2          # 按住-移動-放開，拖放用（device.drag）
$E match ASSET [--image F]   # 每個語言變體的 template / luma 相似度、平均色
$E ocr ASSET|X1,Y1,X2,Y2 [--image F] [--digit|--counter]
$E asset assets/<share|cn>/<模組>/<子目錄>/<NAME>.png X1 Y1 X2 Y2 [--image F]
```

- 預設只印 WARNING 以上的 log，加 `-v` 看完整 log（`goto` 一律完整）。
- 輸出夾雜 `product: ...`、`nemu_connect ...`、`connect not same day`，這是 MuMu 的 DLL 直接寫到 stdout 的，忽略即可。
- 座標一律用 1280x720。拿到任務流程截圖或別的解析度的參考圖時，要在模擬器上重截，不要直接換算座標。
- 每個指令都會重新連線（約 3–5 秒）。探索時把同一個畫面上的多個動作串在同一個 Bash 呼叫裡，中間用 `sleep` 等動畫，最後才 `shot`。
- 拖放要用 `drag`；`swipe` 對拖放無效。「划過去收集」這類互動要慢速 swipe（0.8 秒有效，0.3 秒不會觸發）。
- 點擊沒反應時先截圖確認畫面是不是還在播動畫或過場，不要連點。同一個按鈕連點很容易觸發 `GameTooManyClickError`。

## 素材 → 按鈕定義

1. 用 `shot` 截圖，找出目標區域；`asset ... --image screenshots/X.png` 會產生 1280x720、區域外全黑的 PNG。
   - `button_extract` 用非黑像素的 bbox 當 `area`，目標區域的邊緣若本身是純黑，產出的 area 會縮小，要檢查生成值。
   - 文字會隨語言變的素材放 `assets/cn/`，圖示放 `assets/share/`。只有 cn 版本時，生成碼會出現 `en=None`，這是正常的。
2. `.venv/Scripts/python.exe -m dev_tools.button_extract`（約 20 秒，重新生成全部 `tasks/*/assets/*.py`）。
3. 如果新素材是給 `tasks/base/page.py` 的頁面 check button，要放進 `assets/<lang>/base/page/`，它就會生成到 `assets_base_page.py`。
4. **跑完先看 `git status`**：上游的 `tasks/item/assets/assets_item_gacha.py` 和它的素材不一致，每次都會被改寫，要 `git checkout --` 還原。只保留自己模組的 diff。
5. 驗證：在正確的畫面 `match` 要 > 0.85，另外至少找一張**相近但錯誤**的畫面 `match --image`，確認分數夠低（實測無關畫面約 0.1）。只測正例的素材不算驗證過。

## 從既有截圖批次產素材

探索時截下來的每個畫面都是素材來源。先對整張圖跑一次全畫面 OCR，就能拿到每段文字的精確 box，不必手量座標：

```python
# 建一個覆蓋全畫面的 ButtonWrapper，再呼叫 Ocr(...).detect_and_ocr(image)，逐筆印出 r.box 與 r.ocr_text
```

接著用 OpenCV 依 box 批次寫出黑底素材 PNG，順手拼一張 montage 用 Read 一次檢查全部裁切。小心這些地方：

- `DigitCounter` 的框要留出最大位數，`0/3000` 和 `3000/3000` 寬度不同，框太窄時會把 `3000` 截成 `300`。
- 會被半透明面板蓋住一半的畫面（例如盤面上方的彈出面板），底下的按鈕仍會匹配成功。辨識面板的條件要排在辨識底層畫面的條件之前。
- 判斷格子是否為空用區域標準差就夠了（空格約 35，有卡片 60 以上），不需要做模板。
- 樣式各異、會不斷新增的彈出面板（角色天賦二選一、裝備箱、聘用書、專家邀請函），不要逐個做模板：先找它們共有的文字結構寫成一條 OCR 規則（貨幣戰爭是「请选择」提示＋選項卡內的文字，見 `tasks/currency_wars/choice.py`），再把每種面板的截圖放進同一個參數化測試。遇到新面板時，先把截圖加進測試清單看規則是否已涵蓋，不通過才改規則。逐個做模板時，置中的副標題還會隨標題長度移動、超出 ±20px 搜尋範圍，而且永遠追不完。
- 置中顯示、左邊帶圖示的計數器（如上場人數 `0/4`、`10/11`），圖示會隨位數移動。固定 OCR 框不管左邊界放哪裡，總有一種位數會被切字或把圖示讀成「1」。要先用欄位投影找到圖示（第一段與背景色差大的欄），再 OCR 圖示右邊。
- 新放進格子的卡片在飛入動畫期間沒有前/後台標記，看起來像箱子。同一流程裡點過的格子要記下來，不要再點，否則會打開角色詳情。
- 數字在畫面切換後會有跳動動畫（大廳積分、等級、金幣）。讀數要等連續兩次相同才採用，不然可能會讀到動畫中途的值，例如把 18000 讀成 8000。

## 用測試守住辨識器

- 素材和辨識邏輯的回歸測試放在 `tasks/<模組>/test_*.py`，fixture 截圖用 JPEG 品質 75 存在 `tasks/<模組>/test_data/`（實測模板分數不受影響，15 張約 1.8 MB）。每個 check 素材都要至少一組正例和一組相近畫面的反例。
- 辨識函式只讀 `self.device.image` 時，用 `cls.__new__(cls)` 建實例，塞一個 `SimpleNamespace(image=..., stuck_record_add=lambda b: None)` 當 device，再加上 `interval_timer = {}`，就能在不連模擬器的情況下測。
- 控制流程（連點次數、何時停）要測時，寫一個 FakeDevice：`click()` 記錄按鈕名，並呼叫真正的 `Device.click_record_check(self)`；其餘 `screenshot/sleep/stuck_record_add` 都是 no-op。OCR 讀數用 monkeypatch 換成固定序列。這樣不用模擬器也能重現 `GameTooManyClickError`。
- pytest 不在 requirements 裡。裝進 venv 時要指定 `pytest<8.4`，並保留 `packaging==20.9`（新版 pytest 會把 packaging 升級，弄壞 uiautomator2）。`pip check` 必須沒有錯誤。
- 新規則照使用者的要求做雙向驗證：故意改壞閾值或條件，確認測試會失敗；還原後確認全部通過。**一次只改壞一處**：同時改兩處時，第一處可能讓程式走進 fallback，剛好遮住第二處，結果看起來測試沒守住，或是誤以為有守住。
- 畫面整體變暗、右下角延遲顯示 999ms，代表網路卡頓或斷線。這時按鈕模板會對不上，OCR 也容易讀錯小字，接著遊戲可能把角色踢回大世界。要排查「卡住」時，先看截圖右下角的延遲數字，不要直接懷疑素材壞了。
- 暗化畫面上讀 OCR，選字大、對比高的那一行（例如紅底白字的提示條）當辨識依據，比選字小、本身也變暗的按鈕文字可靠。

## OCR

- 整行 UI 文字很可靠（`生存索引` 分數 0.96）；10px 左右的小字會漏字或多字（`星际和平指南` 會被讀成 `可星际和平指`）。框要緊貼文字行，小字改用關鍵字模糊比對或模板比對。
- 同時看 `single_line` 與 `detect_and_ocr` 的 box，用來決定正式 `OCR_*` 素材的範圍。

## 單獨跑一段邏輯

模組底部的 `if __name__ == '__main__'` 範例寫死 `'src'` 設定，開發時改用 `'dev'`，並自己設定 adb 埠：

```bash
export ANDROID_ADB_SERVER_PORT=5038
.venv/Scripts/python.exe - <<'EOF'
from tasks.dungeon.ui.ui import DungeonUI
from tasks.dungeon.keywords import KEYWORDS_DUNGEON_TAB, KEYWORDS_DUNGEON_NAV
self = DungeonUI('dev', task='Dungeon')
self.device.screenshot()
self.dungeon_tab_goto(KEYWORDS_DUNGEON_TAB.Simulated_Universe)
self.dungeon_nav_goto(KEYWORDS_DUNGEON_NAV.Currency_Wars)
self.device.image_save('screenshots/after.png')
EOF
```

- 長時間的測試（一整局自動戰鬥）用 Bash `run_in_background` 跑，log 寫到 `$TEMP/src_dev/*.log`，再用 Monitor `tail -F log | grep --line-buffered` 只訂閱里程碑點擊與 `CRITICAL|ERROR|Traceback|Wait too long|Too many click`。改了程式碼要重跑時，先 TaskStop 舊的背景任務，避免兩個程序同時操作模擬器。
- 跑完整任務時走 `StarRailCopilot('dev')`，先 `src.config.bind('<Task>')`，再覆寫要測的設定值（例如 `src.config.<Group>_<Arg> = 1`），然後呼叫 `src.run('<snake_case 任務名>')`。這只改記憶體中的值，不會寫回 dev.json。
- 要測排程器的錯誤處理（例外分類、重啟、存錯誤截圖），就走 `StarRailCopilot('dev').run('<任務方法名>')`，不要直接呼叫任務的 `run()`。遇到 ScriptError 或未知例外時它會 `exit(1)`。
- `dev.json` 有其他到期的任務時，任務在第一次 `task_switched()` 檢查就會交出控制權。驗收多局流程時，在腳本裡設 `src.config.task_switched = lambda: False`。
- Monitor 最長 30 分鐘就會過期，過期後用 `tail -n 0 -F` 重新訂閱，避免重複收到舊事件。
- 正常操作也可能需要連點同一個按鈕 12 次以上（例如金幣很多時連買經驗）。每次確認動作有生效（數值有變）就 `click_record_clear()`，只有沒生效時才算卡住。
- 長時間等待（自動戰鬥、動畫）時，`device.stuck_record_check()` 會丟 `GameStuckError`；同一個按鈕在最近 15 次點擊中出現 12 次會丟 `GameTooManyClickError`。等待迴圈裡要呼叫 `self.device.stuck_record_clear()`，重複點擊要用 `click_record_clear()` 或 interval 控制。

## 設定 schema

- 改完 `module/config/argument/{task,argument}.yaml` 後執行 `.venv/Scripts/python.exe -m module.config.config_updater`。它會重新生成 `args.json`、`menu.json`、`config_generated.py`、`config/template.json`，並在五個 `i18n/*.json` 裡留下 `"Task.X.name"` 這種佔位字串，要自己填中文和英文。
- 不要用 Bash heredoc 裡的 Python 字串去替換含 `\` 續行的程式碼，續行會被吃掉、合成一行。多行或含反斜線的修改用 Edit 工具。
- 在 Windows 上用 Python 改寫 yaml 或 py 檔時，`open(...,'w')` 會把行尾變成 CRLF；repo 規定 `eol=lf`。改完用 `git diff --stat` 檢查有沒有出現 CRLF warning，有的話就轉回 LF。

## 導航與頁面

- 關閉遊戲內面板前先確認左上角是什麼。`handle_ui_back` 點的是左上角的 BACK，但有些玩法的左上角是「退出」。點空白處關不掉的面板（例如角色詳情），改用 Android 返回鍵 `self.device.adb_shell(['input', 'keyevent', '4'])`，而且只在認出該面板時才送。

- `goto` / `ui_ensure` 只認得 `tasks/base/page.py` 裡定義的頁面。從其他畫面（例如活動或玩法大廳）啟動時，`ui_get_current_page` 會在 10 秒後丟 `GamePageUnknownError`。新玩法的大廳要嘛加成 `Page` 並 link 回 `page_main`，要嘛由任務自己的狀態機先退回已知頁面。
- 「從任意畫面恢復」要在不同的畫面實際啟動測過：先用 `page` 確認該畫面被認成什麼，再跑任務入口。

## Log 與錯誤截圖

- log 檔是 `log/<日期>_<腳本名>.txt`；stdin 腳本的名稱是 `-`，`emu.py` 的名稱是 `emu`。
- 錯誤時產生 `log/error/<毫秒時間戳>/`：最近的截圖 `*.png`（張數由 `Error.ScreenshotLength` 決定，dev.json 設為 30）加上 `log.txt`。用 Read 工具從最後一張往前看，對照 log 中最後幾個 `Click` 與 `[UI]` 行，判斷卡在哪個畫面、狀態機漏了哪個分支。
- 看完就刪掉 `log/error/` 裡自己產生的資料夾（log/ 本來就不會 commit，刪掉只是為了避免下次誤讀）。

## 環境重建

- **adb**：SDK 的 adb 37 佔用 5037，SRC 自帶的 adb 是 34。兩個版本共用同一個 server 埠會互相踢掉對方。開發時一律用 `ANDROID_ADB_SERVER_PORT=5038`（emu.py 已預設），讓自帶的 adb 起一個獨立的 server，兩邊都能看到 `127.0.0.1:16384`。`emulator-5554` 是無關的 Android Studio 模擬器，不要動它。
- **截圖**：設定寫的是 scrcpy，但偵測到 MuMu 12 時 device 層會自動改用 `nemu_ipc`。log 裡的 `check_mumu_app_keep_alive ... MuMuPlayer-12.0-0 ... not exists` 是實例路徑命名不符造成的，無害。
- **venv**：用攜帶版 SRC 的 `D:\Apps\Portable\StarRailCopilot\toolkit\python.exe -m venv .venv`（只借用它的直譯器）。PyPI 上已經沒有 `av==10.0.0` 的 wheel，原始碼編譯會失敗，所以先裝 `requirements.txt` 裡 av 以外的套件，再把 toolkit 的 `Lib/site-packages/{av,av.libs,av-10.0.0.dist-info}` 複製進 `.venv/Lib/site-packages/`。
- **dev.json**：`config/template.json` 拷貝一份，`Alas.Emulator` / `Alas.EmulatorInfo` 取自攜帶版 `config/src.json`（serial `127.0.0.1:16384`、`CN-Official`、`cn`）；`Optimization.WhenTaskQueueEmpty=stay_there`、`Error.ScreenshotLength=30`。
