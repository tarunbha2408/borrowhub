@echo off
cd /d "%~dp0"
title BorrowHub Database Setup
echo ================================================================================
echo BORROWHUB DATABASE SETUP (MySQL 8.0)
echo ================================================================================
echo.
echo Installing Python dependencies from backend/requirements.txt ...
python -m pip install -r backend/requirements.txt
echo.
echo If your MySQL root password is not '12345', please update backend/.env accordingly.
echo Importing schema.sql and seed.sql into MySQL 'borrowhub' database...
mysql -u root -p12345 -e "CREATE DATABASE IF NOT EXISTS borrowhub CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -p12345 --default-character-set=utf8mb4 borrowhub < database/schema.sql
mysql -u root -p12345 --default-character-set=utf8mb4 borrowhub < database/seed.sql
echo.
echo Database setup completed successfully!
echo You can now double-click 'start_server.bat' to launch BorrowHub.
echo.
pause
