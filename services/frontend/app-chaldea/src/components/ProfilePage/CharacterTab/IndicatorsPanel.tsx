import { Heart } from 'lucide-react';
import { useAppSelector } from '../../../redux/store';
import {
  selectAttributes,
  selectProfile,
  selectRaceInfo,
  selectEquipment,
} from '../../../redux/slices/profileSlice';
import PanelShell, { PANEL_DESKTOP_HEIGHT_CLASS } from '../PanelShell';
import StatsPanel from '../CharacterInfoPanel/StatsPanel';
import PrimaryStatsSection from '../StatsTab/PrimaryStatsSection';
import StatDistributionPanel from '../StatsTab/StatDistributionPanel';
import DerivedStatsSection from '../StatsTab/DerivedStatsSection';

interface IndicatorsPanelProps {
  characterId: number;
}

/**
 * Panel 2 (minmax(300px,352px)) — «Показатели» (FEAT-149 Task 5):
 * vitals bars with icon-only labels, «Характеристики» tiered bars,
 * stat distribution (when points > 0), «В бою» stat cards + resist chips.
 * Each section renders its own mock-style title row with a fading gold rule.
 */
const IndicatorsPanel = ({ characterId }: IndicatorsPanelProps) => {
  const profile = useAppSelector(selectProfile);
  const raceInfo = useAppSelector(selectRaceInfo);
  const attributes = useAppSelector(selectAttributes);
  const equipment = useAppSelector(selectEquipment);

  const classId = raceInfo?.id_class ?? null;
  const mainWeaponSlot = equipment.find((slot) => slot.slot_type === 'main_weapon');
  const mainWeaponDamageModifier = mainWeaponSlot?.item?.damage_modifier ?? 0;
  const statPoints = profile?.stat_points ?? 0;

  return (
    <PanelShell
      title="Показатели"
      icon={<Heart size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
      className={PANEL_DESKTOP_HEIGHT_CLASS}
    >
      <div className="flex flex-col gap-6">
        {/* Vitals — icon-only labels, values right-aligned */}
        <StatsPanel />

        {/* «Характеристики» — tiered bars */}
        {attributes && <PrimaryStatsSection attributes={attributes} />}

        {/* Stat point distribution (only when there are points to spend) */}
        {attributes && statPoints > 0 && (
          <StatDistributionPanel
            characterId={characterId}
            statPoints={statPoints}
            attributes={attributes}
          />
        )}

        {/* «В бою» — combat stat cards + resist chips */}
        {attributes && (
          <DerivedStatsSection
            attributes={attributes}
            classId={classId}
            mainWeaponDamageModifier={mainWeaponDamageModifier}
          />
        )}
      </div>
    </PanelShell>
  );
};

export default IndicatorsPanel;
