@echo off
REM One-click Host GUI launcher for Windows (no execution-policy hassle).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_host.ps1"
