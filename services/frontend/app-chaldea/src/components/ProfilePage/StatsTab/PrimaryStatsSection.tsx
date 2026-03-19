import { CharacterAttributes } from '../../../redux/slices/profileSlice';
import { MAIN_STATS, STAT_LABELS } from '../constants';

interface PrimaryStatsSectionProps {
  attributes: CharacterAttributes;
}

const TieredBar = ({ value }: { value: number }) => {
  const greenWidth = Math.min(value, 100);
  const redWidth = Math.min(Math.max(value - 100, 0), 100);
  const blackWidth = Math.min(Math.max(value - 200, 0), 100);

  return (
    <div className="relative h-2 w-full rounded-full bg-white/10 overflow-hidden">
      {/* Green layer: 0-100 */}
      <div
        className="absolute inset-y-0 left-0 rounded-full transition-all duration-300"
        style={{
          width: `${greenWidth}%`,
          background: '#4ade80',
        }}
      />
      {/* Red layer: 100-200 */}
      <div
        className="absolute inset-y-0 left-0 rounded-full transition-all duration-300"
        style={{
          width: `${redWidth}%`,
          background: '#ef4444',
        }}
      />
      {/* Black layer: 200+ */}
      <div
        className="absolute inset-y-0 left-0 rounded-full transition-all duration-300"
        style={{
          width: `${blackWidth}%`,
          background: '#1a1a2e',
        }}
      />
    </div>
  );
};

const PrimaryStatsSection = ({ attributes }: PrimaryStatsSectionProps) => {
  return (
    <div>
      <h3 className="gold-text text-xl font-medium uppercase mb-4">
        Основные характеристики
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
        {MAIN_STATS.map((stat) => {
          const value = attributes[stat] ?? 0;
          return (
            <div key={stat} className="flex flex-col gap-1">
              <div className="flex justify-between items-center">
                <span className="text-white text-sm font-medium">
                  {STAT_LABELS[stat]}
                </span>
                <span className="text-white/70 text-sm font-mono">
                  {value}
                </span>
              </div>
              <TieredBar value={value} />
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default PrimaryStatsSection;
