import useNavigateTo from '../../../../hooks/useNavigateTo';
import SubraceButton from './SubraceButton/SubraceButton';
import type { RaceData, StatPreset } from '../../types';
import { STAT_LABELS } from '../../../ProfilePage/constants';
import questionMarkIcon from '../../../../assets/questionMarkSVG.svg';

interface RaceDescriptionProps {
  raceData: RaceData;
  onSubraceChange: (id: number) => void;
  selectedSubraceId: number | null;
}

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

export default function RaceDescription({
  raceData,
  onSubraceChange,
  selectedSubraceId,
}: RaceDescriptionProps) {
  const navigateTo = useNavigateTo();

  const selectedSubrace = raceData.subraces.find(
    (subrace) => subrace?.id_subrace === selectedSubraceId,
  );

  return (
    <div className="w-full grid grid-cols-1 md:grid-cols-3 md:gap-[50px] gap-8 px-4 md:px-[60px]">
      {/* Race description column */}
      <div className="relative flex flex-col items-center gap-5 md:after:content-[''] md:after:absolute md:after:top-1/2 md:after:right-[-7.5%] md:after:h-[70%] md:after:w-px md:after:bg-gradient-to-b md:after:from-transparent md:after:via-[#999] md:after:to-transparent md:after:z-[1] md:after:-translate-y-1/2">
        <h4 className="gold-text text-xl font-medium uppercase">{raceData.name}</h4>
        <p className="text-white text-base font-normal">{raceData.description}</p>
        {raceData.image && (
          <img
            src={raceData.image}
            alt={raceData.name}
            className="w-full max-w-[200px] rounded-card object-cover"
          />
        )}
      </div>

      {/* Subrace selection column */}
      <div className="relative flex flex-col items-center gap-5 md:after:content-[''] md:after:absolute md:after:top-1/2 md:after:right-[-7.5%] md:after:h-[70%] md:after:w-px md:after:bg-gradient-to-b md:after:from-transparent md:after:via-[#999] md:after:to-transparent md:after:z-[1] md:after:-translate-y-1/2">
        <div className="flex flex-wrap justify-center gap-3 w-full">
          {raceData.subraces.map((subrace) => (
            <SubraceButton
              key={subrace.id_subrace}
              text={subrace.name}
              index={subrace.id_subrace}
              isActive={selectedSubraceId === subrace.id_subrace}
              setCurrentIndex={onSubraceChange}
            />
          ))}
        </div>
        <p className="text-white text-base font-normal">
          {selectedSubrace?.description}
        </p>
        {selectedSubrace?.image && (
          <img
            src={selectedSubrace.image}
            alt={selectedSubrace.name}
            className="w-full max-w-[200px] rounded-card object-cover"
          />
        )}
      </div>

      {/* Stats preset column */}
      <div className="flex flex-col items-center gap-5">
        <h4 className="gold-text text-xl font-medium uppercase relative">
          Характеристики
          <a
            className="cursor-pointer absolute w-[15px] h-[15px] -top-[5px] -right-[18px] bg-no-repeat bg-cover"
            style={{ backgroundImage: `url(${questionMarkIcon})` }}
            onClick={() => navigateTo('/rules')}
          />
        </h4>

        {selectedSubrace?.stat_preset ? (
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
                  {selectedSubrace.stat_preset![key]}
                </span>
              </div>
            ))}
            <div className="col-span-2 flex justify-between items-center mt-2 pt-2 border-t border-white/10">
              <span className="text-white/60 text-xs uppercase">Всего</span>
              <span className="text-gold text-sm font-medium">
                {STAT_DISPLAY_ORDER.reduce(
                  (sum, key) => sum + (selectedSubrace.stat_preset![key] || 0),
                  0,
                )}
              </span>
            </div>
          </div>
        ) : (
          <p className="text-white/50 text-sm">
            Выберите подрасу для просмотра характеристик
          </p>
        )}
      </div>
    </div>
  );
}
