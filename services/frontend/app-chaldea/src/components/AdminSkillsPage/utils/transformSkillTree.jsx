// src/utils/transformSkillTree.js

// Преобразуем данные, полученные с бэкенда,
// чтобы для каждого ранга создать поля selfDamage и enemyDamage, основанные на damage_entries.
export const transformReceivedSkillTree = (skillTree) => {
  return {
    ...skillTree,
    ranks: skillTree.ranks.map(rank => ({
      ...rank,
      // Разбиваем damage_entries по target_side
      selfDamage: rank.damage_entries.filter(entry => entry.target_side === 'self'),
      enemyDamage: rank.damage_entries.filter(entry => entry.target_side === 'enemy')
    }))
  };
};
