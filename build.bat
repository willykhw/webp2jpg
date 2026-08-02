@echo off
REM Build a single-file Windows .exe (no Python needed to run the result).
REM Usage: double-click this file, or run build.bat in a terminal.
REM Output: dist\webp2jpg.exe

echo [1/2] Installing dependencies...
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto error

echo [2/2] Packaging...
REM --collect-all tkinterdnd2 bundles the tkdnd resources, otherwise
REM drag-and-drop stops working after packaging.
REM --distpath . puts webp2jpg.exe right here instead of in a dist\ folder.
pyinstaller --noconfirm --onefile --windowed --name webp2jpg --collect-all tkinterdnd2 --distpath . app.py
if errorlevel 1 goto error

echo.
echo Done. The executable is webp2jpg.exe (in this folder).
goto end

:error
echo.
echo Build failed. Please check the error messages above.
exit /b 1

:end
