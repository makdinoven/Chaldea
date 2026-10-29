"""Currency abbreviation: «ṃ» instead of «мар.».

Only rewrites the singleton `econ_settings` row while it still holds the untouched «мар.» from
029, so an abbreviation an admin already set is kept. Downgrade restores «мар.» only when the row
still holds «ṃ».

Revision ID: 030_currency_short_mark
Revises: 029_currency_marks
"""

from alembic import op
import sqlalchemy as sa


revision = "030_currency_short_mark"
down_revision = "029_currency_marks"
branch_labels = None
depends_on = None


def _swap(old: str, new: str) -> None:
    op.get_bind().execute(
        sa.text("UPDATE econ_settings SET currency_short = :new WHERE id = 1 AND currency_short = :old"),
        {"old": old, "new": new},
    )


def upgrade() -> None:
    _swap("мар.", "ṃ")


def downgrade() -> None:
    _swap("ṃ", "мар.")
