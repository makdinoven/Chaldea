import { CharacterAttributes } from '../../../redux/slices/profileSlice';

interface ResourceStatsSectionProps {
  attributes: CharacterAttributes;
}

const RESOURCE_STATS = [
  {
    label: 'Здоровье',
    currentKey: 'current_health' as const,
    maxKey: 'max_health' as const,
    colorClass: 'stat-bar-hp',
  },
  {
    label: 'Энергия',
    currentKey: 'current_energy' as const,
    maxKey: 'max_energy' as const,
    colorClass: 'stat-bar-energy',
  },
  {
    label: 'Мана',
    currentKey: 'current_mana' as const,
    maxKey: 'max_mana' as const,
    colorClass: 'stat-bar-mana',
  },
  {
    label: 'Выносливость',
    currentKey: 'current_stamina' as const,
    maxKey: 'max_stamina' as const,
    colorClass: 'stat-bar-stamina',
  },
];

const ResourceStatsSection = ({ attributes }: ResourceStatsSectionProps) => {
  return (
    <div>
      <h3 className="gold-text text-xl font-medium uppercase mb-4">
        Ресурсы
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
        {RESOURCE_STATS.map(({ label, currentKey, maxKey, colorClass }) => {
          const current = attributes[currentKey] ?? 0;
          const max = attributes[maxKey] ?? 1;
          const percent = max > 0 ? Math.min((current / max) * 100, 100) : 0;

          return (
            <div key={currentKey} className="flex flex-col gap-1">
              <div className="flex justify-between items-center">
                <span className="text-white text-sm font-medium">
                  {label}
                </span>
                <span className="text-white/70 text-sm font-mono">
                  {Math.round(current)} / {Math.round(max)}
                </span>
              </div>
              <div className="stat-bar">
                <div
                  className={`stat-bar-fill ${colorClass}`}
                  style={{ width: `${percent}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ResourceStatsSection;
