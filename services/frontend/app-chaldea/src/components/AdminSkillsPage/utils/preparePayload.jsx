// src/utils/preparePayload.js

// Функция объединяет данные урона из вкладок "Для себя" и "Для врага"
// с явным добавлением поля target_side и игнорированием поля duration.
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
// Она копирует все поля, затем удаляет временные ключи (например, selfDamage, enemyDamage и проч.),
// затем добавляет сформированное поле damage_entries и оставляет эффекты как есть.
export const prepareRankPayload = (rankData) => {
  // Создаем копию данных ранга, чтобы не менять оригинал.
  const baseData = { ...rankData };

  // Удаляем поля, которые используются только для UI (не должны уходить в payload)
  delete baseData.selfDamage;
  delete baseData.enemyDamage;
  delete baseData.selfDamageBuff;
  delete baseData.selfResist;
  delete baseData.enemyDamageBuff;
  delete baseData.enemyResist;
  delete baseData.enemyVulnerability;
  delete baseData.selfVulnerability;
  delete baseData.selfComplexEffects;
  delete baseData.enemyComplexEffects;

  return {
    ...baseData,
    // Если rank_image уже установлен, сохраняем его.
    ...(rankData.rank_image ? { rank_image: rankData.rank_image } : {}),
    // Формируем единственное поле damage_entries из данных selfDamage и enemyDamage.
    damage_entries: transformDamageData(rankData.selfDamage, rankData.enemyDamage),
    // Если эффекты присутствуют, передаем их; иначе – пустой массив.
    effects: rankData.effects ? rankData.effects : []
  };
};

// Функция подготовки данных для всего навыка (полное дерево).
// Она сохраняет основные поля, включая skill_image, и для каждого ранга вызывается prepareRankPayload.
export const prepareSkillPayload = (skillTreeData) => {
  // Создаем копию данных навыка.
  const baseData = { ...skillTreeData };

  // Если в объекте есть лишние поля, которые не должны уходить в payload – можно удалить их здесь.
  // Например, если есть какие-то UI-поля, которые не нужны на сервере.
  delete baseData.ranks; // будем задавать заново

  return {
    ...baseData,
    // Сохраняем фотографию навыка, если она уже есть.
    ...(skillTreeData.skill_image ? { skill_image: skillTreeData.skill_image } : {}),
    // Для каждого ранга формируем payload с помощью prepareRankPayload.
    ranks: skillTreeData.ranks.map(rankData => prepareRankPayload(rankData))
  };
};
