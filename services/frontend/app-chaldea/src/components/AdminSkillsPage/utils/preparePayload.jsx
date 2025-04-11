// utils/preparePayload.js

// Объединяем урон из вкладок "Для себя" и "Для врага"
export const transformDamageData = (selfDamage = [], enemyDamage = []) => {
  const self = selfDamage.map(item => ({
    damage_type: item.damage_type,
    amount: item.amount,
    chance: item.chance,
    description: item.description || '',
    target_side: 'self'
  }));

  const enemy = enemyDamage.map(item => ({
    damage_type: item.damage_type,
    amount: item.amount,
    chance: item.chance,
    description: item.description || '',
    target_side: 'enemy'
  }));

  return [...self, ...enemy];
};

// Преобразование дополнительных эффектов из групп в единый формат эффекта.
// Здесь мы задаём, например, для баффов: effect_name = "Buff: <damage_type>",
// для резистов: "Resist: <type>" и для уязвимостей: "Vulnerability: <type>".
// Если у вас другая логика формирования названия эффекта — скорректируйте при необходимости.
const transformBuff = (buffArray = [], targetSide = 'self') =>
  buffArray.map(item => ({
    target_side: targetSide,
    effect_name: `Buff: ${item.damage_type}`,
    description: item.description || '',
    chance: item.chance,
    duration: item.duration,
    magnitude: item.percent,
    attribute_key: null
  }));
const transformResist = (resistArray = [], targetSide = 'self') =>
  resistArray.map(item => ({
    target_side: targetSide,
    effect_name: `Resist: ${item.type}`, // для резистов поле называется "type"
    description: '',
    chance: item.chance,
    duration: item.duration,
    magnitude: item.percent,
    attribute_key: null
  }));

const transformVulnerability = (vulnArray = [], targetSide = 'self') =>
  vulnArray.map(item => ({
    target_side: targetSide,
    effect_name: `Vulnerability: ${item.type}`, // для уязвимостей
    description: '',
    chance: item.chance,
    duration: item.duration,
    magnitude: item.percent,
    attribute_key: null
  }));

// Если комплексные эффекты уже имеют структуру, похожую на основную модель эффекта, то достаточно добавить target_side.
const transformComplexEffects = (complexArray = [], targetSide = 'self') =>
  complexArray.map(item => ({
    ...item,
    target_side: targetSide
  }));

// Функция подготовки данных для одного ранга.
// Здесь кроме объединения урона (damage_entries) мы объединяем дополнительные эффекты в единый массив effects.
// utils/preparePayload.js
export const prepareRankPayload = (rankData) => {
  const {
    selfDamage = [], enemyDamage = [],
    selfDamageBuff = [], enemyDamageBuff = [],
    selfResist = [], enemyResist = [],
    selfVulnerability = [], enemyVulnerability = [],
    selfComplexEffects = [], enemyComplexEffects = [],
    effects = [],
    ...baseData
  } = rankData;

  const mergedEffects = [
    ...transformBuff(selfDamageBuff, 'self'),
    ...transformBuff(enemyDamageBuff, 'enemy'),
    ...transformResist(selfResist, 'self'),
    ...transformResist(enemyResist, 'enemy'),
    ...transformVulnerability(selfVulnerability, 'self'),
    ...transformVulnerability(enemyVulnerability, 'enemy'),
    ...transformComplexEffects(selfComplexEffects, 'self'),
    ...transformComplexEffects(enemyComplexEffects, 'enemy'),
    ...effects
  ];

  return {
    ...baseData,
    damage_entries: transformDamageData(selfDamage, enemyDamage),
    effects: mergedEffects
  };
};


// Функция подготовки данных для всего навыка (полное дерево).
export const prepareSkillPayload = (skillTreeData) => {
  const { ranks, ...baseData } = skillTreeData;
  return {
    ...baseData,
    // Сохраняем фотографию навыка
    skill_image: skillTreeData.skill_image,
    // Для каждого ранга формируем корректный объект с помощью prepareRankPayload
    ranks: ranks.map(rankData => prepareRankPayload(rankData))
  };
};
