# WebP → JPG 轉檔小工具

Windows 10/11 上的圖片轉檔程式，把 `.webp` 轉成 `.jpg`。有圖形介面、可拖曳檔案、批次轉檔、自選輸出資料夾、可調 JPG 品質。

## 功能

- 🖼️ WebP → JPG 轉檔（其他格式之後再擴充）
- 📦 批次多檔一次轉
- 🎚️ JPG 品質滑桿（1–100，預設 90）
- 🖱️ 拖曳檔案進清單（需 `tkinterdnd2`）
- 📁 自選輸出資料夾
- ⚪ 透明背景自動填白底（JPG 不支援透明）
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
