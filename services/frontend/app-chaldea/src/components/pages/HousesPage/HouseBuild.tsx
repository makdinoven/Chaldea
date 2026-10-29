import { useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { MapPin, Trash2 } from 'lucide-react';
import {
  buildRoom,
  demolishRoom,
  findCost,
  MAX_ROOM_LEVEL,
  ROOM_TYPE_LABEL,
  ROOM_TYPES,
  upgradeRoom,
  type BuildCost,
  type House,
  type HouseRoom,
  type PlanCell,
  type RoomType,
} from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import { useAppDispatch } from '../../../redux/store';
import { getMe } from '../../../redux/slices/userSlice';
import { FIELD, LABEL } from '../EpisodesPage/EpisodeFormModal';
import ConfirmDialog from '../LocationPage/ConfirmDialog';
import { CostView, levelPerk, ROOM_TYPE_ICON, roomTypeHint } from './building';
import { useCurrency } from '../../../hooks/useCurrency';

/*
  FEAT-180 stages 2 and 5 — the owner's building actions, used by the house
  plan: build a room on a free place, upgrade it (levels 1..3, each step costs
  gold, materials and time) and pull it down. Building needs the owner
  standing at the house; demolishing doesn't.
*/

export type HouseAction = (action: () => Promise<unknown>, ok: string, fail: string) => Promise<boolean>;

/** Runs an owner action: toasts, reloads the house and the header gold. */
export const useHouseAction = (onChanged: () => void): { busy: boolean; act: HouseAction } => {
  const dispatch = useAppDispatch();
  const [busy, setBusy] = useState(false);
  const act: HouseAction = async (action, ok, fail) => {
    setBusy(true);
    try {
      await action();
      toast.success(ok);
      onChanged();
      // Gold shown in the header comes from /users/me.
      void dispatch(getMe());
      return true;
    } catch (e) {
      toast.error(apiErrorMessage(e, fail));
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, act };
};

/** «Дойдите до дома, чтобы строить» with a link to the house's location. */
export const AtHouseHint = ({ house, what = 'строить' }: { house: House; what?: string }) => (
  <p className="flex items-center gap-1.5 text-gold-light text-xs bg-gold/10 border border-gold-dark/30 rounded-card px-3 py-2">
    <MapPin size={13} className="shrink-0" />
    <span>
      Дойдите до дома, чтобы {what}:{' '}
      <Link to={`/location/${house.location_id}`} className="site-link">{house.location_name ?? 'локация дома'}</Link>
    </span>
  </p>
);

interface OwnerActionProps {
  house: House;
  characterId: number;
  costs: BuildCost[] | null;
  atHouse: boolean;
  frozen: boolean;
  busy: boolean;
  act: HouseAction;
}

/** Upgrade (with its price) and demolish of one room. */
export const RoomBuildActions = ({ house, room, characterId, costs, atHouse, frozen, busy, act }: OwnerActionProps & { room: HouseRoom }) => {
  const { forms } = useCurrency();
  const [demolishing, setDemolishing] = useState(false);
  const building = room.upgrade_to_level != null;
  const next = room.level + 1;
  const canUpgrade = !building && room.level < MAX_ROOM_LEVEL;
  const cost = costs ? findCost(costs, room.room_type, next) : null;

  return (
    <div className="flex flex-col gap-3 pt-3 border-t border-white/[0.06]">
      {!building && room.level >= MAX_ROOM_LEVEL && <span className="text-white/40 text-xs">Наивысший уровень</span>}
      {canUpgrade && (
        <div className="flex flex-col gap-2">
          <span className="text-white/45 text-[11px]">
            Улучшение до ур. {next}
            {levelPerk(room.room_type, next) ? ` (${levelPerk(room.room_type, next)})` : ''}:
          </span>
          {costs ? <CostView cost={cost} /> : <span className="text-white/30 text-xs">Загрузка стоимости...</span>}
          <button type="button" disabled={busy || !atHouse || !cost || frozen}
            onClick={() => void act(() => upgradeRoom(house.id, room.id, characterId),
              `«${room.name}»: улучшение до ур. ${next} началось`, 'Не удалось начать улучшение')}
            className="btn-blue !w-full sm:!w-auto !px-5 !py-1.5 !text-xs self-start disabled:opacity-50">
            Улучшить до ур. {next}
          </button>
        </div>
      )}
      <button type="button" disabled={busy || frozen} onClick={() => setDemolishing(true)}
        className="self-start flex items-center gap-1.5 text-xs text-white/45 hover:text-site-red disabled:opacity-40 transition-colors">
        <Trash2 size={14} />Снести комнату
      </button>
      {demolishing && (
        <ConfirmDialog
          title="Снести комнату"
          message={`«${room.name}» будет снесена вместе со всеми её постами. Потраченные ${forms.name.toLowerCase()} и материалы не возвращаются.`}
          confirmLabel="Снести"
          danger
          onCancel={() => setDemolishing(false)}
          onConfirm={() => {
            setDemolishing(false);
            void act(() => demolishRoom(house.id, room.id, characterId), `«${room.name}» снесена`, 'Не удалось снести комнату');
          }}
        />
      )}
    </div>
  );
};

/** A new room on a free place: the types the place allows, their level-1 price, a name. */
export const BuildRoomForm = ({ house, cell, characterId, costs, atHouse, frozen, busy, act }: OwnerActionProps & { cell: PlanCell }) => {
  const { format } = useCurrency();
  const types = ROOM_TYPES.filter((t) => cell.allowed_types.includes(t));
  const [type, setType] = useState<RoomType | null>(types[0] ?? null);
  const [name, setName] = useState(types[0] ? ROOM_TYPE_LABEL[types[0]] : '');

  if (!type) return <p className="text-white/50 text-sm">Здесь нельзя построить ни одну комнату.</p>;

  const changeType = (t: RoomType) => {
    // Keep a name the owner typed; replace only the default one.
    if (!name.trim() || ROOM_TYPES.some((x) => ROOM_TYPE_LABEL[x] === name.trim())) setName(ROOM_TYPE_LABEL[t]);
    setType(t);
  };

  const build = () => {
    const trimmed = name.trim();
    if (!trimmed) {
      toast.error('Введите название комнаты');
      return;
    }
    void act(() => buildRoom(house.id, characterId, type, trimmed, cell.id), `Стройка «${trimmed}» началась`,
      'Не удалось начать стройку');
  };

  const cost = costs ? findCost(costs, type, 1) : null;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <span className={LABEL}>Что построить</span>
        <div className="grid grid-cols-1 min-[420px]:grid-cols-2 gap-2">
          {types.map((t) => {
            const Icon = ROOM_TYPE_ICON[t];
            const perk = levelPerk(t, 1);
            const typeCost = costs ? findCost(costs, t, 1) : null;
            return (
              <button key={t} type="button" onClick={() => changeType(t)}
                className={`chip-outline rounded-card px-3 py-2 text-left flex items-start gap-2 min-w-0 ${t === type ? 'chip-outline-active' : ''}`}>
                <Icon size={15} className="shrink-0 mt-0.5" />
                <span className="flex flex-col gap-0.5 min-w-0">
                  <span className="text-sm leading-tight break-words">{ROOM_TYPE_LABEL[t]}</span>
                  {perk && <span className="text-[10px] text-white/50 leading-tight break-words">{perk}</span>}
                  {costs && (
                    <span className="text-[10px] text-gold/80 leading-tight">
                      {typeCost ? format(typeCost.gold) : 'цена не задана'}
                    </span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </div>
      <p className="text-white/55 text-xs leading-relaxed">{roomTypeHint(type)}</p>
      <div className="flex flex-col gap-1">
        <span className="text-white/45 text-[11px]">
          Стоимость (ур. 1{levelPerk(type, 1) ? `, ${levelPerk(type, 1)}` : ''}):
        </span>
        {costs ? <CostView cost={cost} /> : <span className="text-white/30 text-xs">Загрузка стоимости...</span>}
      </div>
      <label className="flex flex-col gap-1.5">
        <span className={LABEL}>Название</span>
        <input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} className={FIELD} />
      </label>
      <button type="button" onClick={build} disabled={busy || !atHouse || !cost || frozen}
        className="btn-blue !w-full sm:!w-auto !px-6 self-start disabled:opacity-50">
        {busy ? 'Подождите...' : 'Построить'}
      </button>
    </div>
  );
};
