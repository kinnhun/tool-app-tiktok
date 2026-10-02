@echo off
chcp 65001 >nul
title Build TikTok Shop Scraper EXE
echo ========================================================
echo   Đang đóng gói ứng dụng sang file EXE...
echo ========================================================
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" build_exe.py
) else (
    python build_exe.py
)
pause
