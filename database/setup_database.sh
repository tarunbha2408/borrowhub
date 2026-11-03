#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# BorrowHub - one-shot database setup for Linux (Arch / Fedora / Ubuntu)
#
#   bash database/setup_database.sh
#
# It performs four steps:
#   1. loads schema.sql (DROPs and recreates the borrowhub database)
#   2. loads seed.sql (demo accounts and items)
#   3. creates the application MySQL user used by backend/.env
#   4. verifies the result and prints the counts
#
# NOTE: schema.sql drops the borrowhub database. Back it up first
#       (mariadb-dump) if it holds data you want to keep.
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEMA="$ROOT_DIR/database/schema.sql"
SEED="$ROOT_DIR/database/seed.sql"
DB_NAME="borrowhub"
APP_USER="borrowhub"
APP_PASS="BorrowHub2026"

[ -f "$SCHEMA" ] || { echo "!! $SCHEMA not found"; exit 1; }
[ -f "$SEED" ]   || { echo "!! $SEED not found"; exit 1; }

SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

echo "==> 1/4  Loading schema.sql (the borrowhub database will be dropped and recreated)"
$SUDO mariadb -e "SOURCE $SCHEMA" || $SUDO mysql -e "SOURCE $SCHEMA"

echo "==> 2/4  Loading seed.sql"
$SUDO mariadb -e "SOURCE $SEED" || $SUDO mysql -e "SOURCE $SEED"

echo "==> 3/4  Creating the application user '$APP_USER' (password: $APP_PASS)"
$SUDO mariadb -e "CREATE USER IF NOT EXISTS '$APP_USER'@'localhost' IDENTIFIED BY '$APP_PASS';
                  ALTER USER '$APP_USER'@'localhost' IDENTIFIED BY '$APP_PASS';
                  GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$APP_USER'@'localhost';
                  FLUSH PRIVILEGES;" \
  || $SUDO mysql -e "CREATE USER IF NOT EXISTS '$APP_USER'@'localhost' IDENTIFIED BY '$APP_PASS';
                     ALTER USER '$APP_USER'@'localhost' IDENTIFIED BY '$APP_PASS';
                     GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$APP_USER'@'localhost';
                     FLUSH PRIVILEGES;"

echo "==> 4/4  Verifying"
$SUDO mariadb -e "USE $DB_NAME;
  SELECT 'tables' AS object, COUNT(*) AS count FROM information_schema.tables  WHERE table_schema='$DB_NAME'
  UNION ALL SELECT 'routines', COUNT(*) FROM information_schema.routines WHERE routine_schema='$DB_NAME'
  UNION ALL SELECT 'triggers', COUNT(*) FROM information_schema.triggers WHERE trigger_schema='$DB_NAME'
  UNION ALL SELECT 'accounts', COUNT(*) FROM app_user;" 2>/dev/null \
  || echo "   (run as root to verify: sudo mariadb -e \"USE $DB_NAME; SHOW TABLES;\")"

echo
echo "==> Now put these two lines into backend/.env:"
echo "    DATABASE_URL=mysql+pymysql://$APP_USER:$APP_PASS@localhost:3306/$DB_NAME?charset=utf8mb4"
echo "    JWT_SECRET_KEY=borrowhub-local-dev-key-change-me-please-32"
echo
echo "==> Then start the server:"
echo "    bash run_local.sh"
