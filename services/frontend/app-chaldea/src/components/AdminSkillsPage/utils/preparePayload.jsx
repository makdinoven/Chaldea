// utils/preparePayload.js
/* ---------- damage ---------- */
export const transformDamageData = (selfDamage = [], enemyDamage = []) => {
  const map = (item, side) => ({
    damage_type: item.damage_type,
    amount: item.amount,
    chance: item.chance,
    description: item.description || "",
    target_side: side,
    weapon_slot: item.weapon_slot || "main_weapon",
  });
  return [
    ...selfDamage.map((i) => map(i, "self")),
    ...enemyDamage.map((i) => map(i, "enemy")),
  ];
};

/* ---------- helpers ---------- */
const makeEffectRow = ({
  id = null,
  target_side,
  effect_name,
  magnitude,
  duration,
  chance,
  attribute_key = null,
  description = "",
}) => ({
  id,
  target_side,
  effect_name,
  description,
  chance,
  duration,
  magnitude,
  attribute_key,
});

/* Buff / Resist */
const transformBuff = (arr = [], side = "self") =>
  arr.map((i) =>
    makeEffectRow({
      id: i.id,
      target_side: side,
      effect_name: `Buff: ${i.damage_type}`,
      magnitude: i.percent,
      duration: i.duration,
      chance: i.chance,
    })
  );

const transformResist = (arr = [], side = "self") =>
  arr.map((i) =>
    makeEffectRow({
      id: i.id,
      target_side: side,
      effect_name: `Resist: ${i.damage_type}`,
      magnitude: i.percent,
      duration: i.duration,
      chance: i.chance,
    })
  );

/* ---------- Stat Modifiers ---------- */
const transformStatMods = (arr = [], side = "self") =>
  arr.map((i) =>
    makeEffectRow({
      id: i.id,
      target_side: side,
      effect_name: "StatModifier",
      attribute_key: i.key,
      magnitude: i.amount,
      duration: i.duration,
      chance: i.chance,
    })
  );

/* ---------- complex ---------- */
const transformComplex = (arr = [], side = "self") =>
  arr.map((i) => ({ ...i, target_side: side }));

/* ---------- rank ---------- */
export const prepareRankPayload = (rankData) => {
  const {
    selfDamage = [],
    enemyDamage = [],

    selfDamageBuff = [],
    enemyDamageBuff = [],

    selfResist = [],
    enemyResist = [],

    selfStatMods = [],
    enemyStatMods = [],

    selfComplexEffects = [],
    enemyComplexEffects = [],

    ...base
  } = rankData;

  const effects = [
    ...transformBuff(selfDamageBuff, "self"),
    ...transformBuff(enemyDamageBuff, "enemy"),
    ...transformResist(selfResist, "self"),
    ...transformResist(enemyResist, "enemy"),
    ...transformStatMods(selfStatMods, "self"),
    ...transformStatMods(enemyStatMods, "enemy"),
    ...transformComplex(selfComplexEffects, "self"),
    ...transformComplex(enemyComplexEffects, "enemy"),
  ];

  return {
    ...base,
    damage_entries: transformDamageData(selfDamage, enemyDamage),
    effects,
  };
};

/* ---------- skill‑tree ---------- */
export const prepareSkillPayload = (skillTree) => {
  const { ranks, ...skill } = skillTree;
  return {
    ...skill,
    ranks: ranks.map((r) => prepareRankPayload(r)),
  };
};
