import { useState } from 'react';
import { Snowflake } from 'lucide-react';
import { type ActingCharacter, type House } from '../../../api/houses';
import { useBodyBackground } from '../../../hooks/useBodyBackground';
import HouseFurnish from './HouseFurnish';
import HouseOwnership from './HouseOwnership';
import HouseTaxPanel from './HouseTaxPanel';
import HouseResidents from './HouseResidents';
import HouseSettings from './HouseSettings';
import HousePlan from './HousePlan';

/*
  FEAT-180 stage 7 — «Управление домом»: everything that manages the house
  rather than happens in a room — plan and building, residents and guests,
  furniture, tax, ownership and settings. Needs only the house's location,
  not a room (the shared storage lives in the storage room and the cellar).
*/

type Section = 'plan' | 'residents' | 'furnish' | 'ownership' | 'settings';

const SECTION_LABEL: Record<Section, string> = {
  plan: 'План и стройка',
  residents: 'Жильцы и гости',
  furnish: 'Обстановка',
  ownership: 'Владение',
  settings: 'Настройки',
};

interface HouseManageProps {
  house: House;
  acting: ActingCharacter | null;
  onChanged: () => void;
}

/** Whether the viewer has anything to manage here (owner, resident or guest characters). */
export const canManage = (house: House) => house.acting.length > 0;

const HouseManage = ({ house, acting, onChanged }: HouseManageProps) => {
  const [section, setSection] = useState<Section>('plan');
  useBodyBackground(house.image_url);

  const ownerActing = house.acting.find((a) => a.is_owner && a.character) ?? null;
  const ownerCharacterId = ownerActing?.character?.id ?? null;
  const members = house.acting.filter((a) => !a.is_guest);
  const frozen = house.status === 'frozen';

  const sections: Section[] = ['plan', 'residents'];
  if (ownerActing) sections.push('furnish', 'ownership');
  if (house.is_owner && ownerCharacterId != null) sections.push('settings');
  const shown: Section = sections.includes(section) ? section : 'plan';

  return (
    <div className="flex flex-col gap-4 sm:gap-5">
      {members.length > 0 && (
        <HouseTaxPanel house={house} acting={acting && !acting.is_guest ? acting : members[0]} onChanged={onChanged} />
      )}

      <div className="flex flex-wrap gap-1.5 sm:gap-2">
        {sections.map((s) => (
          <button key={s} type="button" onClick={() => setSection(s)}
            className={`chip-outline rounded-full px-3 sm:px-4 py-1.5 text-xs font-medium ${s === shown ? 'chip-outline-active' : ''}`}>
            {SECTION_LABEL[s]}
          </button>
        ))}
      </div>

      {frozen && shown === 'furnish' && (
        <p className="flex items-center gap-2 text-site-red text-sm">
          <Snowflake size={15} className="shrink-0" />Дом заморожен — это недоступно, пока не уплачен налог.
        </p>
      )}

      {shown === 'plan' && house.rooms.length === 0 && (
        <p className="text-white/55 text-sm">
          {house.plot_kind === 'empty' ? 'Участок пока пуст — комнаты строит хозяин на свободных местах плана.' : 'Комнат пока нет.'}
        </p>
      )}
      {shown === 'plan' && (
        <HousePlan house={house} acting={acting} ownerActing={ownerActing} frozen={frozen} onChanged={onChanged} />
      )}
      {shown === 'residents' && (
        <HouseResidents house={house} ownerCharacterId={ownerCharacterId} onChanged={onChanged} />
      )}
      {shown === 'furnish' && ownerActing && (
        <HouseFurnish house={house} owner={ownerActing} onChanged={onChanged} />
      )}
      {shown === 'ownership' && ownerCharacterId != null && (
        <HouseOwnership house={house} ownerCharacterId={ownerCharacterId} onChanged={onChanged} />
      )}
      {shown === 'settings' && ownerCharacterId != null && (
        <HouseSettings house={house} ownerCharacterId={ownerCharacterId} onChanged={onChanged} />
      )}
    </div>
  );
};

export default HouseManage;
