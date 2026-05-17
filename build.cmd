@echo off
:: MTG Deck Imager — Build Script
:: Installs dependencies and rebuilds the standalone .exe
echo ============================================
echo   MTG Deck Imager — Build
echo ============================================
echo.
echo Installing dependencies...
python -m pip install -r "%~dp0requirements.txt" --quiet
if %ERRORLEVEL% neq 0 (
    echo ERROR: pip install failed. Is Python installed and on PATH?
    pause
    exit /b 1
)
echo.
echo Building executable...
python "%~dp0build_exe.py"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Build failed.
    pause
    exit /b 1
)
echo.
echo ============================================
echo   Build complete!
echo   Output: dist\MTGDeckImager.exe
echo ============================================
pause
