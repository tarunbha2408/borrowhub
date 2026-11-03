"""Initial BorrowHub relational schema migration.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-10-31 15:30:00.000000

Important
---------
The authoritative schema of this project is ``database/schema.sql``. It holds
the tables, 30 triggers, 27 stored procedures, 6 functions, 7 views and the
seed-independent configuration rows, none of which a Python migration can
reproduce faithfully.

This revision therefore only records that the baseline exists, so that a later
``alembic revision`` has a parent to hang off. ``alembic upgrade head`` on an
empty database must be preceded by::

    mysql -u root -p < database/schema.sql
    mysql -u root -p borrowhub < database/seed.sql
"""
from typing import Sequence, Union

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Baseline marker: the real schema is loaded from database/schema.sql."""


def downgrade() -> None:
    """Nothing to undo: the baseline is the SQL file."""
