@echo off
cd /d "%~dp0"
echo =============================================
echo   WhoAteMySalary  -  PyQt5 edition
echo =============================================
echo Launching (Python 3.12 + PyQt5)...
rmdir /s /q __pycache__ 2>nul
python -c "import PyQt5" 2>nul || python -m pip install PyQt5 --quiet
python -c "import windows_toasts" 2>nul || python -m pip install windows-toasts --quiet
python -c "import win32com" 2>nul || python -m pip install pywin32 --quiet
python -c "import winotify" 2>nul || python -m pip install winotify --quiet
python app.py
echo.
echo (window closed) - press a key to exit.
pause >nul
