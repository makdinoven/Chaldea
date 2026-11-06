/**
 * Attribute keys with Russian labels, grouped for selects.
 * Shared by the perk editor (flat / percent bonuses) and FEAT-207 faction rank passives.
 */

export interface BonusOption {
  value: string;
  label: string;
  group?: string;
}

/** Flat & percent perk bonuses share the same attribute keys. */
export const ATTRIBUTE_BONUS_OPTIONS: BonusOption[] = [
  { value: "health", label: "Здоровье", group: "Ресурсы" },
  { value: "mana", label: "Мана", group: "Ресурсы" },
  { value: "energy", label: "Энергия", group: "Ресурсы" },
  { value: "stamina", label: "Выносливость (ресурс)", group: "Ресурсы" },
  { value: "strength", label: "Сила", group: "Основные" },
  { value: "agility", label: "Ловкость", group: "Основные" },
  { value: "intelligence", label: "Интеллект", group: "Основные" },
  { value: "endurance", label: "Живучесть", group: "Основные" },
  { value: "charisma", label: "Харизма", group: "Основные" },
  { value: "luck", label: "Удача", group: "Основные" },
  { value: "stealth", label: "Скрытность", group: "Основные" },
  { value: "damage", label: "Урон", group: "Боевые" },
  { value: "dodge", label: "Уклонение", group: "Боевые" },
  { value: "critical_hit_chance", label: "Шанс крита", group: "Боевые" },
  { value: "critical_damage", label: "Крит. урон", group: "Боевые" },
  { value: "res_physical", label: "Сопр. физическому", group: "Сопротивления" },
  { value: "res_catting", label: "Сопр. режущему", group: "Сопротивления" },
  { value: "res_crushing", label: "Сопр. дробящему", group: "Сопротивления" },
  { value: "res_piercing", label: "Сопр. колющему", group: "Сопротивления" },
  { value: "res_magic", label: "Сопр. магии", group: "Сопротивления" },
  { value: "res_fire", label: "Сопр. огню", group: "Сопротивления" },
  { value: "res_ice", label: "Сопр. льду", group: "Сопротивления" },
  { value: "res_watering", label: "Сопр. воде", group: "Сопротивления" },
  { value: "res_electricity", label: "Сопр. электричеству", group: "Сопротивления" },
  { value: "res_wind", label: "Сопр. ветру", group: "Сопротивления" },
  { value: "res_sainting", label: "Сопр. святому", group: "Сопротивления" },
  { value: "res_damning", label: "Сопр. проклятию", group: "Сопротивления" },
  { value: "res_effects", label: "Сопр. эффектам", group: "Сопротивления" },
  { value: "vul_physical", label: "Уязв. физическому", group: "Уязвимости" },
  { value: "vul_catting", label: "Уязв. режущему", group: "Уязвимости" },
  { value: "vul_crushing", label: "Уязв. дробящему", group: "Уязвимости" },
  { value: "vul_piercing", label: "Уязв. колющему", group: "Уязвимости" },
  { value: "vul_magic", label: "Уязв. магии", group: "Уязвимости" },
  { value: "vul_fire", label: "Уязв. огню", group: "Уязвимости" },
  { value: "vul_ice", label: "Уязв. льду", group: "Уязвимости" },
  { value: "vul_watering", label: "Уязв. воде", group: "Уязвимости" },
  { value: "vul_electricity", label: "Уязв. электричеству", group: "Уязвимости" },
  { value: "vul_wind", label: "Уязв. ветру", group: "Уязвимости" },
  { value: "vul_sainting", label: "Уязв. святому", group: "Уязвимости" },
  { value: "vul_damning", label: "Уязв. проклятию", group: "Уязвимости" },
  { value: "vul_effects", label: "Уязв. эффектам", group: "Уязвимости" },
];

/**
 * FEAT-207 §3.0 #4 — keys a faction rank passive may use (`faction_core.FACTION_PASSIVE_KEYS`):
 * battle keys only — no resources (a free heal each battle) and no charisma / stealth (no effect in battle).
 */
const NON_PASSIVE_KEYS = new Set(["health", "mana", "energy", "stamina", "charisma", "stealth"]);

export const FACTION_PASSIVE_OPTIONS: BonusOption[] = ATTRIBUTE_BONUS_OPTIONS.filter(
  (o) => !NON_PASSIVE_KEYS.has(o.value),
);

export const FACTION_PASSIVE_KEYS: ReadonlySet<string> = new Set(FACTION_PASSIVE_OPTIONS.map((o) => o.value));
