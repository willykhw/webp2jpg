# 圖片轉檔小工具

Windows 10/11 上的圖片轉檔程式。有圖形介面、可拖曳、批次轉檔、可調品質與縮放。

## 功能

- 🖼️ 多格式輸入：WebP / PNG / JPG / BMP / GIF / TIFF
- 🎯 多格式輸出：JPG / PNG / WEBP（下拉選單切換）
- 📦 批次多檔一次轉
- 🎚️ 品質滑桿（1–100，有損格式；PNG 無損會自動停用）
- 📐 尺寸縮放：可限制最長邊，等比例縮小（不放大）
- 🖱️ 拖曳檔案進清單（需 `tkinterdnd2`）
- 📁 自選輸出資料夾，或勾「預設」輸出到來源檔旁邊
- ⚪ 智慧透明處理：輸出 PNG/WEBP 保留透明，輸出 JPG 才填白底
- ⚠️ 目的地檔名衝突（已存在／批次內互撞）會跳警告讓你選覆蓋/略過/取消
- 💾 設定會自動記憶（格式、品質、輸出位置、縮放等）
- 🛡️ 單檔失敗不中斷整批，最後回報失敗清單

## 安裝與執行（開發模式）

需要 Python 3.8+。

```bash
pip install -r requirements.txt
python app.py
```

> 沒安裝 `tkinterdnd2` 也能跑，只是不能拖曳，改用「加入檔案」按鈕即可。

## 打包成 .exe（給沒有 Python 的電腦用）

在 Windows 上直接執行：

```bat
build.bat
```

完成後執行檔 `webp2jpg.exe` 就在本資料夾內（跟 app.py 同一層），雙擊即可使用。設定檔 `config.json` 也會存在同一層。

## 檔案說明

| 檔案 | 說明 |
| --- | --- |
| `app.py` | tkinter 圖形介面 |
| `converter.py` | 轉檔核心邏輯（與 UI 無關，純函式） |
| `test_converter.py` | 核心邏輯的單元測試 |
| `build.bat` | Windows 打包腳本 |

## 測試

```bash
pip install pytest
pytest
```
