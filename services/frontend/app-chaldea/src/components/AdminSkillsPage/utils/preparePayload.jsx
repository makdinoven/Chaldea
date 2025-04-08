// src/utils/preparePayload.js

// Функция для объединения данных урона из вкладок "Для себя" и "Для врага"
export const transformDamageData = (selfDamage = [], enemyDamage = []) => {
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

// Функция подготовки данных для одного ранга
export const prepareRankPayload = (rankData) => {
  // Извлекаем поля, которые не должны попадать в payload
  const {
    selfDamage,    // данные из вкладки "для себя"
    enemyDamage,   // данные из вкладки "для врага"
    selfDamageBuff, // и другие поля, если не должны отправляться
    selfResist,
    enemyDamageBuff,
    enemyResist,
    enemyVulnerability,
    selfVulnerability,
    selfComplexEffects,
    enemyComplexEffects,
    ...baseData // сюда попадут все остальные поля, которые нам нужны
  } = rankData;

  return {
    ...baseData,
    // Формируем единственный массив damage_entries, объединяя selfDamage и enemyDamage
    damage_entries: transformDamageData(selfDamage, enemyDamage)
    // Поле effects оставляем так, как оно есть – предполагается, что они уже содержат target_side
  };
};

// Функция подготовки данных для всего навыка (полное дерево)
export const prepareSkillPayload = (skillTreeData) => {
  return {
    id: skillTreeData.id,
    name: skillTreeData.name,
    skill_type: skillTreeData.skill_type,
    description: skillTreeData.description,
    class_limitations: skillTreeData.class_limitations,
    race_limitations: skillTreeData.race_limitations,
    subrace_limitations: skillTreeData.subrace_limitations,
    min_level: skillTreeData.min_level,
    purchase_cost: skillTreeData.purchase_cost,
    // Обязательно сохраняем skill_image, чтобы фотография не исчезала
    skill_image: skillTreeData.skill_image,
    // Для каждого ранга формируем корректный payload
    ranks: skillTreeData.ranks.map(rankData => prepareRankPayload(rankData))
  };
};
