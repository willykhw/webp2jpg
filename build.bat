@echo off
REM Build both tools into single .exe files in this folder.
REM   webp2jpg.exe         - main image converter (app.py)
REM   webp2jpg-folder.exe  - folder batch tool (folder_app.py)
REM Usage: double-click this file, or run build.bat in a terminal.
REM Scratch (work dir + .spec) stays under build\.

echo [1/3] Installing dependencies...
python -m pip install -r src\requirements.txt pyinstaller
if errorlevel 1 goto error

echo [2/3] Packaging webp2jpg.exe ...
pyinstaller --noconfirm --onefile --windowed --name webp2jpg --collect-all tkinterdnd2 --collect-all comtypes --collect-all pillow_heif --distpath . --workpath build\_work --specpath build src\app.py
if errorlevel 1 goto error

echo [3/3] Packaging webp2jpg-folder.exe ...
pyinstaller --noconfirm --onefile --windowed --name webp2jpg-folder --collect-all tkinterdnd2 --collect-all send2trash --collect-all comtypes --collect-all pillow_heif --distpath . --workpath build\_work --specpath build src\folder_app.py
if errorlevel 1 goto error

echo.
echo Done. webp2jpg.exe and webp2jpg-folder.exe are in this folder.
goto end

:error
echo.
echo Build failed. Please check the error messages above.
exit /b 1

:end
