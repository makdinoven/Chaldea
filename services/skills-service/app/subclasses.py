"""
Hardcoded subclass registry — single source of truth for class subclasses.

A subclass_choice tree node and a subclass tree both reference a subclass by its
stable ``key`` (never change a key once shipped — it is the link, see
``docs/SUBCLASS-PASSIVES.md``). Names/descriptions live here so the player tree
can show a preview straight from the registry, and the admin editor can offer a
dropdown instead of free-text name matching.

Passives (FEAT-188): every subclass carries exactly one ``PassiveDef`` — a stable
``key`` (battle-service matches on it, never rename once shipped), the player-facing
Russian name/description, and ``implemented`` (True only when battle-service actually
applies the effect; the UI shows the others with a "not active in battle yet" note).
Live since FEAT-189: 14 passives — berserker_rage (FEAT-188) + the 13 "existing
mechanics" passives of wave 1. FEAT-190 (wave 2, new battle mechanics: shields,
lifesteal, reflect, HP payment, passive-sourced ally buffs, redirect) made the
remaining 7 live — all 21 passives are ``implemented=True`` now. battle-service
mirrors this set in ``passives.IMPLEMENTED_PASSIVES`` — flip both together.

The NUMBERS of a passive's effect live in ``services/battle-service/app/passives.py``.
The descriptions here quote those numbers — change a constant there, update the
description here (and ``docs/SUBCLASS-PASSIVES.md``).
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class PassiveDef:
    key: str
    name: str
    description: str
    implemented: bool = False


@dataclass(frozen=True)
class SubclassDef:
    key: str
    class_id: int
    name: str
    description: str
    passive: PassiveDef


# class_id: 1 = Воин, 2 = Плут, 3 = Маг
SUBCLASSES: List[SubclassDef] = [
    # --- Воин (class_id=1) ---
    SubclassDef(
        key="warrior_inquisitor", class_id=1, name="Инквизитор",
        description=(
            "Воин-полумаг и ненавистник магии. Сам владеет магией и снижает магам "
            "сопротивление к ней, чтобы бить их же оружием. Подкласс-антимаг."
        ),
        passive=PassiveDef(
            key="inquisitor_heresy_seal", name="Печать ереси", implemented=True,
            description=(
                "Каждое попадание по врагу, который в этом бою применял магию, снижает "
                "все его не-физические сопротивления (магия, стихии, святость, проклятие) "
                "на 3%, до 5 стаков (−15%), до конца боя. Снижение работает и для "
                "союзников Инквизитора."
            ),
        ),
    ),
    SubclassDef(
        key="warrior_paladin", class_id=1, name="Паладин",
        description=(
            "Воин-полумаг светлого пути. Сочетает святые техники и физическую мощь "
            "воина."
        ),
        passive=PassiveDef(
            key="paladin_sacred_vow", name="Священный обет", implemented=True,
            description=(
                "Один раз за бой при падении здоровья ниже 30%: щит на 20% макс. здоровья "
                "(держится до конца боя или пока не пробит) и снятие самого свежего "
                "снимаемого негативного эффекта (оглушение и паралич не снимаются ничем)."
            ),
        ),
    ),
    SubclassDef(
        key="warrior_saber", class_id=1, name="Сейбер",
        description=(
            "Классический воин с двуручным оружием: сильные приёмы и хорошая защита, "
            "но узкая специализация. Удобен для зачистки мобов."
        ),
        passive=PassiveDef(
            key="saber_monster_hunter", name="Охотник на чудовищ", implemented=True,
            description=(
                "По мобам +15% урона; каждое убийство в подземелье даёт +2% урона до "
                "конца забега, максимум +10%. Несгибаемость (PvP): каждый пропущенный "
                "удар даёт +2% ко всем сопротивлениям, максимум 3 стака (+6%)."
            ),
        ),
    ),
    SubclassDef(
        key="warrior_guardian", class_id=1, name="Хранитель",
        description=(
            "Центральный танк воина: умеренный урон и высокая живучесть. Защитник, "
            "который держит удар за всю команду."
        ),
        passive=PassiveDef(
            key="guardian_retribution", name="Возмездие", implemented=True,
            description=(
                "15% полученного урона (после сопротивлений) возвращается атакующему. "
                "Отражённый урон не критует, от него не уклониться, и он сам не "
                "отражается."
            ),
        ),
    ),
    SubclassDef(
        key="warrior_gladiator", class_id=1, name="Гладиатор",
        description=(
            "Универсальный воин, расцветающий в тяжёлом бою: чем сильнее враг или чем "
            "больше противников — тем опаснее он сам."
        ),
        passive=PassiveDef(
            key="gladiator_arena", name="Арена", implemented=True,
            description=(
                "За каждого врага сверх числа союзников: +8% урона и +4% сопротивлений, "
                "максимум 3. Если Гладиатор не в меньшинстве: +3% урона за каждый свой "
                "ход, максимум +15%."
            ),
        ),
    ),
    SubclassDef(
        key="warrior_berserker", class_id=1, name="Берсерк",
        description=(
            "Самый дамажный и самый хрупкий подкласс воина. Превращает собственную "
            "боль в ярость и сокрушительный урон."
        ),
        passive=PassiveDef(
            key="berserker_rage", name="Ярость", implemented=True,
            description=(
                "Боль превращается в ярость: +4% к урону за каждые полные 10% потерянного "
                "здоровья (до +36%). Ниже 25% здоровья — вампиризм: 15% нанесённого урона "
                "лечит Берсерка."
            ),
        ),
    ),
    SubclassDef(
        key="warrior_agent", class_id=1, name="Агент",
        description=(
            "Воин-полуплут: лёгкий и проворный, делает ставку на эффекты и "
            "критические удары."
        ),
        passive=PassiveDef(
            key="agent_weak_spot", name="Слабое место", implemented=True,
            description=(
                "При критическом ударе: +20 п.п. к шансу наложить эффекты навыка; для "
                "оглушения и паралича — только +10 п.п."
            ),
        ),
    ),

    # --- Плут (class_id=2) ---
    SubclassDef(
        key="rogue_lancer", class_id=2, name="Лансер",
        description=(
            "Плут с копьём, антиплут. Лишает врага уклонений и критов, одновременно "
            "усиливая в этом себя."
        ),
        passive=PassiveDef(
            key="lancer_pin", name="Пригвоздить", implemented=True,
            description=(
                "Каждое попадание крадёт у цели 2% уклонения и 2 п.п. шанса крита себе, "
                "до 5 стаков (±10), до конца боя. Ниже нуля значения цели не уходят — "
                "крадётся только то, что есть."
            ),
        ),
    ),
    SubclassDef(
        key="rogue_mechanic", class_id=2, name="Механик",
        description=(
            "Единственный подкласс с механическим оружием. Его шрапнель рикошетит, "
            "задевая несколько целей разом."
        ),
        passive=PassiveDef(
            key="mechanic_shrapnel", name="Шрапнель", implemented=True,
            description=(
                "С шансом 30% удар задевает ещё одного случайного врага на 40% урона (со "
                "своим броском уклонения). Если других врагов нет: с шансом 30% — +35% "
                "урона той же цели."
            ),
        ),
    ),
    SubclassDef(
        key="rogue_archer", class_id=2, name="Арчер",
        description=(
            "Классический лучник: хрупкий, но выдаёт много урона и критов на "
            "дистанции."
        ),
        passive=PassiveDef(
            key="archer_first_blood", name="Первая кровь", implemented=True,
            description=(
                "Первый удар по каждой цели в бою — гарантированный крит с +50% к "
                "критическому урону (×1.75 вместо ×1.25)."
            ),
        ),
    ),
    SubclassDef(
        key="rogue_assassin", class_id=2, name="Ассасин",
        description=(
            "Центральный подкласс плута: высокий урон и уклонение, но защита слабее "
            "даже лучника."
        ),
        passive=PassiveDef(
            key="assassin_from_shadow", name="Из тени", implemented=True,
            description=(
                "После успешного уклонения следующая атака — гарантированный крит с +25% "
                "к критическому урону. Добивание: по целям ниже 30% здоровья — +20% "
                "урона."
            ),
        ),
    ),
    SubclassDef(
        key="rogue_bard", class_id=2, name="Бард",
        description=(
            "Полусаппорт: вдохновляет и усиливает союзников и себя боевыми мотивами."
        ),
        passive=PassiveDef(
            key="bard_rhythm", name="Ритм", implemented=True,
            description=(
                "Каждый свой ход — стак «Вдохновения» себе и союзникам: +3% урона, "
                "максимум 4 (+12%). Если Бард пал, стаки исчезают. Если союзников нет — "
                "только себе: +5%, максимум 3 (+15%)."
            ),
        ),
    ),
    SubclassDef(
        key="rogue_trickster", class_id=2, name="Фокусник",
        description=(
            "Противоположность барду: своими трюками сбивает врагов с толку и "
            "осыпает их дебафами."
        ),
        passive=PassiveDef(
            key="trickster_deceit", name="Обман", implemented=True,
            description=(
                "С шансом 10% атака по Фокуснику не проходит; в групповом бою она уходит в "
                "случайного союзника атакующего с 50% урона. Дебафы Фокусника держатся "
                "на 1 ход дольше (кроме оглушения и паралича)."
            ),
        ),
    ),
    SubclassDef(
        key="rogue_monk", class_id=2, name="Монах",
        description=(
            "Плут-полумаг, превращающий собственное тело в оружие. Силён в защите и "
            "контроле противника."
        ),
        passive=PassiveDef(
            key="monk_harmony", name="Гармония", implemented=True,
            description=(
                "+10 п.п. к шансу наложить контроль (оглушение и паралич — +5 п.п.). "
                "Первый контроль на Монаха в бою не срабатывает."
            ),
        ),
    ),

    # --- Маг (class_id=3) ---
    SubclassDef(
        key="mage_necromancer", class_id=3, name="Некромант",
        description=(
            "Призыватель тьмы и мастер проклятий. Жертвует своим здоровьем ради "
            "усилений и мерзких дебафов."
        ),
        passive=PassiveDef(
            key="necromancer_blood_price", name="Плата кровью", implemented=True,
            description=(
                "Нехватку маны на навык доплачивает здоровьем: 1 маны = 1.5 здоровья. "
                "Убить себя нельзя — если здоровья не хватает, ход срывается, как при "
                "нехватке маны. За убийство в бою — лечение на 10% макс. "
                "здоровья."
            ),
        ),
    ),
    SubclassDef(
        key="mage_etheriad", class_id=3, name="Эфириад",
        description=(
            "Маг святых духов: бафает, дебафает и разит светлой магией."
        ),
        passive=PassiveDef(
            key="etheriad_spirit_whisper", name="Шёпот духов", implemented=True,
            description=(
                "Каждый свой ход духи выбирают по приоритету: союзник ниже 50% здоровья "
                "(самый побитый) получает +8% сопротивлений; иначе враг без дебафа духов "
                "(по которому бил Эфириад) получает −8% сопротивлений; иначе союзник "
                "получает +8% урона. Эффект длится 2 хода. Если союзников нет, "
                "союзник — сам Эфириад."
            ),
        ),
    ),
    SubclassDef(
        key="mage_salamander", class_id=3, name="Саламандр",
        description=(
            "Маг, рождённый чистой яростью огня."
        ),
        passive=PassiveDef(
            key="salamander_kindling", name="Разгорание", implemented=True,
            description=(
                "Каждый огненный удар подряд по одной цели — +6% урона, до 5 стаков "
                "(+30%); сброс при смене цели или не-огненной атаке. Ожоги Саламандра "
                "держатся на 1 ход дольше."
            ),
        ),
    ),
    SubclassDef(
        key="mage_caster", class_id=3, name="Кастер",
        description=(
            "Центральный маг дерева: чистая энергия магии и познание её природы. "
            "Считает стихийную ересь второсортной."
        ),
        passive=PassiveDef(
            key="caster_pure_energy", name="Чистая энергия", implemented=True,
            description=(
                "Чистый магический урон (не стихийный) игнорирует 25% сопротивления цели "
                "(30% → 22.5%). Все навыки на 10% дешевле по мане."
            ),
        ),
    ),
    SubclassDef(
        key="mage_sparkmage", class_id=3, name="Искромаг",
        description=(
            "Повелитель молний и ветра. Средний по урону, но универсальный."
        ),
        passive=PassiveDef(
            key="sparkmage_chain_lightning", name="Цепная молния", implemented=True,
            description=(
                "Урон электричеством или ветром с шансом 25% перескакивает на другого "
                "врага на 50%. Если других врагов нет: с шансом 25% — повторный удар по "
                "той же цели на 40%."
            ),
        ),
    ),
    SubclassDef(
        key="mage_auromancer", class_id=3, name="Ауромант",
        description=(
            "Его конёк — вода и поддержка союзников: лечит, спасает и выручает "
            "команду."
        ),
        passive=PassiveDef(
            key="auromancer_tide", name="Прилив", implemented=True,
            description=(
                "Лечение сверх максимума здоровья становится щитом, до 20% макс. здоровья "
                "цели, на 3 хода. Если союзников нет — от лечения самого себя."
            ),
        ),
    ),
    SubclassDef(
        key="mage_priest", class_id=3, name="Жрец",
        description=(
            "Маг-полувоин: очень живуч, хорошо бьёт, немного лечит и защищает себя. "
            "Узконаправлен на святость."
        ),
        passive=PassiveDef(
            key="priest_faith", name="Вера", implemented=True,
            description=(
                "10% нанесённого урона лечит Жреца, святым уроном — 15%."
            ),
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


def get_passive_for_subclass(key: Optional[str]) -> Optional[PassiveDef]:
    subclass = get_subclass(key)
    return subclass.passive if subclass else None
