import transformDamageData from '../utils/transformDamageData';

const prepareRankPayload = (rankData) => ({
  id: rankData.id,
  rank_name: rankData.rank_name,
  rank_image: rankData.rank_image,
  rank_number: rankData.rank_number,
  left_child_id: rankData.left_child_id,
  right_child_id: rankData.right_child_id,
  cost_energy: rankData.cost_energy,
  cost_mana: rankData.cost_mana,
  cooldown: rankData.cooldown,
  level_requirement: rankData.level_requirement,
  upgrade_cost: rankData.upgrade_cost,
  class_limitations: rankData.class_limitations,
  race_limitations: rankData.race_limitations,
  subrace_limitations: rankData.subrace_limitations,
  rank_description: rankData.rank_description,
  // Объединяем данные урона из двух вкладок в один массив damage_entries
  damage_entries: transformDamageData(rankData.selfDamage, rankData.enemyDamage),
  effects: rankData.effects // Эффекты уже должны содержать поле target_side
});

const prepareSkillPayload = (skillTreeData) => ({
  id: skillTreeData.id,
  name: skillTreeData.name,
  skill_type: skillTreeData.skill_type,
  description: skillTreeData.description,
  class_limitations: skillTreeData.class_limitations,
  race_limitations: skillTreeData.race_limitations,
  subrace_limitations: skillTreeData.subrace_limitations,
  min_level: skillTreeData.min_level,
  purchase_cost: skillTreeData.purchase_cost,
  skill_image: skillTreeData.skill_image,
  // Преобразуем каждый ранг с помощью функции prepareRankPayload
  ranks: skillTreeData.ranks.map(rankData => prepareRankPayload(rankData))
});
