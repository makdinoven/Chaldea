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
