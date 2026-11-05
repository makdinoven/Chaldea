# Base stat values for derived stat calculations.
# Used by upgrade and recalculate logic.

BASE_HEALTH = 100
BASE_MANA = 75
BASE_ENERGY = 50
BASE_STAMINA = 100
BASE_DODGE = 5.0
BASE_CRIT = 20.0
BASE_CRIT_DMG = 125

# Multipliers for resource stats (points -> max value)
HEALTH_MULTIPLIER = 10
MANA_MULTIPLIER = 10
ENERGY_MULTIPLIER = 5
STAMINA_MULTIPLIER = 5

# Per-point bonus for combat/resistance stats
STAT_BONUS_PER_POINT = 0.1

# Per-point bonus for endurance -> res_effects
ENDURANCE_RES_EFFECTS_MULTIPLIER = 0.2

# Physical resistance fields (boosted by Strength)
PHYSICAL_RESISTANCE_FIELDS = [
    "res_physical",
    "res_catting",
    "res_crushing",
    "res_piercing",
]

# Magical resistance fields (boosted by Intelligence)
MAGICAL_RESISTANCE_FIELDS = [
    "res_magic",
    "res_fire",
    "res_ice",
    "res_watering",
    "res_electricity",
    "res_wind",
    "res_sainting",
    "res_damning",
]

# All resistance fields (union of physical + magical + effects)
ALL_RESISTANCE_FIELDS = (
    PHYSICAL_RESISTANCE_FIELDS
    + MAGICAL_RESISTANCE_FIELDS
    + ["res_effects"]
)

# Per-point bonuses of agility / luck (luck feeds three derived fields)
AGILITY_DODGE_MULTIPLIER = STAT_BONUS_PER_POINT
LUCK_DODGE_MULTIPLIER = STAT_BONUS_PER_POINT
LUCK_CRIT_MULTIPLIER = STAT_BONUS_PER_POINT
LUCK_RES_EFFECTS_MULTIPLIER = STAT_BONUS_PER_POINT

# FEAT-195: what one EFFECTIVE point (stat_caps.effective_stat of the total) of a
# primary attribute adds to the stored derived fields. Charisma has no stored
# derived field (merchant discount is computed in econ_core).
PRIMARY_DERIVED_EFFECTS = {
    "strength": {field: STAT_BONUS_PER_POINT for field in PHYSICAL_RESISTANCE_FIELDS},
    "intelligence": {field: STAT_BONUS_PER_POINT for field in MAGICAL_RESISTANCE_FIELDS},
    "agility": {"dodge": AGILITY_DODGE_MULTIPLIER},
    "endurance": {"res_effects": ENDURANCE_RES_EFFECTS_MULTIPLIER},
    "luck": {
        "dodge": LUCK_DODGE_MULTIPLIER,
        "critical_hit_chance": LUCK_CRIT_MULTIPLIER,
        "res_effects": LUCK_RES_EFFECTS_MULTIPLIER,
    },
}
# FEAT-201: stealth, like charisma, has no stored derived field (it only lowers
# the chance a crime is witnessed; computed in character-service).
PRIMARY_ATTRIBUTE_KEYS = (
    "strength", "agility", "intelligence", "endurance", "charisma", "luck", "stealth",
)

# Resource stat -> (base max, multiplier): max_R = BASE_R + floor(m_R * eff(R))
RESOURCE_STATS = {
    "health": (BASE_HEALTH, HEALTH_MULTIPLIER),
    "mana": (BASE_MANA, MANA_MULTIPLIER),
    "energy": (BASE_ENERGY, ENERGY_MULTIPLIER),
    "stamina": (BASE_STAMINA, STAMINA_MULTIPLIER),
}

# FEAT-196: per-level growth of resource maximums, by class (subclass ignored).
# max_R += level * rate(class, R); outside the FEAT-195 cap (not a stat).
# Mirrored on the frontend in src/utils/resourceGrowth.ts.
MAIN_RESOURCE_PER_LEVEL = 15
OTHER_RESOURCE_PER_LEVEL = 10
CLASS_MAIN_RESOURCE = {1: "health", 2: "energy", 3: "mana"}  # warrior, rogue, mage
LEVEL_RESOURCE_GROWTH = {
    class_id: {
        resource: (MAIN_RESOURCE_PER_LEVEL if resource == main else OTHER_RESOURCE_PER_LEVEL)
        for resource in RESOURCE_STATS
    }
    for class_id, main in CLASS_MAIN_RESOURCE.items()
}

# Fields a modifier adds as-is (no derived propagation of their own)
FLAT_MODIFIER_KEYS = (
    "damage", "dodge", "res_effects",
    "res_physical", "res_catting", "res_crushing", "res_piercing",
    "res_magic", "res_fire", "res_ice", "res_watering",
    "res_electricity", "res_wind", "res_sainting", "res_damning",
    "critical_hit_chance", "critical_damage",
    "vul_effects", "vul_physical", "vul_catting", "vul_crushing", "vul_piercing",
    "vul_magic", "vul_fire", "vul_ice", "vul_watering",
    "vul_electricity", "vul_sainting", "vul_wind", "vul_damning",
)

# Derived fields a rebuild re-creates from flat sources + eff(primary)
DERIVED_FLAT_KEYS = ALL_RESISTANCE_FIELDS + ["dodge", "critical_hit_chance"]

# Mapping of class_id to main attribute name for damage calculation.
# Must stay in sync with battle-service/app/battle_engine.py CLASS_MAIN_ATTRIBUTE.
CLASS_MAIN_ATTRIBUTE = {1: "strength", 2: "agility", 3: "intelligence"}

# FEAT-164: passive regen in rest + satiety (food effect)
REGEN_PERCENT_PER_HOUR = 5.0            # % of max per real hour, all 4 resources
SATIETY_DURATION_HOURS = 24
# FEAT-180 6a: a house kitchen makes food last longer; the caller sends the hours within these bounds.
SATIETY_MIN_DURATION_HOURS = 1
SATIETY_MAX_DURATION_HOURS = 72
# Regen bonus by food rarity (fraction: 0.5 = +50%). Food is capped at legendary.
SATIETY_REGEN_BONUS_BY_RARITY = {"common": 0.5, "rare": 1.0, "epic": 1.5, "legendary": 2.0}
REGEN_RESOURCES = ("health", "mana", "energy", "stamina")
