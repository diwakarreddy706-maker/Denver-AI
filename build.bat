@echo off
setlocal enabledelayedexpansion

echo =====================================================================
echo   DENVER AI ASSISTANT -- WINDOWS PRODUCTION RELEASE BUILD PIPELINE
echo =====================================================================
echo.

:: Check non-interactive mode
set NON_INTERACTIVE=0
if "%1"=="--non-interactive" set NON_INTERACTIVE=1
if "%1"=="-y" set NON_INTERACTIVE=1
if defined CI set NON_INTERACTIVE=1

:: 1. Verify Python
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    if %NON_INTERACTIVE% equ 0 pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [INFO] Detected Python: %PYTHON_VERSION%

:: 2. Verify / Install PyInstaller
where pyinstaller >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [INFO] PyInstaller not found. Installing PyInstaller...
    pip install pyinstaller
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to install PyInstaller.
        if %NON_INTERACTIVE% equ 0 pause
        exit /b 1
    )
)

for /f "tokens=*" %%i in ('pyinstaller --version 2^>^&1') do set PYINSTALLER_VERSION=%%i
echo [INFO] Detected PyInstaller: %PYINSTALLER_VERSION%
echo.

:: 3. Run Pre-Build Test Suite
echo [STEP 1/3] Running pre-build test suite verification...
python -m pytest tests/unit/test_cyber_hud.py tests/unit/test_new_dashboard_cards.py tests/integration/test_ui_pipeline.py -q
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Pre-build test verification failed! Aborting release packaging.
    if %NON_INTERACTIVE% equ 0 pause
    exit /b 1
)
echo [SUCCESS] Pre-build tests passed.
echo.

:: 4. Build Standalone Executable via PyInstaller
echo [STEP 2/3] Compiling standalone Windows distribution via PyInstaller...
echo [INFO] Spec file: denver.spec
pyinstaller denver.spec --noconfirm --clean
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] PyInstaller compilation failed!
    if %NON_INTERACTIVE% equ 0 pause
    exit /b 1
)
echo [SUCCESS] Standalone executable compiled to dist\Denver\Denver.exe

:: Copy seed data and configuration template to standalone distribution
if not exist "dist\Denver\data" mkdir "dist\Denver\data"
if exist "data\apps.json" copy /y "data\apps.json" "dist\Denver\data\" >nul
if exist "data\contacts.json" copy /y "data\contacts.json" "dist\Denver\data\" >nul
if exist "data\routines.json" copy /y "data\routines.json" "dist\Denver\data\" >nul
if exist ".env.example" copy /y ".env.example" "dist\Denver\.env.example" >nul
echo [INFO] Staged runtime seed datasets into dist\Denver\data\
echo.

:: 5. Assemble Portable Release Archive & Run Security Verifier
echo [STEP 3/3] Packaging portable distribution and verifying release artifacts...
python release_build.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Portable release packaging or security verification failed!
    if %NON_INTERACTIVE% equ 0 pause
    exit /b 1
)
echo.

echo =====================================================================
echo   BUILD COMPLETED SUCCESSFULLY!
echo =====================================================================
echo   Standalone Binary : dist\Denver\Denver.exe
echo   Portable Archive  : dist\Denver-v0.1.0-Windows-Portable.zip
echo =====================================================================
echo.
if %NON_INTERACTIVE% equ 0 pause
