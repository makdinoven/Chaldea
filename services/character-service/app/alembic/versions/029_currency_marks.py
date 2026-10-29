"""FEAT-182 follow-up: default currency is the Middengerd mark («марки»), not gold.

Only rewrites the singleton `econ_settings` row while it still holds the old untouched
gold defaults, so a name an admin already set is kept. Downgrade restores gold only
when the row still holds the mark defaults.

Revision ID: 029_currency_marks
Revises: 028_econ_living_regions
"""

from alembic import op
import sqlalchemy as sa


revision = "029_currency_marks"
down_revision = "028_econ_living_regions"
branch_labels = None
depends_on = None


GOLD = {"name": "Золото", "genitive": "золота", "one": "золотой", "few": "золотых", "many": "золотых",
        "short": "зол."}
MARKS = {"name": "Марки", "genitive": "марок", "one": "марка", "few": "марки", "many": "марок",
         "short": "мар."}


def _swap(old: dict, new: dict) -> None:
    params = {f"old_{k}": v for k, v in old.items()}
    params.update({f"new_{k}": v for k, v in new.items()})
    op.get_bind().execute(sa.text("""
        UPDATE econ_settings
           SET currency_name = :new_name, currency_genitive = :new_genitive, currency_one = :new_one,
               currency_few = :new_few, currency_many = :new_many, currency_short = :new_short
         WHERE id = 1
           AND currency_name = :old_name AND currency_genitive = :old_genitive AND currency_one = :old_one
           AND currency_few = :old_few AND currency_many = :old_many AND currency_short = :old_short
    """), params)


def upgrade() -> None:
    _swap(GOLD, MARKS)


def downgrade() -> None:
    _swap(MARKS, GOLD)
