@echo off
cd /d "%~dp0"
python -c "import PySide6.QtWidgets" >nul 2>&1
if errorlevel 1 (
  echo Please install dependencies: python -m pip install -r requirements.txt
  pause
  exit /b 1
)
start "" pythonw "%~dp0main.py"
