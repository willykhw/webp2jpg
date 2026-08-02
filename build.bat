@echo off
REM Build the app into a single webp2jpg.exe in this folder.
REM Usage: double-click this file, or run build.bat in a terminal.
REM Output: webp2jpg.exe (in this folder). Scratch stays under build\.

echo [1/2] Installing dependencies...
python -m pip install -r src\requirements.txt pyinstaller
if errorlevel 1 goto error

echo [2/2] Packaging (onefile)...
REM --onefile: one portable .exe (slower start, but no support folder needed).
REM --collect-all tkinterdnd2 bundles the tkdnd resources for drag-and-drop.
REM --distpath . puts webp2jpg.exe here; work dir + .spec stay under build\.
pyinstaller --noconfirm --onefile --windowed --name webp2jpg --collect-all tkinterdnd2 --distpath . --workpath build\_work --specpath build src\app.py
if errorlevel 1 goto error

echo.
echo Done. Run webp2jpg.exe in this folder.
goto end

:error
echo.
echo Build failed. Please check the error messages above.
exit /b 1

:end
