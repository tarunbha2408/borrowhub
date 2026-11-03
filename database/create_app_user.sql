-- ============================================================================
--  BorrowHub - application database user
-- ============================================================================
--  When is this needed?
--  If the MySQL/MariaDB root account uses the `unix_socket` / `auth_socket`
--  plugin (the default on Arch, Fedora and the Ubuntu MariaDB packages), root
--  cannot connect with a password and the application fails with:
--
--      (1698, "Access denied for user 'root'@'localhost'")
--
--  In that case create a dedicated account for the application. This file does
--  exactly that.
--
--  How to run it (as root, through the socket login):
--      sudo mariadb < database/create_app_user.sql          # MariaDB
--      sudo mysql   < database/create_app_user.sql          # MySQL
--
--  Or from an interactive shell:
--      sudo mariadb
--      SOURCE database/create_app_user.sql;
-- ============================================================================

-- 1) Application user. The password uses only letters and digits so it needs no
--    URL-encoding inside DATABASE_URL.
CREATE USER IF NOT EXISTS 'borrowhub'@'localhost' IDENTIFIED BY 'BorrowHub2026';

-- 2) Full access to the application database: tables, views, triggers and
--    stored routines. (ALL PRIVILEGES covers SELECT/INSERT/UPDATE/DELETE/
--    CREATE/ALTER/INDEX/REFERENCES/CREATE ROUTINE/ALTER ROUTINE/EXECUTE/TRIGGER.)
--
--    NOTE: change the database name below if you used a different one.
--    The default name is: borrowhub
CREATE DATABASE IF NOT EXISTS borrowhub
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

GRANT ALL PRIVILEGES ON borrowhub.* TO 'borrowhub'@'localhost';

FLUSH PRIVILEGES;

-- 3) Confirm - these three statements should work:
--      SHOW GRANTS FOR 'borrowhub'@'localhost';
--      SELECT user, host, plugin FROM mysql.user WHERE user = 'borrowhub';
-- ----------------------------------------------------------------------------
-- Now set this in backend/.env:
--
--   DATABASE_URL=mysql+pymysql://borrowhub:BorrowHub2026@localhost:3306/borrowhub?charset=utf8mb4
--
-- then restart the server (backend/.env is only read at startup).
--
-- Test from the shell, outside the application:
--   mariadb -u borrowhub -pBorrowHub2026 borrowhub -e "SELECT COUNT(*) FROM app_user;"
--   -> should return 7 (the data created by seed.sql). If it returns 0, run seed.sql.
-- ============================================================================
