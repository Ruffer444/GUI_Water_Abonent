@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   Сборка MapAUVcoder.exe
echo ========================================
echo.

REM Активация venv, если есть
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo [OK] venv активирован
) else (
    echo [!] venv не найден — используем системный Python
)

REM Ищем исходник
set SRC=
if exist "MapAUVcoder.py" set SRC=MapAUVcoder.py
if exist "shifr.py"        set SRC=shifr.py

if "%SRC%"=="" (
    echo [ОШИБКА] Не найден MapAUVcoder.py или shifr.py
    pause
    exit /b 1
)
echo [OK] Исходник: %SRC%

REM PyInstaller
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [!] PyInstaller не найден — ставлю...
    pip install pyinstaller pygame
)

echo.
echo Сборка...
pyinstaller --noconfirm --onefile --windowed --name MapAUVcoder "%SRC%"

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