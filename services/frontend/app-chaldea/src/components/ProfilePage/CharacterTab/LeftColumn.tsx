import { useAppSelector } from '../../../redux/store';
import {
  selectAttributes,
  selectProfile,
  selectRaceInfo,
  selectRaceNamesMap,
  selectEquipment,
} from '../../../redux/slices/profileSlice';
import { CLASS_NAMES } from '../constants';
import StatsPanel from '../CharacterInfoPanel/StatsPanel';
import PrimaryStatsSection from '../StatsTab/PrimaryStatsSection';
import DerivedStatsSection from '../StatsTab/DerivedStatsSection';
import StatDistributionPanel from '../StatsTab/StatDistributionPanel';
import goldCoinsIcon from '../../../assets/icons/gold-coins.svg';

interface LeftColumnProps {
  characterId: number;
}

const LeftColumn = ({ characterId }: LeftColumnProps) => {
  const profile = useAppSelector(selectProfile);
  const raceInfo = useAppSelector(selectRaceInfo);
  const raceNamesMap = useAppSelector(selectRaceNamesMap);
  const attributes = useAppSelector(selectAttributes);
  const equipment = useAppSelector(selectEquipment);

  const raceName = raceInfo ? (raceNamesMap[raceInfo.id_race] ?? 'Неизвестная раса') : '—';
  const className = raceInfo ? (CLASS_NAMES[raceInfo.id_class] ?? 'Неизвестный класс') : '—';
  const classId = raceInfo?.id_class ?? null;
  const mainWeaponSlot = equipment.find((slot) => slot.slot_type === 'main_weapon');
  const mainWeaponDamageModifier = mainWeaponSlot?.item?.damage_modifier ?? 0;
  const statPoints = profile?.stat_points ?? 0;

  return (
    <div className="w-full lg:min-w-[260px] flex flex-col gap-4 lg:max-h-[calc(100vh-120px)] lg:overflow-y-auto gold-scrollbar lg:pr-1 order-2 lg:order-1 bg-black/30 rounded-card p-4">
      {/* Character name, race, class */}
      {profile && (
        <div className="flex flex-col gap-1.5">
          <h3 className="gold-text text-xl font-medium uppercase">
            {profile.name}
          </h3>
          {profile.active_title && (
            <span className="text-site-blue text-sm italic">
              {profile.active_title}
            </span>
          )}
          <div className="flex items-center gap-2 text-sm text-white/80">
            <span>{raceName}</span>
            <span className="text-white/30">|</span>
            <span>{className}</span>
          </div>
          {/* Currency */}
          <div className="flex items-center gap-2 mt-1">
            <img src={goldCoinsIcon} alt="" className="w-5 h-5" />
            <span className="gold-text text-sm font-medium">
              {profile.currency_balance.toLocaleString('ru-RU')}
            </span>
          </div>
        </div>
      )}

      {/* Resource bars */}
      <div className="gradient-divider-h relative pb-2" />
      <StatsPanel />

      {/* Primary stats (forced single column) */}
      {attributes && (
        <>
          <div className="gradient-divider-h relative pb-2" />
          <div className="[&_.grid]:!grid-cols-1">
            <PrimaryStatsSection attributes={attributes} />
          </div>
        </>
      )}

      {/* Stat distribution panel */}
      {attributes && statPoints > 0 && (
        <>
          <div className="gradient-divider-h relative pb-2" />
          <div className="[&_.grid]:!grid-cols-1">
            <StatDistributionPanel
              characterId={characterId}
              statPoints={statPoints}
              attributes={attributes}
            />
          </div>
        </>
      )}

      {/* Derived/combat stats (forced single column) */}
      {attributes && (
        <>
          <div className="gradient-divider-h relative pb-2" />
          <div className="[&_.grid]:!grid-cols-1">
            <DerivedStatsSection
              attributes={attributes}
              classId={classId}
              mainWeaponDamageModifier={mainWeaponDamageModifier}
            />
          </div>
        </>
      )}
    </div>
  );
};

export default LeftColumn;
