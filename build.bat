@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   Сборка MapAUVcoder.exe
echo ========================================
echo.

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo [OK] venv активирован
)

set SRC=
if exist "MapAUVcoder.py" set SRC=MapAUVcoder.py
if exist "shifr.py"        set SRC=shifr.py

if "%SRC%"=="" (
    echo [ОШИБКА] Не найден MapAUVcoder.py или shifr.py
    pause
    exit /b 1
)
echo [OK] Исходник: %SRC%

REM Конвертация PNG → ICO, если нужно
if exist "icon.png" if not exist "icon.ico" (
    echo [!] Конвертирую icon.png → icon.ico
    python -c "from PIL import Image; img=Image.open('icon.png').convert('RGBA'); img.save('icon.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
    if errorlevel 1 (
        echo [!] Не удалось конвертировать. Установи: pip install pillow
    )
)

set ICON_ARG=
if exist "icon.ico" (
    set ICON_ARG=--icon=icon.ico
    echo [OK] Иконка: icon.ico
) else (
    echo [!] icon.ico не найден — exe будет без своей иконки
)

where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [!] Ставлю pyinstaller + pygame + pillow...
    pip install pyinstaller pygame pillow
)

echo.
echo Сборка...
pyinstaller --noconfirm --onefile --windowed --name MapAUVcoder %ICON_ARG% "%SRC%"

if errorlevel 1 (
    echo.
    echo [ОШИБКА] Сборка не удалась
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Готово: dist\MapAUVcoder.exe
echo ========================================
explorer dist
pause