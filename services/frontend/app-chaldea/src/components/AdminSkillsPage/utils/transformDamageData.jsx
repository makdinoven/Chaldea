// src/utils/transformDamageData.js
const transformDamageData = (selfDamage = [], enemyDamage = []) => {
  const self = selfDamage.map(item => ({
    damage_type: item.damage_type || item.type, // если где-то ещё используется "type"
    amount: item.amount,
    chance: item.chance,
    description: item.description || '',
    target_side: 'self'
  }));
  const enemy = enemyDamage.map(item => ({
    damage_type: item.damage_type || item.type,
    amount: item.amount,
    chance: item.chance,
    description: item.description || '',
    target_side: 'enemy'
  }));
  return [...self, ...enemy];
};

export default transformDamageData;
