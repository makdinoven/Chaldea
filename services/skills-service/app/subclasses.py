"""
Hardcoded subclass registry — single source of truth for class subclasses.

A subclass_choice tree node and a subclass tree both reference a subclass by its
stable ``key`` (never change a key once shipped — it is the link, see
``docs/SUBCLASS-PASSIVES.md``). Names/descriptions live here so the player tree
can show a preview straight from the registry, and the admin editor can offer a
dropdown instead of free-text name matching.

Passives are intentionally NOT modeled yet — they wait on the combat-system work
(targeting, group battles, control). See docs/SUBCLASS-PASSIVES.md.
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class SubclassDef:
    key: str
    class_id: int
    name: str
    description: str


# class_id: 1 = Воин, 2 = Плут, 3 = Маг
SUBCLASSES: List[SubclassDef] = [
    # --- Воин (class_id=1) ---
    SubclassDef(
        key="warrior_inquisitor", class_id=1, name="Инквизитор",
        description=(
            "Воин-полумаг и ненавистник магии. Сам владеет магией и снижает магам "
            "сопротивление к ней, чтобы бить их же оружием. Подкласс-антимаг."
        ),
    ),
    SubclassDef(
        key="warrior_paladin", class_id=1, name="Паладин",
        description=(
            "Воин-полумаг светлого пути. Сочетает святые техники и физическую мощь "
            "воина."
        ),
    ),
    SubclassDef(
        key="warrior_saber", class_id=1, name="Сейбер",
        description=(
            "Классический воин с двуручным оружием: сильные приёмы и хорошая защита, "
            "но узкая специализация. Удобен для зачистки мобов."
        ),
    ),
    SubclassDef(
        key="warrior_guardian", class_id=1, name="Хранитель",
        description=(
            "Центральный танк воина: умеренный урон и высокая живучесть. Защитник, "
            "который держит удар за всю команду."
        ),
    ),
    SubclassDef(
        key="warrior_gladiator", class_id=1, name="Гладиатор",
        description=(
            "Универсальный воин, расцветающий в тяжёлом бою: чем сильнее враг или чем "
            "больше противников — тем опаснее он сам."
        ),
    ),
    SubclassDef(
        key="warrior_berserker", class_id=1, name="Берсерк",
        description=(
            "Самый дамажный и самый хрупкий подкласс воина. Превращает собственную "
            "боль в ярость и сокрушительный урон."
        ),
    ),
    SubclassDef(
        key="warrior_agent", class_id=1, name="Агент",
        description=(
            "Воин-полуплут: лёгкий и проворный, делает ставку на эффекты и "
            "критические удары."
        ),
    ),

    # --- Плут (class_id=2) ---
    SubclassDef(
        key="rogue_lancer", class_id=2, name="Лансер",
        description=(
            "Плут с копьём, антиплут. Лишает врага уклонений и критов, одновременно "
            "усиливая в этом себя."
        ),
    ),
    SubclassDef(
        key="rogue_mechanic", class_id=2, name="Механик",
        description=(
            "Единственный подкласс с механическим оружием. Его шрапнель рикошетит, "
            "задевая несколько целей разом."
        ),
    ),
    SubclassDef(
        key="rogue_archer", class_id=2, name="Арчер",
        description=(
            "Классический лучник: хрупкий, но выдаёт много урона и критов на "
            "дистанции."
        ),
    ),
    SubclassDef(
        key="rogue_assassin", class_id=2, name="Ассасин",
        description=(
            "Центральный подкласс плута: высокий урон и уклонение, но защита слабее "
            "даже лучника."
        ),
    ),
    SubclassDef(
        key="rogue_bard", class_id=2, name="Бард",
        description=(
            "Полусаппорт: вдохновляет и усиливает союзников и себя боевыми мотивами."
        ),
    ),
    SubclassDef(
        key="rogue_trickster", class_id=2, name="Фокусник",
        description=(
            "Противоположность барду: своими трюками сбивает врагов с толку и "
            "осыпает их дебафами."
        ),
    ),
    SubclassDef(
        key="rogue_monk", class_id=2, name="Монах",
        description=(
            "Плут-полумаг, превращающий собственное тело в оружие. Силён в защите и "
            "контроле противника."
        ),
    ),

    # --- Маг (class_id=3) ---
    SubclassDef(
        key="mage_necromancer", class_id=3, name="Некромант",
        description=(
            "Призыватель тьмы и мастер проклятий. Жертвует своим здоровьем ради "
            "усилений и мерзких дебафов."
        ),
    ),
    SubclassDef(
        key="mage_etheriad", class_id=3, name="Эфириад",
        description=(
            "Маг святых духов: бафает, дебафает и разит светлой магией."
        ),
    ),
    SubclassDef(
        key="mage_salamander", class_id=3, name="Саламандр",
        description=(
            "Маг, рождённый чистой яростью огня."
        ),
    ),
    SubclassDef(
        key="mage_caster", class_id=3, name="Кастер",
        description=(
            "Центральный маг дерева: чистая энергия магии и познание её природы. "
            "Считает стихийную ересь второсортной."
        ),
    ),
    SubclassDef(
        key="mage_sparkmage", class_id=3, name="Искромаг",
        description=(
            "Повелитель молний и ветра. Средний по урону, но универсальный."
        ),
    ),
    SubclassDef(
        key="mage_auromancer", class_id=3, name="Ауромант",
        description=(
            "Его конёк — вода и поддержка союзников: лечит, спасает и выручает "
            "команду."
        ),
    ),
    SubclassDef(
        key="mage_priest", class_id=3, name="Жрец",
        description=(
            "Маг-полувоин: очень живуч, хорошо бьёт, немного лечит и защищает себя. "
            "Узконаправлен на святость."
        ),
    ),
]

SUBCLASSES_BY_KEY = {s.key: s for s in SUBCLASSES}


def subclasses_for_class(class_id: int) -> List[SubclassDef]:
    return [s for s in SUBCLASSES if s.class_id == class_id]


def get_subclass(key: Optional[str]) -> Optional[SubclassDef]:
    if not key:
        return None
    return SUBCLASSES_BY_KEY.get(key)
