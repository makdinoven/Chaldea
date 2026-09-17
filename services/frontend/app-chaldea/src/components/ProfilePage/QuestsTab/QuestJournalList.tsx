// FEAT-151 — QuestsTab journal list (left master column of the master-detail layout).
// FEAT-166 — rows are ProfileCards with GoldIconFrame + ProgressBar.
import { motion } from 'motion/react';
import { Check, Scroll } from 'lucide-react';
import { MotionProfileCard } from '../shared/ProfileCard';
import GoldIconFrame from '../shared/GoldIconFrame';
import ProgressBar from '../shared/ProgressBar';
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
          <MotionProfileCard
            key={quest.id}
            variants={{
              hidden: { opacity: 0, y: 10 },
              visible: { opacity: 1, y: 0 },
            }}
            as="button"
            interactive
            active={active}
            onClick={() => onSelect(quest.id)}
            className="p-3"
          >
            {/* inner flex row: ProfileCard `as="button"` is `block w-full` */}
            <span className="flex items-center gap-3 min-w-0">
              <GoldIconFrame size={42}>
                <Scroll size={18} strokeWidth={1.6} className="text-gold/70" />
              </GoldIconFrame>

              <span className="flex flex-col gap-1.5 flex-1 min-w-0">
                <span className="text-white text-[13.5px] font-medium leading-tight truncate">
                  {quest.title}
                </span>
                <span className="flex items-center gap-2 min-w-0">
                  <span
                    className={`text-[10px] font-medium uppercase tracking-[0.05em] shrink-0 ${typeColor}`}
                  >
                    {typeLabel}
                  </span>
                  <ProgressBar
                    value={pct}
                    max={100}
                    size="sm"
                    variant={complete ? 'energy' : 'mana'}
                    className="flex-1"
                  />
                </span>
              </span>

              {complete && (
                <Check size={18} strokeWidth={2.6} className="text-stat-energy shrink-0" />
              )}
            </span>
          </MotionProfileCard>
        );
      })}
    </motion.div>
  );
};

export default QuestJournalList;
