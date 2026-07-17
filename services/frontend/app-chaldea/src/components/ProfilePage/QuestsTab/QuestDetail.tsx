// FEAT-151 — QuestsTab detail panel (right column of the master-detail layout):
// header with icon/title/type, description, objectives with progress bars,
// reward chips, «Сдать задание» / «Отказаться» actions.
import { motion } from 'motion/react';
import { Check, Coins, Scroll, Star, X } from 'lucide-react';
import SectionHeader from '../shared/SectionHeader';
import {
  type ActiveQuest,
  QUEST_TYPE_BADGES,
  QUEST_TYPE_LABELS,
  isQuestComplete,
} from './questModel';

interface QuestDetailProps {
  quest: ActiveQuest;
  completing: boolean;
  abandoning: boolean;
  onComplete: () => void;
  onAbandon: () => void;
}

const QuestDetail = ({
  quest,
  completing,
  abandoning,
  onComplete,
  onAbandon,
}: QuestDetailProps) => {
  const complete = isQuestComplete(quest);
  const typeLabel = QUEST_TYPE_LABELS[quest.quest_type] ?? quest.quest_type;
  const typeBadge = QUEST_TYPE_BADGES[quest.quest_type] ?? 'text-white/70 bg-white/10';
  const busy = completing || abandoning;
  const hasRewards =
    quest.reward_currency > 0 || quest.reward_exp > 0 || (quest.reward_items?.length ?? 0) > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className="flex flex-col flex-1 min-h-0"
    >
      {/* Detail header */}
      <div className="flex items-start gap-4 p-5 border-b border-white/[0.08] bg-black/20 rounded-t-card shrink-0">
        {/* 56px icon in gold-gradient frame */}
        <div className="w-14 h-14 shrink-0 rounded-xl p-[2px] bg-gradient-to-b from-gold-light to-gold-dark">
          <div className="w-full h-full rounded-[10px] bg-site-dark flex items-center justify-center">
            <Scroll size={24} strokeWidth={1.6} className="text-gold/70" />
          </div>
        </div>
        <div className="flex flex-col gap-2 flex-1 min-w-0">
          <h3 className="text-white text-lg sm:text-xl font-medium leading-tight">
            {quest.title}
          </h3>
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={`text-[10px] font-medium uppercase tracking-[0.06em] px-2 py-0.5 rounded ${typeBadge}`}
            >
              {typeLabel}
            </span>
            {complete && (
              <span className="text-[10px] font-medium uppercase tracking-[0.06em] px-2 py-0.5 rounded text-stat-energy bg-stat-energy/[0.16]">
                Выполнено
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 min-h-0 lg:overflow-y-auto gold-scrollbar-wide p-5 flex flex-col gap-6">
        <p className="text-sm leading-relaxed text-white/70">{quest.description}</p>

        {/* Objectives */}
        {quest.objectives.length > 0 && (
          <div className="flex flex-col gap-3.5">
            <SectionHeader title="Задачи" />
            {quest.objectives.map((obj) => {
              const done = obj.current_count >= obj.target_count;
              const progress = Math.min(obj.current_count / Math.max(obj.target_count, 1), 1);
              return (
                <div key={obj.objective_id} className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between gap-2.5">
                    <span
                      className={`flex items-center gap-2 text-[13px] ${
                        done ? 'text-stat-energy line-through' : 'text-white/80'
                      }`}
                    >
                      {done ? (
                        <Check
                          size={15}
                          strokeWidth={2.6}
                          className="text-stat-energy shrink-0"
                        />
                      ) : (
                        <span className="w-[13px] h-[13px] shrink-0 rounded-full border-[1.5px] border-white/[0.35]" />
                      )}
                      {obj.description}
                    </span>
                    <span
                      className={`font-mono tabular-nums text-xs font-medium shrink-0 ${
                        done ? 'text-stat-energy' : 'text-white/50'
                      }`}
                    >
                      {obj.current_count}/{obj.target_count}
                    </span>
                  </div>
                  <div className="stat-bar">
                    <div
                      className={`stat-bar-fill ${done ? 'stat-bar-energy' : 'stat-bar-mana'}`}
                      style={{ width: `${progress * 100}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Rewards */}
        {hasRewards && (
          <div className="flex flex-col gap-3">
            <SectionHeader title="Награда" />
            <div className="flex flex-wrap gap-2.5">
              {quest.reward_currency > 0 && (
                <span className="flex items-center gap-2 px-3 py-2 rounded-[10px] border border-gold/20 bg-gold/[0.06]">
                  <Coins size={15} strokeWidth={1.6} className="text-gold shrink-0" />
                  <span className="font-mono tabular-nums text-[13px] font-medium text-gold">
                    {quest.reward_currency}
                  </span>
                </span>
              )}
              {quest.reward_exp > 0 && (
                <span className="flex items-center gap-2 px-3 py-2 rounded-[10px] border border-site-blue/25 bg-site-blue/[0.08]">
                  <Star size={14} strokeWidth={1.6} className="text-site-blue shrink-0" />
                  <span className="font-mono tabular-nums text-[13px] font-medium text-site-blue">
                    {quest.reward_exp} XP
                  </span>
                </span>
              )}
              {quest.reward_items?.map((ri) => (
                <span
                  key={ri.item_id}
                  className="flex items-center gap-2 pl-1.5 pr-3 py-1.5 rounded-[10px] border border-white/10 bg-white/[0.04]"
                >
                  <span className="w-8 h-8 shrink-0 rounded-full p-[2px] bg-gradient-to-b from-gold-light to-gold-dark">
                    <span className="w-full h-full rounded-full bg-site-dark flex items-center justify-center overflow-hidden">
                      {ri.item_image ? (
                        <img
                          src={ri.item_image}
                          alt={ri.item_name}
                          className="w-full h-full object-cover rounded-full"
                        />
                      ) : (
                        <span className="text-[9px] text-white/30">?</span>
                      )}
                    </span>
                  </span>
                  <span className="text-xs text-white/85">
                    {ri.item_name}{' '}
                    <span className="font-mono tabular-nums font-medium text-white">
                      ×{ri.quantity}
                    </span>
                  </span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-col sm:flex-row gap-2.5 mt-auto pt-4">
          {complete && (
            <button
              type="button"
              onClick={onComplete}
              disabled={busy}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-[10px] border border-stat-energy/50 bg-stat-energy/[0.14] text-stat-energy text-[13px] font-medium uppercase tracking-[0.04em] cursor-pointer transition-colors duration-200 ease-site hover:bg-stat-energy/[0.24] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {completing ? (
                <span className="w-4 h-4 border-2 border-stat-energy/30 border-t-stat-energy rounded-full animate-spin" />
              ) : (
                <Check size={16} strokeWidth={2.4} className="shrink-0" />
              )}
              Сдать задание
            </button>
          )}
          <button
            type="button"
            onClick={onAbandon}
            disabled={busy}
            className="flex items-center justify-center gap-2 px-5 py-3 rounded-[10px] border border-white/[0.16] text-white/65 text-[13px] font-medium uppercase tracking-[0.04em] cursor-pointer transition-colors duration-200 ease-site hover:text-site-red hover:border-site-red/60 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {abandoning ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <X size={16} strokeWidth={2} className="shrink-0" />
            )}
            Отказаться
          </button>
        </div>
      </div>
    </motion.div>
  );
};

export default QuestDetail;
