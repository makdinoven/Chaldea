"""Lore template populations (×100) and «Регион» wording of the templates.

FEAT-186: `econ_regions.population` / `econ_region_templates.default_population` hold the lore number; the
simulation divides it by `population_scale` (a key of `econ_sim_settings.params`, missing = 100).

`econ_regions.population` and `econ_region_history` are NOT touched: on prod the admin already typed lore numbers
(120 000 … 4 000 000). Existing regions are brought to the new scale by the admin through «Заполнить регионы по
шаблонам» with `return_purse_excess` / `return_treasury_excess` (a ledger operation, not a migration).

Template rows are rewritten field by field only while a field still holds its 028 default (an admin edit is kept):
default_population ×100, name → «… регион», description → region-flavoured text, settlement_noun / noun_gender →
«Регион» / m. Downgrade restores the 028 values where a field still holds the 032 value.

Revision ID: 032_econ_population_scale
Revises: 031_econ_banks
"""

from alembic import op
import sqlalchemy as sa


revision = "032_econ_population_scale"
down_revision = "031_econ_banks"
branch_labels = None
depends_on = None

POPULATION_FACTOR = 100

# 028 default_population per template (the 032 value is x POPULATION_FACTOR)
DEFAULT_POPULATIONS = {"capital": 25000, "port": 12000, "mining": 6000, "agrarian": 8000, "forest": 4000,
                       "magic": 7000, "fortress": 3000, "rural": 2500}

# code -> ((028 name, description, noun, gender), (032 name, description, noun, gender))
TEMPLATE_TEXTS = {
    "capital": (
        ("Столица", "Крупный город: ремёсла и роскошь, сырьё привозное.", "Город", "m"),
        ("Столичный регион", "Сердце страны: ремёсла и роскошь, сырьё привозное.", "Регион", "m"),
    ),
    "port": (
        ("Портовый", "Портовый город: рыба, ткани, шкуры; умеренное ремесло.", "Порт", "m"),
        ("Портовый регион", "Побережье и гавани: рыба, ткани, шкуры; умеренное ремесло.", "Регион", "m"),
    ),
    "mining": (
        ("Шахтёрский", "Горное поселение: много руды и инструментов, мало трав и еды.", "Город", "m"),
        ("Шахтёрский регион", "Горы и рудники: много руды и инструментов, мало трав и еды.", "Регион", "m"),
    ),
    "agrarian": (
        ("Аграрный", "Земледельческий край: житница с избытком продовольствия.", "Край", "m"),
        ("Аграрный регион", "Пашни и пастбища — житница с избытком продовольствия.", "Регион", "m"),
    ),
    "forest": (
        ("Лесной", "Лесной край: древесина, травы, шкуры и мебель.", "Край", "m"),
        ("Лесной регион", "Леса и чащи: древесина, травы, шкуры и мебель.", "Регион", "m"),
    ),
    "magic": (
        ("Магический", "Город магов: магические материалы и зелья, нужда в травах.", "Город", "m"),
        ("Магический регион", "Земли магов: магические материалы и зелья, нужда в травах.", "Регион", "m"),
    ),
    "fortress": (
        ("Пограничная крепость", "Гарнизон на границе: оружие и броня, своей еды не хватает.", "Крепость", "f"),
        ("Пограничный регион", "Пограничье с гарнизонами: оружие и броня, своей еды не хватает.", "Регион", "m"),
    ),
    "rural": (
        ("Сельская округа", "Мелкие деревни — поставщики сырья и еды.", "Округа", "f"),
        ("Сельский регион", "Деревни и хутора — поставщики сырья и еды.", "Регион", "m"),
    ),
}


def _scale_template_populations(multiply: bool) -> None:
    """Template default_population 028 value <-> x100, only where the field still holds the source value."""
    bind = op.get_bind()
    for code, old in DEFAULT_POPULATIONS.items():
        new = old * POPULATION_FACTOR
        src, dst = (old, new) if multiply else (new, old)
        bind.execute(sa.text("UPDATE econ_region_templates SET default_population = :dst "
                             "WHERE code = :code AND default_population = :src"),
                     {"code": code, "src": src, "dst": dst})


def _rewrite_texts(src: int, dst: int) -> None:
    """Per field: set the ``dst`` text where the field still holds the ``src`` text (0 = 028, 1 = 032)."""
    bind = op.get_bind()
    for code, variants in TEMPLATE_TEXTS.items():
        old, new = variants[src], variants[dst]
        for col, i in (("name", 0), ("description", 1)):
            bind.execute(sa.text(f"UPDATE econ_region_templates SET {col} = :new WHERE code = :code AND {col} = :old"),
                         {"code": code, "old": old[i], "new": new[i]})
        bind.execute(sa.text(
            "UPDATE econ_region_templates SET settlement_noun = :noun, noun_gender = :gender "
            "WHERE code = :code AND settlement_noun = :old_noun AND noun_gender = :old_gender"
        ), {"code": code, "noun": new[2], "gender": new[3], "old_noun": old[2], "old_gender": old[3]})


def upgrade() -> None:
    _scale_template_populations(multiply=True)
    _rewrite_texts(0, 1)


def downgrade() -> None:
    _scale_template_populations(multiply=False)
    _rewrite_texts(1, 0)
