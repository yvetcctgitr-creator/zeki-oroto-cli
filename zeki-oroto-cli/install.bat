@echo off
echo.
echo ========================================
echo    OROTO CLI TOOL - KURULUM SCRIPTI
echo ========================================
echo.

REM Yönetici yetkisini kontrol et; yoksa kullanıcı PATH'i güncelle
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] Yonetici yetkileri mevcut. Sistem PATH guncellenecek.
    set "TARGET_SCOPE=machine"
) else (
    echo [INFO] Yonetici yetkisi yok. Kullanici PATH guncellenecek.
    set "TARGET_SCOPE=user"
)

REM Mevcut dizini al
set "OROTO_PATH=%~dp0"
set "OROTO_PATH=%OROTO_PATH:~0,-1%"

echo Oroto dizini: %OROTO_PATH%
echo.

REM Python kurulu mu kontrol et
python --version >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] Python kurulu.
    python --version
) else (
    echo [HATA] Python bulunamadi! Lutfen Python'u kurun.
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

echo.
echo Gerekli Python paketleri kuruluyor...
pip install httpx rich

REM Komut shimi olusturuluyor (Python Scripts dizinine)
for /f "delims=" %%I in ('python -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'Scripts'))"') do set "PY_SCRIPTS=%%I"
if exist "%PY_SCRIPTS%" (
    echo Shim dizini: %PY_SCRIPTS%
    > "%PY_SCRIPTS%\oroto.cmd" echo @echo off
    >> "%PY_SCRIPTS%\oroto.cmd" echo "%OROTO_PATH%\oroto.bat" %%*
    if exist "%PY_SCRIPTS%\oroto.cmd" (
        echo [OK] Komut shimi olusturuldu: %PY_SCRIPTS%\oroto.cmd
    ) else (
        echo [WARN] Sistem Scripts klasorune yazilamadi. Kullanici Scripts klasorune denenecek.
        for /f "delims=" %%J in ('python -c "import site, os; print(os.path.join(site.getuserbase(), 'Scripts'))"') do set "USER_SCRIPTS=%%J"
        if not exist "%USER_SCRIPTS%" (
            mkdir "%USER_SCRIPTS%" >nul 2>&1
        )
        > "%USER_SCRIPTS%\oroto.cmd" echo @echo off
        >> "%USER_SCRIPTS%\oroto.cmd" echo "%OROTO_PATH%\oroto.bat" %%*
        if exist "%USER_SCRIPTS%\oroto.cmd" (
            echo [OK] Komut shimi olusturuldu: %USER_SCRIPTS%\oroto.cmd
        ) else (
            echo [HATA] Komut shimi olusturulamadi.
        )
    )
) else (
    echo [WARN] Python Scripts klasoru bulunamadi: %PY_SCRIPTS%
)
echo.
echo PATH'e Oroto dizini ekleniyor...

REM Mevcut PATH'i al ve hedefe gore guncelle
if /I "%TARGET_SCOPE%"=="machine" (
    for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul') do set "CURRENT_PATH=%%B"
) else (
    for /f "tokens=2*" %%A in ('reg query "HKCU\\Environment" /v PATH 2^>nul') do set "CURRENT_PATH=%%B"
    if not defined CURRENT_PATH set "CURRENT_PATH=%PATH%"
)

REM Oroto dizini zaten PATH'te var mı kontrol et
echo %CURRENT_PATH% | findstr /i "%OROTO_PATH%" >nul
if %errorLevel% == 0 (
    echo [OK] Oroto dizini zaten PATH'te mevcut.
) else (
    echo Oroto dizini PATH'e ekleniyor...
    if /I "%TARGET_SCOPE%"=="machine" (
        setx PATH "%CURRENT_PATH%;%OROTO_PATH%" /M
    ) else (
        setx PATH "%CURRENT_PATH%;%OROTO_PATH%"
    )
    echo [OK] PATH guncelleme komutu calistirildi.
    echo [INFO] Degisikliklerin etkin olmasi icin yeni bir terminal penceresi acin.
)

echo.
echo ========================================
echo           KURULUM TAMAMLANDI!
echo ========================================
echo.
echo Artik herhangi bir terminal/cmd penceresinde
echo "oroto" komutunu kullanabilirsiniz.
echo.
echo Kullanim:
echo   oroto          - Oroto'yu baslat
echo   oroto --help   - Yardim
echo.
echo NOT: Yeni terminal penceresi acmaniz gerekebilir.
echo.
pause