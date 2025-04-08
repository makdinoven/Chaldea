// src/utils/preparePayload.js

// Функция объединяет данные урона из вкладок "Для себя" и "Для врага"
// с добавлением поля target_side и игнорированием поля duration.
export const transformDamageData = (selfDamage = [], enemyDamage = []) => {
  const self = selfDamage.map(item => ({
    damage_type: item.damage_type || item.type,
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

// Функция подготовки данных для одного ранга.
// Здесь с помощью деструктуризации удаляются поля для UI: selfDamage, enemyDamage и прочие.
export const prepareRankPayload = (rankData) => {
  const {
    selfDamage = [],
    enemyDamage = [],
    selfDamageBuff,
    selfResist,
    enemyDamageBuff,
    enemyResist,
    enemyVulnerability,
    selfVulnerability,
    selfComplexEffects,
    enemyComplexEffects,
    ...baseData
  } = rankData;

  return {
    ...baseData,
    // Если rank_image уже задан, оно останется в baseData
    damage_entries: transformDamageData(selfDamage, enemyDamage),
    effects: rankData.effects ? rankData.effects : []  // Передаем эффекты как есть
  };
};

// Функция подготовки данных для всего навыка (полное дерево).
// Здесь сохраняются основные поля, включая skill_image, и для каждого ранга вызывается prepareRankPayload.
export const prepareSkillPayload = (skillTreeData) => {
  const { ranks, ...baseData } = skillTreeData;
  return {
    ...baseData,
    // Сохраняем фотографию навыка, если она уже есть
    skill_image: skillTreeData.skill_image,
    // Для каждого ранга формируем корректный payload через prepareRankPayload
    ranks: ranks.map(rankData => prepareRankPayload(rankData))
  };
};
