import { useAppSelector } from '../../../redux/store';
import {
  selectAttributes,
  selectProfile,
  selectRaceInfo,
  selectRaceNamesMap,
} from '../../../redux/slices/profileSlice';
import { CLASS_NAMES } from '../constants';
import PanelShell, { PANEL_DESKTOP_HEIGHT_CLASS } from '../PanelShell';
import AvatarEquipmentGrid from './AvatarEquipmentGrid';
import FastSlots from '../EquipmentPanel/FastSlots';
import goldCoinsIcon from '../../../assets/icons/gold-coins.svg';

const getRarityColorClass = (rarity?: string | null): string => {
  switch (rarity) {
    case 'common': return 'text-rarity-common';
    case 'rare': return 'text-rarity-rare';
    case 'epic': return 'text-rarity-epic';
    case 'mythical': return 'text-rarity-mythical';
    case 'legendary': return 'text-rarity-legendary';
    default: return 'text-rarity-common';
  }
};

/**
 * Panel 1 (392px) — «Персонаж» paper doll (FEAT-149 Task 4):
 * dimmed identity header band (gold LVL circle, name, title, race | class),
 * portrait + equipment diamond, XP bar + stat points, currency + active XP,
 * fast slots 5×2.
 */
const CharacterPanel = () => {
  const profile = useAppSelector(selectProfile);
  const raceInfo = useAppSelector(selectRaceInfo);
  const raceNamesMap = useAppSelector(selectRaceNamesMap);
  const attributes = useAppSelector(selectAttributes);

  const raceName = raceInfo ? (raceNamesMap[raceInfo.id_race] ?? 'Неизвестная раса') : '—';
  const className = raceInfo ? (CLASS_NAMES[raceInfo.id_class] ?? 'Неизвестный класс') : '—';

  return (
    <PanelShell
      className={PANEL_DESKTOP_HEIGHT_CLASS}
      bodyClassName="flex-1 min-h-0 flex flex-col"
    >
      {/* Identity header — dimmed band per mock */}
      {profile && (
        <div className="gradient-divider-h relative flex items-center gap-3.5 px-4 lg:px-5 py-4 bg-black/20 rounded-t-card shrink-0">
          {/* Gold LVL circle */}
          <div className="w-[52px] h-[52px] shrink-0 rounded-full p-[2px] bg-gradient-to-b from-gold-light to-gold-dark shadow-[0_0_14px_rgba(240,217,92,0.35)]">
            <div className="w-full h-full rounded-full bg-site-dark flex flex-col items-center justify-center gap-0.5 leading-none">
              <span className="text-[8px] tracking-[0.1em] text-white/50">LVL</span>
              <span className="gold-text text-lg font-medium leading-none">
                {profile.level}
              </span>
            </div>
          </div>
          <div className="flex flex-col gap-1 min-w-0">
            <h3 className="gold-text text-xl font-medium uppercase leading-tight truncate">
              {profile.name}
            </h3>
            {profile.active_title && (
              <span className={`${getRarityColorClass(profile.active_title_rarity)} text-xs italic truncate`}>
                {profile.active_title}
              </span>
            )}
            <div className="flex items-center gap-2 text-xs text-white/75">
              <span className="truncate">{raceName}</span>
              <span className="text-white/30">|</span>
              <span className="truncate">{className}</span>
            </div>
          </div>
        </div>
      )}

      {/* Scrollable panel body */}
      <div className="flex-1 min-h-0 p-4 lg:p-5 lg:overflow-y-auto gold-scrollbar-wide">
        <div className="flex flex-col gap-[18px]">
          {/* Portrait + equipment diamond */}
          <AvatarEquipmentGrid />

          {/* XP bar + stat points */}
          {profile && (
            <div className="flex flex-col gap-2.5">
              <div className="flex justify-between items-baseline">
                <span className="gold-text text-xs font-medium uppercase tracking-[0.06em]">
                  Опыт
                </span>
                <span className="text-white/85 text-sm">
                  {Math.round(profile.level_progress?.current_exp_in_level ?? 0)}
                  /{Math.round(profile.level_progress?.exp_to_next_level ?? 0)}
                </span>
              </div>
              <div className="stat-bar">
                <div
                  className="stat-bar-fill"
                  style={{
                    width: `${Math.min((profile.level_progress?.progress_fraction ?? 0) * 100, 100)}%`,
                    background: 'linear-gradient(176.46deg, #FFF9B8 2.91%, #BCAB4C 237.31%)',
                  }}
                />
              </div>
              <div className="flex items-center justify-center gap-2 mt-0.5">
                <span className="gold-text text-xs font-medium uppercase tracking-[0.05em]">
                  Очки прокачки
                </span>
                <div className="flex items-center gap-1">
                  <div className="skill-point-dot" />
                  <span className="text-site-blue text-sm font-medium">
                    {profile.stat_points}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Currency + active XP — bordered row per mock */}
          {profile && (
            <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-1 py-3 border-y border-white/10">
              <div className="flex items-center gap-2">
                <img src={goldCoinsIcon} alt="Валюта" className="w-[18px] h-[18px]" />
                <span className="gold-text text-sm font-medium">
                  {profile.currency_balance.toLocaleString('ru-RU')}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-medium uppercase tracking-[0.05em] text-white/55">
                  Актив. опыт
                </span>
                <span className="text-white text-sm font-medium">
                  {(attributes?.active_experience ?? 0).toLocaleString('ru-RU')}
                </span>
              </div>
            </div>
          )}

          {/* Fast slots 5×2 */}
          <FastSlots />
        </div>
      </div>
    </PanelShell>
  );
};

export default CharacterPanel;
