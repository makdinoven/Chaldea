// FEAT-151 — QuestsTab shared types, labels and progress helpers.
// API shapes match locations-service GET /locations/quests/active.

export interface QuestObjective {
  objective_id: number;
  description: string;
  objective_type: string;
  target_count: number;
  current_count: number;
}

export interface QuestRewardItem {
  item_id: number;
  item_name: string;
  item_image: string | null;
  quantity: number;
}

export interface ActiveQuest {
  id: number;
  quest_id: number;
  title: string;
  description: string;
  quest_type: string;
  reward_currency: number;
  reward_exp: number;
  reward_items: QuestRewardItem[];
  objectives: QuestObjective[];
  accepted_at: string;
}

export const QUEST_TYPE_LABELS: Record<string, string> = {
  standard: 'Обычный',
  daily: 'Ежедневный',
  repeatable: 'Повторяемый',
};

/** Text color for the small type label in journal rows */
export const QUEST_TYPE_TEXT_COLORS: Record<string, string> = {
  standard: 'text-gold/80',
  daily: 'text-site-blue',
  repeatable: 'text-stat-energy',
};

/** Badge (pill) classes for the detail header */
export const QUEST_TYPE_BADGES: Record<string, string> = {
  standard: 'text-gold bg-gold/10',
  daily: 'text-site-blue bg-site-blue/10',
  repeatable: 'text-stat-energy bg-stat-energy/10',
};

/** A quest is ready to turn in when every objective reached its target */
export const isQuestComplete = (quest: ActiveQuest): boolean =>
  quest.objectives.length > 0 &&
  quest.objectives.every((obj) => obj.current_count >= obj.target_count);

/** Overall quest progress 0–100 across all objectives */
export const questProgressPct = (quest: ActiveQuest): number => {
  if (quest.objectives.length === 0) return 0;
  let current = 0;
  let target = 0;
  for (const obj of quest.objectives) {
    const t = Math.max(obj.target_count, 1);
    target += t;
    current += Math.min(obj.current_count, t);
  }
  return Math.round((current / target) * 100);
};
