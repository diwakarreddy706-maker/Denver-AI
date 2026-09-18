# ============================================================================
# Denver AI Assistant - Windows Release Build Script
# ============================================================================
# Description: Compiles and packages Denver AI Assistant into a standalone
#              Windows release candidate (Denver.exe) using PyInstaller.
# Platform:    Windows 11 / Windows 10 (x64)
# Python:      Python 3.14.7
# ============================================================================

param (
    [switch]$SkipTests,
    [switch]$SkipClean
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
Set-Location $ProjectRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  DENVER AI ASSISTANT - WINDOWS RELEASE BUILD PIPELINE      " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot"

# 1. Verify Python Version
Write-Host "`n[1/7] Verifying Python runtime..." -ForegroundColor Yellow
$PythonVersion = & python --version 2>&1
Write-Host "Python Version: $PythonVersion"

# 2. Verify PyInstaller Installation
Write-Host "`n[2/7] Checking PyInstaller availability..." -ForegroundColor Yellow
try {
    $PyInstallerVersion = & python -m PyInstaller --version 2>&1
    Write-Host "PyInstaller Version: $PyInstallerVersion"
} catch {
    Write-Host "PyInstaller not found. Installing..." -ForegroundColor Yellow
    & pip install pyinstaller
}

# 3. Execute Regression Test Suite
if (-not $SkipTests) {
    Write-Host "`n[3/7] Running test suite validation..." -ForegroundColor Yellow
    & python -m pytest
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Test suite failed! Aborting release build."
        exit 1
    }
    Write-Host "Test suite: 100% PASS." -ForegroundColor Green
} else {
    Write-Host "`n[3/7] Skipping test suite as requested." -ForegroundColor Gray
}

# 4. Clean Build Artifacts (Never delete database or user data)
if (-not $SkipClean) {
    Write-Host "`n[4/7] Cleaning temporary build artifacts..." -ForegroundColor Yellow
    if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    if (Test-Path "dist\Denver") { Remove-Item -Recurse -Force "dist\Denver" }
}

# 5. Build Standalone Executable via PyInstaller
Write-Host "`n[5/7] Compiling Denver.exe (One-Folder Mode)..." -ForegroundColor Yellow
& python -m PyInstaller "denver.spec" --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed!"
    exit 1
}

# 6. Verify Executable & Populate Release Metadata
Write-Host "`n[6/7] Verifying release package..." -ForegroundColor Yellow
$ExePath = "$ProjectRoot\dist\Denver\Denver.exe"

if (-not (Test-Path $ExePath)) {
    Write-Error "Executable not found at expected location: $ExePath"
    exit 1
}

# Generate release metadata files
$VersionInfo = @"
Denver AI Assistant v0.1.0
Target Platform: Windows (x64)
Runtime: Python 3.14.7 / PySide6 6.11.2 (Qt 6)
Build Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Status: Windows Release Candidate
"@
$VersionInfo | Out-File -FilePath "$ProjectRoot\dist\Denver\VERSION.txt" -Encoding utf8

$ReadmeInfo = @"
============================================================
  DENVER AI ASSISTANT - WINDOWS RELEASE CANDIDATE
============================================================

To run Denver Cockpit GUI:
  .\Denver.exe --gui

To run CLI Health Diagnostics:
  .\Denver.exe --health

To check Configuration:
  .\Denver.exe --check-config

To run a single command:
  .\Denver.exe -c "Denver, what time is it?"

Data and memory are stored in your user profile:
  %LOCALAPPDATA%\Denver\
============================================================
"@
$ReadmeInfo | Out-File -FilePath "$ProjectRoot\dist\Denver\README.txt" -Encoding utf8

# 7. Smoke Test Release Executable
Write-Host "`n[7/7] Running executable smoke tests..." -ForegroundColor Yellow
Write-Host "Checking --version output:"
& $ExePath --version
Write-Host "Checking --check-config output:"
& $ExePath --check-config

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "  BUILD SUCCESSFUL: Denver Windows Release Candidate Ready  " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Executable: $ExePath"
Write-Host "Directory:  $ProjectRoot\dist\Denver"
