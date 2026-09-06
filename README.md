# 圖片轉檔小工具

Windows 10/11 上的圖片轉檔程式。有圖形介面、可拖曳、批次轉檔、可調品質。

## 功能

- 🖼️ 多格式輸入：WebP / PNG / JPG / BMP / GIF / TIFF / HEIC（HEIC 需 `pillow-heif`）
- 🎯 多格式輸出：JPG / PNG / WEBP（下拉選單切換）
- 📦 批次多檔一次轉
- 🎚️ 品質滑桿（1–100，有損格式；PNG 無損會自動停用）
- 🖱️ 拖曳檔案進清單（需 `tkinterdnd2`）
- 📁 自選輸出資料夾，或勾「預設」輸出到來源檔旁邊
- 🔢 可選「重新命名」：以流水號命名（001、002…），起始數字可設（0–9）
- ⚪ 智慧透明處理：輸出 PNG/WEBP 保留透明，輸出 JPG 才填白底
- ⚠️ 目的地檔名衝突（已存在／批次內互撞）會跳警告讓你選覆蓋/略過/取消
- 💾 設定會自動記憶（格式、品質、輸出位置等）
- 🛡️ 單檔失敗不中斷整批，最後回報失敗清單

## 專案結構

本專案有兩支程式：

- **webp2jpg**（`app.py`）：主圖片轉檔工具，清單以「檔案」為單位。
- **webp2jpg-folder**（`folder_app.py`）：資料夾批次工具，清單以「資料夾」為單位，
  把每個資料夾內的圖片就地轉成 JPG、成功後原圖移到資源回收桶（交易式、逐夾處理）。

```
webp2jpg/
├── build.bat            Windows 打包腳本（在根目錄執行，一次產生兩個 exe）
├── README.md
├── src/                 原始碼
│   ├── app.py               主程式 GUI
│   ├── folder_app.py        資料夾批次工具 GUI
│   ├── converter.py         轉檔核心邏輯（純函式）
│   ├── folder_core.py       資料夾交易式處理核心（純函式）
│   ├── test_converter.py    converter 單元測試
│   ├── test_folder_core.py  folder_core 單元測試
│   └── requirements.txt
├── webp2jpg.exe         主程式執行檔（不進版控）
├── webp2jpg-folder.exe  資料夾工具執行檔（不進版控）
└── build/               打包暫存工作夾（不進版控）
```

## 安裝與執行（開發模式）

需要 Python 3.8+。

```bash
pip install -r src/requirements.txt
python src/app.py          # 主程式
python src/folder_app.py   # 資料夾批次工具
```

> 沒安裝 `tkinterdnd2` 也能跑，只是不能拖曳，改用按鈕加入即可。

## 打包成執行檔（給沒有 Python 的電腦用）

在 Windows 上、於專案根目錄直接執行：

```bat
build.bat
```

採用 `--onefile` 模式，一次產生兩個執行檔 `webp2jpg.exe` 與 `webp2jpg-folder.exe`
直接放在根目錄，雙擊即可執行；打包暫存則留在 `build\`。設定檔 `config.json` 會存在
exe 同一層。複製這兩顆 exe 就能拿到別台電腦執行。

> 注意：onefile 每次啟動會先解壓到暫存區，開啟比 onedir 慢幾秒；且未簽章的
> exe 可能被防毒（如 Avast）誤判攔下，需自行加入例外或回報誤判。

## 測試

```bash
pip install pytest
cd src && pytest
```
