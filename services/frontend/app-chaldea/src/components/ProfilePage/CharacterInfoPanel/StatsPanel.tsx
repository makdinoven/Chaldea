import { useAppSelector } from '../../../redux/store';
import { selectAttributes, selectProfile } from '../../../redux/slices/profileSlice';
import { RESOURCE_BARS } from '../constants';

export default function StatsPanel() {
  const attributes = useAppSelector(selectAttributes);
  const profile = useAppSelector(selectProfile);

  if (!attributes && !profile) {
    return (
      <div className="flex flex-col gap-[10px] w-[210px]">
        {[...Array(4)].map((_, i) => (
          <div key={i}>
            <div className="flex justify-between items-center mb-[10px]">
              <span className="gold-text text-sm font-medium uppercase w-20 h-4 animate-pulse" />
              <span className="gold-text text-sm font-medium w-16 h-4 animate-pulse" />
            </div>
            <div className="stat-bar" />
          </div>
        ))}
      </div>
    );
  }

  // Use attributes for current/max values (they're more detailed),
  // but fall back to profile.attributes if attributes are not loaded yet
  const resourceData = {
    current_health: attributes?.current_health ?? profile?.attributes?.current_health ?? 0,
    max_health: attributes?.max_health ?? profile?.attributes?.max_health ?? 1,
    current_mana: attributes?.current_mana ?? profile?.attributes?.current_mana ?? 0,
    max_mana: attributes?.max_mana ?? profile?.attributes?.max_mana ?? 1,
    current_energy: attributes?.current_energy ?? profile?.attributes?.current_energy ?? 0,
    max_energy: attributes?.max_energy ?? profile?.attributes?.max_energy ?? 1,
    current_stamina: attributes?.current_stamina ?? profile?.attributes?.current_stamina ?? 0,
    max_stamina: attributes?.max_stamina ?? profile?.attributes?.max_stamina ?? 1,
  };

  return (
    <div className="flex flex-col gap-5 w-[210px]">
      {/* Resource Bars — Figma: 210px wide, gold labels, 9px bars */}
      {RESOURCE_BARS.map(({ key, label, colorClass }) => {
        const currentKey = `current_${key}` as keyof typeof resourceData;
        const maxKey = `max_${key}` as keyof typeof resourceData;
        const current = resourceData[currentKey];
        const max = resourceData[maxKey];
        const percent = max > 0 ? Math.min((current / max) * 100, 100) : 0;

        return (
          <div key={key} className="flex flex-col gap-[10px]">
            <div className="flex justify-between items-end relative">
              <span className="gold-text text-sm font-medium uppercase">
                {label}
              </span>
              <span className="gold-text text-sm font-medium uppercase text-right">
                {Math.round(current)}/{Math.round(max)}
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
  );
}
