// FEAT-151 — QuestsTab journal list (left master column of the master-detail layout).
import { motion } from 'motion/react';
import { Check, Scroll } from 'lucide-react';
import {
  type ActiveQuest,
  QUEST_TYPE_LABELS,
  QUEST_TYPE_TEXT_COLORS,
  isQuestComplete,
  questProgressPct,
} from './questModel';

interface QuestJournalListProps {
  quests: ActiveQuest[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

const QuestJournalList = ({ quests, selectedId, onSelect }: QuestJournalListProps) => {
  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: 0.05 } },
      }}
      className="flex flex-col gap-2.5"
    >
      {quests.map((quest) => {
        const complete = isQuestComplete(quest);
        const pct = questProgressPct(quest);
        const active = quest.id === selectedId;
        const typeLabel = QUEST_TYPE_LABELS[quest.quest_type] ?? quest.quest_type;
        const typeColor = QUEST_TYPE_TEXT_COLORS[quest.quest_type] ?? 'text-white/60';
        return (
          <motion.button
            key={quest.id}
            variants={{
              hidden: { opacity: 0, y: 10 },
              visible: { opacity: 1, y: 0 },
            }}
            type="button"
            onClick={() => onSelect(quest.id)}
            className={`flex items-center gap-3 p-3 rounded-card border text-left cursor-pointer transition-colors duration-200 ease-site ${
              active
                ? 'border-gold/40 bg-gold/[0.06]'
                : 'border-white/[0.08] bg-black/20 hover:border-gold/25'
            }`}
          >
            {/* 42px icon in gold-gradient frame */}
            <span className="w-[42px] h-[42px] shrink-0 rounded-[10px] p-[2px] bg-gradient-to-b from-gold-light to-gold-dark">
              <span className="w-full h-full rounded-lg bg-site-dark flex items-center justify-center">
                <Scroll size={18} strokeWidth={1.6} className="text-gold/70" />
              </span>
            </span>

            <span className="flex flex-col gap-1.5 flex-1 min-w-0">
              <span className="text-white text-[13.5px] font-medium leading-tight truncate">
                {quest.title}
              </span>
              <span className="flex items-center gap-2">
                <span
                  className={`text-[10px] font-medium uppercase tracking-[0.05em] shrink-0 ${typeColor}`}
                >
                  {typeLabel}
                </span>
                {/* thin overall progress bar */}
                <span className="flex-1 h-1 rounded-full bg-white/10 overflow-hidden">
                  <span
                    className={`block h-full rounded-full ${
                      complete ? 'bg-stat-energy' : 'bg-site-blue'
                    }`}
                    style={{ width: `${pct}%` }}
                  />
                </span>
              </span>
            </span>

            {complete && (
              <Check size={18} strokeWidth={2.6} className="text-stat-energy shrink-0" />
            )}
          </motion.button>
        );
      })}
    </motion.div>
  );
};

export default QuestJournalList;
