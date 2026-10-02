@echo off
chcp 65001 >nul
title TikTok Shop Price Scraper
echo ========================================================
echo   Đang khởi chạy TikTok Shop Price Scraper...
echo ========================================================
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
) else (
    python main.py
)
pause
