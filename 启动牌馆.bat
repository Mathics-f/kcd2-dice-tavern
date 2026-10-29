@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 骰子酒馆
echo 正在开张...
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 server.py
) else (
    python server.py
)
echo.
pause
