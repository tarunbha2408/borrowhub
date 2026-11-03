@echo off
cd /d "%~dp0"
title BorrowHub Automated Test Suite
echo ================================================================================
echo BORROWHUB AUTOMATED TEST SUITE (pytest)
echo ================================================================================
echo.
python -m pytest backend/tests -v
echo.
pause
