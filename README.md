# 圖片轉檔小工具

Windows 10/11 上的圖片轉檔程式。有圖形介面、可拖曳、批次轉檔、可調品質。

## 功能

- 🖼️ 多格式輸入：WebP / PNG / JPG / BMP / GIF / TIFF
- 🎯 多格式輸出：JPG / PNG / WEBP（下拉選單切換）
- 📦 批次多檔一次轉
- 🎚️ 品質滑桿（1–100，有損格式；PNG 無損會自動停用）
- 🖱️ 拖曳檔案進清單（需 `tkinterdnd2`）
- 📁 自選輸出資料夾，或勾「預設」輸出到來源檔旁邊
- ⚪ 智慧透明處理：輸出 PNG/WEBP 保留透明，輸出 JPG 才填白底
- ⚠️ 目的地檔名衝突（已存在／批次內互撞）會跳警告讓你選覆蓋/略過/取消
- 💾 設定會自動記憶（格式、品質、輸出位置等）
- 🛡️ 單檔失敗不中斷整批，最後回報失敗清單

## 專案結構

```
webp2jpg/
├── build.bat          Windows 打包腳本（在根目錄執行）
├── README.md
├── src/               原始碼
│   ├── app.py             tkinter 圖形介面
│   ├── converter.py       轉檔核心邏輯（與 UI 無關，純函式）
│   ├── test_converter.py  核心邏輯的單元測試
│   └── requirements.txt
├── webp2jpg.exe       build.bat 產生的單一執行檔（不進版控）
└── build/             打包暫存工作夾（不進版控）
```

## 安裝與執行（開發模式）

需要 Python 3.8+。

```bash
pip install -r src/requirements.txt
python src/app.py
```

> 沒安裝 `tkinterdnd2` 也能跑，只是不能拖曳，改用「加入檔案」按鈕即可。

## 打包成執行檔（給沒有 Python 的電腦用）

在 Windows 上、於專案根目錄直接執行：

```bat
build.bat
```

採用 `--onefile` 模式，產生**單一** `webp2jpg.exe` 直接放在根目錄，雙擊即可執行；
打包暫存則留在 `build\`。設定檔 `config.json` 會存在 exe 同一層。只要複製這顆
`webp2jpg.exe` 就能拿到別台電腦執行。

> 注意：onefile 每次啟動會先解壓到暫存區，開啟比 onedir 慢幾秒；且未簽章的
> exe 可能被防毒（如 Avast）誤判攔下，需自行加入例外或回報誤判。

## 測試

```bash
pip install pytest
cd src && pytest
```
