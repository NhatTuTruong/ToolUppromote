@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Installing build dependencies...
python -m pip install -q -r requirements.txt -r requirements-build.txt
if errorlevel 1 exit /b 1

echo Building AffiliateOfferFilter.exe ...
python -m PyInstaller build_exe.spec --noconfirm
if errorlevel 1 exit /b 1

echo.
echo Done: dist\AffiliateOfferFilter.exe
echo.
echo Ban ban: dat .env (AFF_LICENSE_HMAC_SECRET, token...) cung thu muc voi .exe.
echo Khong dong goi: .aff_license.json  .aff_free_usage.json  .aff_licensed_usage.json
echo   (de trang thai ban dau: chua kich hoat key).
echo.
echo Put .env in the same folder as the exe (or edit there after first run).
pause
