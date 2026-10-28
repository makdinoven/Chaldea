import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { Trophy, X } from 'lucide-react';
import {
  percentText,
  placeFurniture,
  removeFurniture,
  TROPHY_PERCENT_CAP,
  TROPHY_PERCENT_PER_PIECE,
  type ActingCharacter,
  type HouseRoom,
} from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import type { InventoryItem } from '../../../redux/slices/profileSlice';
import { isEliteTrophy } from '../../../utils/houseItems';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import { InfoTooltip, WithTooltip } from '../../CommonComponents/InfoTooltip';
import { FurnitureIcon } from './FurnitureIcon';
import RoomAction, { ACTION_BAR } from './RoomAction';

/*
  FEAT-180 stage 6b — a trophy hall: elite trophies hang on its slots (the
  furniture endpoints, only items flagged `is_elite_trophy`), each +1 % battle
  XP to the owner and the residents, at most 15 % in all.
*/

interface TrophyHallProps {
  houseId: number;
  houseLocationId: number;
  room: HouseRoom;
  /** The owner's acting entry when the viewer controls the owner (hangs and removes). */
  owner: ActingCharacter | null;
  /** The house's total trophy bonus (fraction). */
  houseBonus: number;
  frozen: boolean;
  onChanged: () => void;
}

interface PickerProps {
  characterId: number;
  busy: boolean;
  onPick: (row: InventoryItem) => void;
  onClose: () => void;
}

/** The owner's elite trophies in the bag. */
const TrophyPicker = ({ characterId, busy, onPick, onClose }: PickerProps) => {
  const [bag, setBag] = useState<InventoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    axios.get<InventoryItem[]>(`/inventory/${characterId}/items`)
      .then(({ data }) => alive && setBag(data.filter((row) => isEliteTrophy(row.item))))
      .catch((e) => {
        if (!alive) return;
        const msg = apiErrorMessage(e, 'Не удалось загрузить сумку хозяина');
        setError(msg);
        toast.error(msg);
      });
    return () => {
      alive = false;
    };
  }, [characterId]);

  return (
    <ModalShell open onClose={onClose} title="Повесить трофей" icon={<Trophy size={18} className="text-gold" />}
      size="md" dismissible={!busy}>
      {error && <p className="text-site-red text-sm">{error}</p>}
      {!error && bag == null && <div className="w-7 h-7 border-4 border-white/30 border-t-gold rounded-full animate-spin mx-auto" />}
      {bag != null && bag.length === 0 && (
        <p className="text-white/60 text-sm">
          В сумке хозяина нет элитных трофеев. Их добывают с особых противников; обычные трофеи сюда не вешают.
        </p>
      )}
      {bag != null && bag.length > 0 && (
        <div className="flex flex-col gap-2">
          {bag.map((row) => (
            <button key={row.id} type="button" disabled={busy} onClick={() => onPick(row)}
              className="flex items-center gap-3 p-2.5 rounded-card border border-white/[0.08] bg-white/[0.03] hover:border-gold/50 hover:bg-gold/[0.06] text-left transition-colors duration-200 ease-site disabled:opacity-50 min-w-0">
              <FurnitureIcon name={row.item.name} image={row.item.image} rarity={row.item.item_rarity} />
              <span className="flex flex-col gap-0.5 min-w-0 flex-1">
                <span className="text-white text-sm leading-tight break-words">
                  {row.item.name}{row.quantity > 1 && <span className="text-white/45"> ×{row.quantity}</span>}
                </span>
                <span className="text-gold-light/80 text-[11px]">+1 % к опыту за бои</span>
              </span>
              <Trophy size={16} className="text-gold shrink-0" />
            </button>
          ))}
        </div>
      )}
    </ModalShell>
  );
};

/** Slots of a trophy hall with the hung trophies; the owner hangs and takes them down. */
const TrophyHall = ({ houseId, houseLocationId, room, owner, houseBonus, frozen, onChanged }: TrophyHallProps) => {
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState(false);
  const [removing, setRemoving] = useState(false);
  const ownerId = owner?.character?.id ?? null;

  const act = useCallback(async (action: () => Promise<unknown>, ok: string, fail: string) => {
    setBusy(true);
    try {
      await action();
      toast.success(ok);
      onChanged();
      return true;
    } catch (e) {
      toast.error(apiErrorMessage(e, fail));
      return false;
    } finally {
      setBusy(false);
    }
  }, [onChanged]);

  if (room.room_type !== 'trophy_hall' || room.level < 1) return null;

  const slots = room.trophy_slots ?? room.furniture_slots ?? 0;
  const hung = room.furniture ?? [];
  const free = Math.max(0, slots - hung.length);
  const atHouse = owner?.location_id != null && owner.location_id === houseLocationId;
  const ownerReason = !owner ? null
    : frozen ? 'Дом заморожен за неуплату налога.'
    : !atHouse ? 'Дойдите до дома, чтобы вешать трофеи.'
    : owner.asleep_room_id != null ? 'Проснитесь, чтобы вешать трофеи.'
    : owner.reading_room_id != null ? 'Закончите чтение, чтобы вешать трофеи.'
    : null;

  const fullReason = free === 0 ? 'Все места заняты — улучшите зал, чтобы повесить больше.' : null;

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center gap-2 flex-wrap">
        <Trophy size={13} className="text-gold shrink-0" />
        <span className="text-white/60 text-[11px] uppercase tracking-[0.06em]">Трофеи</span>
        <span className="text-white/40 text-[11px]">{hung.length}/{slots}</span>
        <InfoTooltip size={12} label="Как работают трофеи"
          content={`Здесь вешают элитные трофеи: каждый даёт хозяину и жильцам +${TROPHY_PERCENT_PER_PIECE} % опыта за бои, всего не больше ${TROPHY_PERCENT_CAP} %. Вешает и снимает хозяин.`} />
        <span className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-site-blue/40 text-site-blue text-[11px]">
          +{percentText(houseBonus)} % за бои
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        {hung.map((piece) => (
          <WithTooltip key={piece.id} tapToggle className="block"
            content={
              <span className="flex flex-col gap-0.5">
                <span className="text-white">{piece.name}</span>
                <span className="text-gold-light">+{TROPHY_PERCENT_PER_PIECE} % к опыту за бои</span>
                {piece.description && <span>{piece.description}</span>}
              </span>
            }>
            <span className="relative flex items-center justify-center w-14 h-14 rounded-card border border-gold-dark/40 bg-gold/[0.05]">
              <FurnitureIcon name={piece.name} image={piece.image} rarity={piece.rarity} title="" />
            </span>
          </WithTooltip>
        ))}
        {Array.from({ length: free }, (_, i) => (
          <WithTooltip key={`free-${i}`} tapToggle className="block" content="Свободное место для трофея">
            <span className="flex items-center justify-center w-14 h-14 rounded-card border border-dashed border-white/15 text-white/25">
              <Trophy size={16} />
            </span>
          </WithTooltip>
        ))}
      </div>
      {ownerId != null && (
        <div className={ACTION_BAR}>
          <RoomAction icon={Trophy} label="Повесить трофей" sub={`свободно: ${free}`}
            disabled={busy || fullReason != null || ownerReason != null} reason={ownerReason ?? fullReason}
            hint="Выберите элитный трофей из сумки хозяина." onClick={() => setPicking(true)} />
          {hung.length > 0 && (
            <RoomAction icon={X} label="Снять трофей" sub="вернуть в сумку"
              disabled={busy || ownerReason != null} reason={ownerReason}
              hint="Трофей вернётся в сумку хозяина." onClick={() => setRemoving(true)} />
          )}
        </div>
      )}
      {picking && ownerId != null && (
        <TrophyPicker characterId={ownerId} busy={busy} onClose={() => setPicking(false)}
          onPick={(row) => void act(() => placeFurniture(houseId, room.id, ownerId, row.id),
            `«${row.item.name}» висит в «${room.name}»`, 'Не удалось повесить трофей')
            .then((ok) => ok && setPicking(false))} />
      )}
      {removing && ownerId != null && (
        <ModalShell open onClose={() => setRemoving(false)} title="Снять трофей" icon={<Trophy size={18} className="text-gold" />}
          size="md" dismissible={!busy}>
          <div className="flex flex-col gap-2">
            {hung.map((piece) => (
              <button key={piece.id} type="button" disabled={busy}
                onClick={() => void act(() => removeFurniture(houseId, room.id, piece.id, ownerId),
                  `«${piece.name}» снят и убран в сумку`, 'Не удалось снять трофей')
                  .then((ok) => ok && setRemoving(false))}
                className="flex items-center gap-3 p-2.5 rounded-card border border-white/[0.08] bg-white/[0.03] hover:border-gold/50 hover:bg-gold/[0.06] text-left transition-colors duration-200 ease-site disabled:opacity-50 min-w-0">
                <FurnitureIcon name={piece.name} image={piece.image} rarity={piece.rarity} />
                <span className="text-white text-sm leading-tight break-words flex-1 min-w-0">{piece.name}</span>
                <X size={16} className="text-white/50 shrink-0" />
              </button>
            ))}
          </div>
        </ModalShell>
      )}
    </div>
  );
};

export default TrophyHall;
