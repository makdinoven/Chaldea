import { motion } from 'motion/react';
import type { GameClass } from '../../../api/characterRequests';

import warriorImg from '../../../assets/classWarriorImg.png';
import plutImg from '../../../assets/classPlutImg.png';
import magicianImg from '../../../assets/classMagicianImg.png';

/**
 * FEAT-154 (task #17) — replaces the old `ClassItem.jsx` and its SCSS module.
 *
 * Name and description come from `GET /characters/classes`; only the artwork is
 * a frontend asset, keyed by class id with a graceful «no art» fallback, so a
 * class added in the admin still renders.
 */

const CLASS_ART: Record<number, string> = {
  1: warriorImg,
  2: plutImg,
  3: magicianImg,
};

/** Which stat the class turns into damage — mirrors `CLASS_MAIN_ATTRIBUTE`
 *  in character-attributes-service and battle-service. */
const CLASS_MAIN_STAT: Record<number, string> = {
  1: 'Сила',
  2: 'Ловкость',
  3: 'Интеллект',
};

interface ClassCardProps {
  gameClass: GameClass;
  isSelected: boolean;
  onSelect: (classId: number) => void;
}

const ClassCard = ({ gameClass, isSelected, onSelect }: ClassCardProps) => {
  const art = CLASS_ART[gameClass.id_class];
  const mainStat = CLASS_MAIN_STAT[gameClass.id_class];

  return (
    <motion.button
      type="button"
      onClick={() => onSelect(gameClass.id_class)}
      aria-pressed={isSelected}
      whileHover={{ scale: 1.01 }}
      transition={{ duration: 0.2 }}
      className={`flex flex-col gap-3 p-4 rounded-card text-left w-full h-full
        transition-colors duration-200 ease-site
        ${isSelected ? 'gold-outline relative bg-white/[0.06]' : 'gray-bg hover:bg-white/[0.08]'}`}
    >
      <h4
        className={`text-lg font-medium uppercase ${isSelected ? 'gold-text' : 'text-white'}`}
      >
        {gameClass.name}
      </h4>

      {art && (
        <div className="w-full h-40 sm:h-48 rounded-card overflow-hidden bg-white/5">
          <img src={art} alt={gameClass.name} className="w-full h-full object-cover" />
        </div>
      )}

      <p className="text-white/80 text-sm leading-relaxed whitespace-pre-line">
        {gameClass.description || 'Описание класса пока не заполнено.'}
      </p>

      {mainStat && (
        <p className="text-white/45 text-[11px] uppercase tracking-[0.06em] mt-auto">
          Основная характеристика: {mainStat}
        </p>
      )}
    </motion.button>
  );
};

export default ClassCard;
