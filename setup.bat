@echo off
echo ========================================
echo Shopify VAT Invoice Scraper Setup
echo ========================================
echo.

REM Check Python
python --version 2>nul
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Installing Camoufox browser...
python -m camoufox fetch

echo.
echo ========================================
echo Setup complete!
echo.
echo To start the scraper:
echo   1. Open a new terminal in this directory
echo   2. Run: venv\Scripts\activate
echo   3. Run: python -m src.main
echo.
echo The API will be available at: http://localhost:8000
echo ========================================
pause
