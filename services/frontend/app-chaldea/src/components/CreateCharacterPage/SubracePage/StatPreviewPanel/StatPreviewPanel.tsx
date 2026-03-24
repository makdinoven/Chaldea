import { motion } from 'motion/react';
import { STAT_LABELS } from '../../../ProfilePage/constants';
import type { StatPreset, StatPreviewPanelProps } from '../../types';

const STAT_DISPLAY_ORDER: (keyof StatPreset)[] = [
  'strength',
  'agility',
  'intelligence',
  'endurance',
  'health',
  'energy',
  'mana',
  'stamina',
  'charisma',
  'luck',
];

const StatPreviewPanel = ({ statPreset, subraceName }: StatPreviewPanelProps) => {
  return (
    <motion.div
      key={subraceName}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className="gray-bg rounded-card p-4"
    >
      <h4 className="gold-text text-xl font-medium uppercase mb-4 text-center">
        {subraceName}
      </h4>
      <h5 className="gold-text text-base font-medium uppercase mb-3 text-center">
        Характеристики
      </h5>

      {statPreset ? (
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 w-full">
          {STAT_DISPLAY_ORDER.map((key) => (
            <div
              key={key}
              className="flex justify-between items-center px-2 py-1 rounded hover:bg-white/5 transition-colors"
            >
              <span className="text-white text-sm font-normal">
                {STAT_LABELS[key] || key}
              </span>
              <span className="text-gold text-sm font-medium ml-2">
                {statPreset[key]}
              </span>
            </div>
          ))}
          <div className="col-span-2 flex justify-between items-center mt-2 pt-2 border-t border-white/10">
            <span className="text-white/60 text-xs uppercase">Всего</span>
            <span className="text-gold text-sm font-medium">
              {STAT_DISPLAY_ORDER.reduce(
                (sum, key) => sum + (statPreset[key] || 0),
                0,
              )}
            </span>
          </div>
        </div>
      ) : (
        <p className="text-white/50 text-sm text-center">
          Нет данных о характеристиках
        </p>
      )}
    </motion.div>
  );
};

export default StatPreviewPanel;
