export const transformReceivedSkillTree = (skillTree) => {
  // Для "Resist:", "Vulnerability:", "Buff:" мы вырезаем тип из effect_name
  // prefix = "Resist"|"Vulnerability"|"Buff"
  const parseEffects = (effects, prefix) => {
    return effects
      .filter(e => e.effect_name.startsWith(prefix))
      .map(e => ({
        id: e.id,
        // берем всё, что после "Buff: ", "Resist: " или "Vulnerability: "
        type: e.effect_name.replace(`${prefix}: `, ''),
        percent: e.magnitude,
        duration: e.duration,
        chance: e.chance,
        description: e.description || ''
      }));
  };

  return {
    ...skillTree,
    ranks: skillTree.ranks.map(rank => ({
      ...rank,
      // Урон
      selfDamage: rank.damage_entries.filter(d => d.target_side === 'self'),
      enemyDamage: rank.damage_entries.filter(d => d.target_side === 'enemy'),

      // Резисты
      selfResist: parseEffects(rank.effects.filter(e => e.target_side === 'self'), 'Resist'),
      enemyResist: parseEffects(rank.effects.filter(e => e.target_side === 'enemy'), 'Resist'),

      // Уязвимости
      selfVulnerability: parseEffects(rank.effects.filter(e => e.target_side === 'self'), 'Vulnerability'),
      enemyVulnerability: parseEffects(rank.effects.filter(e => e.target_side === 'enemy'), 'Vulnerability'),

      // Баффы
      selfDamageBuff: parseEffects(rank.effects.filter(e => e.target_side === 'self'), 'Buff'),
      enemyDamageBuff: parseEffects(rank.effects.filter(e => e.target_side === 'enemy'), 'Buff'),

      // Остальные эффекты
      selfComplexEffects: rank.effects.filter(e =>
        e.target_side === 'self' &&
        !['Resist', 'Vulnerability', 'Buff'].some(prefix => e.effect_name.startsWith(prefix))
      ),
      enemyComplexEffects: rank.effects.filter(e =>
        e.target_side === 'enemy' &&
        !['Resist', 'Vulnerability', 'Buff'].some(prefix => e.effect_name.startsWith(prefix))
      ),
    }))
  };
};
