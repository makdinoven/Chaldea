// utils/transformSkillTree.js

export const transformReceivedSkillTree = (skillTree) => {
  const parseEffects = (effects, prefix) => effects
    .filter(e => e.effect_name.startsWith(prefix))
    .map(e => ({
      id: e.id,
      type: e.effect_name.replace(`${prefix}: `, ''),
      percent: e.magnitude,
      duration: e.duration,
      chance: e.chance,
      description: e.description || ''
    }));

  return {
    ...skillTree,
    ranks: skillTree.ranks.map(rank => ({
      ...rank,
      selfDamage: rank.damage_entries.filter(e => e.target_side === 'self'),
      enemyDamage: rank.damage_entries.filter(e => e.target_side === 'enemy'),
      selfResist: parseEffects(rank.effects.filter(e => e.target_side === 'self'), 'Resist'),
      enemyResist: parseEffects(rank.effects.filter(e => e.target_side === 'enemy'), 'Resist'),
      selfVulnerability: parseEffects(rank.effects.filter(e => e.target_side === 'self'), 'Vulnerability'),
      enemyVulnerability: parseEffects(rank.effects.filter(e => e.target_side === 'enemy'), 'Vulnerability'),
      selfDamageBuff: parseEffects(rank.effects.filter(e => e.target_side === 'self'), 'Buff'),
      enemyDamageBuff: parseEffects(rank.effects.filter(e => e.target_side === 'enemy'), 'Buff'),
      selfComplexEffects: rank.effects.filter(e => e.target_side === 'self' && !['Resist', 'Vulnerability', 'Buff'].some(prefix => e.effect_name.startsWith(prefix))),
      enemyComplexEffects: rank.effects.filter(e => e.target_side === 'enemy' && !['Resist', 'Vulnerability', 'Buff'].some(prefix => e.effect_name.startsWith(prefix))),
    }))
  };
};
