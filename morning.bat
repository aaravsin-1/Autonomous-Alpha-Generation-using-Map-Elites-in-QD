@echo off
REM ============================================================
REM  morning.bat — Double-click this every morning
REM  Handles everything automatically
REM ============================================================

title QD Trading System - Morning Routine

cd /d "%~dp0"

echo.
echo  Running morning routine...
echo  This will:
echo    - Update SPY data
echo    - Compute today's signal
echo    - Update paper trading journal
echo    - Run monthly health check if due
echo    - Trigger re-evolution if needed
echo.

python morning.py

echo.
echo  Done. Check logs\latest_summary.txt for a clean summary.
echo.
pause