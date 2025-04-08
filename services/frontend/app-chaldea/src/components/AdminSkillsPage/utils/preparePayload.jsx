// src/utils/preparePayload.js

// Функция объединения данных урона из UI: selfDamage и enemyDamage
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

// Подготовка данных для одного ранга
export const prepareRankPayload = (rankData) => {
  // Если UI сохраняет данные по урону в selfDamage и enemyDamage, используем их.
  // Если их нет, можно попробовать использовать уже сохранённое поле damage_entries.
  const selfDamage = rankData.selfDamage || [];
  const enemyDamage = rankData.enemyDamage || [];

  // Создаем копию базовых данных ранга, исключая UI-поля, которые не должны уходить в payload.
  const {
    selfDamage: _, enemyDamage: __, selfDamageBuff, selfResist, enemyDamageBuff, enemyResist,
    enemyVulnerability, selfVulnerability, selfComplexEffects, enemyComplexEffects,
    ...baseData
  } = rankData;

  return {
    ...baseData,
    // Если есть данные из UI, используем их; иначе – оставляем damage_entries как есть.
    damage_entries: (selfDamage.length || enemyDamage.length)
      ? transformDamageData(selfDamage, enemyDamage)
      : rankData.damage_entries,
    effects: rankData.effects || []
  };
};

// Функция подготовки всего навыка (полное дерево)
export const prepareSkillPayload = (skillTreeData) => {
  const { ranks, ...baseData } = skillTreeData;
  return {
    ...baseData,
    // Сохраняем фотографию навыка, если она уже есть
    skill_image: skillTreeData.skill_image,
    // Для каждого ранга вызываем prepareRankPayload
    ranks: ranks.map(rankData => prepareRankPayload(rankData))
  };
};
