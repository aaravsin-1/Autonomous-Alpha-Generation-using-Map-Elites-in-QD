@echo off
REM ============================================================
REM  nse_morning.bat — NSE Production Morning Routine
REM  Run this every morning at 9:00 AM IST (before market opens)
REM
REM  What it does:
REM    1. Checks if today is an NSE trading day
REM    2. Downloads latest NIFTYBEES data
REM    3. Computes signal from QD archive
REM    4. In PAPER mode: logs to journal
REM    5. In LIVE mode: places real order via broker API
REM    6. Monthly health check if due
REM ============================================================

title NSE QD Trading - Morning Routine

cd /d "%~dp0"

echo.
echo ============================================================
echo   NSE QD TRADING SYSTEM
echo   Running morning routine...
echo ============================================================
echo.

REM ── Run the full morning routine (paper mode) ─────────────────
python morning.py --csv data/NIFTYBEES.csv

echo.
echo ============================================================
echo   Done. Check logs\latest_summary.txt
echo ============================================================
echo.
pause
