@echo off
cd /d "%~dp0"
echo =============================================
echo   Mail Money Tracker  -  PyQt5 edition
echo =============================================
echo Launching (Python 3.12 + PyQt5)...
rmdir /s /q __pycache__ 2>nul
py -3.12 -c "import PyQt5" 2>nul || py -3.12 -m pip install PyQt5 --quiet
py -3.12 -c "import windows_toasts" 2>nul || py -3.12 -m pip install windows-toasts --quiet
py -3.12 -c "import win32com" 2>nul || py -3.12 -m pip install pywin32 --quiet
py -3.12 -c "import winotify" 2>nul || py -3.12 -m pip install winotify --quiet
py -3.12 app.py
echo.
echo (window closed) - press a key to exit.
pause >nul
