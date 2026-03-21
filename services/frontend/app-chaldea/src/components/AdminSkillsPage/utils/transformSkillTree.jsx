// utils/transformSkillTree.jsx
import { STAT_MODIFIERS } from "../skillConstants";

const pickDamageRows = (rows, side) =>
  rows
    .filter((d) => d.target_side === side)
    .map((d) => ({
      ...d,
      weapon_slot: d.weapon_slot || "main_weapon",
    }));

/* ---------- helpers ---------- */
const parsePrefix = (effects, side, prefix) =>
  effects
    .filter(
      (e) => e.target_side === side && e.effect_name.startsWith(prefix)
    )
    .map((e) => ({
      id: e.id,
      damage_type: e.effect_name.replace(`${prefix}: `, ""),
      percent: e.magnitude,
      duration: e.duration,
      chance: e.chance,
      description: e.description || "",
    }));

/* NEW StatModifier parser */
const parseStatMods = (effects, side) =>
  effects
    .filter(
      (e) => e.target_side === side && e.effect_name === "StatModifier"
    )
    .map((e) => ({
      id: e.id,
      key: e.attribute_key,
      amount: e.magnitude,
      duration: e.duration,
      chance: e.chance,
    }));

/* Complex‑effects без изменений */
const parseComplex = (effects, side) =>
  effects.filter(
    (e) =>
      e.target_side === side &&
      !e.effect_name.startsWith("Resist") &&
      !e.effect_name.startsWith("Buff") &&
      !e.effect_name.startsWith("Vulnerability") &&
      e.effect_name !== "StatModifier"
  );

/* ---------- main ---------- */
export const transformReceivedSkillTree = (skillTree) => ({
  ...skillTree,
  ranks: skillTree.ranks.map((rank) => {
    const { damage_entries, effects, ...rest } = rank;

    return {
      ...rest,

      /* damage */
      selfDamage: pickDamageRows(damage_entries, "self"),
      enemyDamage: pickDamageRows(damage_entries, "enemy"),

      /* resist / buff */
      selfResist: parsePrefix(effects, "self", "Resist"),
      enemyResist: parsePrefix(effects, "enemy", "Resist"),

      selfDamageBuff: parsePrefix(effects, "self", "Buff"),
      enemyDamageBuff: parsePrefix(effects, "enemy", "Buff"),

      /* vulnerability */
      selfVulnerability: parsePrefix(effects, "self", "Vulnerability"),
      enemyVulnerability: parsePrefix(effects, "enemy", "Vulnerability"),

      /* NEW stat modifiers */
      selfStatMods: parseStatMods(effects, "self"),
      enemyStatMods: parseStatMods(effects, "enemy"),

      /* complex */
      selfComplexEffects: parseComplex(effects, "self"),
      enemyComplexEffects: parseComplex(effects, "enemy"),
    };
  }),
});
