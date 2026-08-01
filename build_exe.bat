@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo Build AffiliateOfferFilter.exe
echo ========================================
echo.

echo [1/4] Installing build dependencies...
python -m pip install -q -r requirements.txt -r requirements-build.txt
if errorlevel 1 exit /b 1

echo [2/4] Installing Playwright browsers (if not found)...
python -m playwright install chromium --with-deps 2>nul
if errorlevel 1 (
    echo    (playwright install failed, trying to continue anyway...)
)

echo [3/4] Building with PyInstaller...
python -m PyInstaller build_exe.spec --noconfirm
if errorlevel 1 exit /b 1

echo [4/4] Copying Playwright browsers to dist...
set "BROWSERS_SRC=%LOCALAPPDATA%\ms-playwright"
set "BROWSERS_DST=%~dp0dist\ms-playwright"

if exist "%BROWSERS_SRC%" (
    if not exist "%BROWSERS_DST%" (
        xcopy /E /I /Y "%BROWSERS_SRC%" "%BROWSERS_DST%" >nul 2>&1
        echo    Browsers copied to dist\ms-playwright
    ) else (
        echo    Browsers already exist in dist
    )
) else (
    echo    WARNING: Playwright browsers not found at %BROWSERS_SRC%
    echo    Please run: playwright install chromium
)

echo.
echo ========================================
echo Build complete!
echo ========================================
echo.
echo Output: dist\AffiliateOfferFilter.exe
echo.
echo Next steps:
echo   1. Copy .env to the same folder as the .exe
echo   2. Run: AffiliateOfferFilter.exe
echo.
echo On a NEW machine, copy the entire dist\ folder including ms-playwright\
echo.
pause
