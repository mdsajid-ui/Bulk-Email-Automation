@echo off
title Bulk Email Automator
echo ======================================================
echo           Bulk Email Automator Launcher
echo ======================================================
echo.
echo Starting Flask web server...
start "" http://127.0.0.1:5000
py app.py
pause
