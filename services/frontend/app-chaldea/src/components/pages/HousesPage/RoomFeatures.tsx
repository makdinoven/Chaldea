import { useEffect, useState, type ReactNode } from 'react';
import toast from 'react-hot-toast';
import { Bath, Check, Clock, Hammer, Package, Sprout } from 'lucide-react';
import {
  BATH_COOLDOWN_HOURS,
  BATH_RESTORE_PERCENT_BY_LEVEL,
  GARDEN_ROOM_PLACE,
  batheInRoom,
  getRoomSeeds,
  harvestBed,
  isGardenRoom,
  isProfessionRoom,
  plantSeed,
  PROFESSION_NAME_BY_SLUG,
  roomProfessionName,
  type ActingCharacter,
  type GardenBed,
  type HarvestResult,
  type RoomType,
  type SeedOption,
} from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import { useAppDispatch } from '../../../redux/store';
import { getMe } from '../../../redux/slices/userSlice';
import { cellsWord } from '../../../utils/furniture';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import { parseServerDate } from '../../../utils/serverDate';
import { InfoTooltip, WithTooltip } from '../../CommonComponents/InfoTooltip';
import RoomAction, { TipBody } from './RoomAction';
import { bedsWord, formatBuildHours, formatLeft, formatLeftShort, levelPerk, roomTypeHint, useTimeLeft } from './building';

/*
  FEAT-180 stage 6a — what a room does by its type: the explanation with the
  profession / storage numbers, the beds of a garden, greenhouse or apiary
  (plant, watch them grow, harvest) and the bath. Used by the plan panel and
  the room page.
*/

/** The room fields these blocks need (a house room or the room page's room). */
export interface FeatureRoom {
  id: number;
  room_type: RoomType;
  level: number;
  beds_total?: number | null;
  beds?: GardenBed[] | null;
  storage_stacks?: number | null;
  profession_slug?: string | null;
  /** Stage 6b (fractions / counts of the current level; null for other types). */
  library_cap?: number | null;
  shrine_bonus?: number | null;
  trophy_slots?: number | null;
  circle_keep_chance?: number | null;
}

export interface ActorProps {
  room: FeatureRoom;
  /** The character the viewer acts through here, if any. */
  acting: ActingCharacter | null;
  /** Location of the house — actions need the character standing there. */
  houseLocationId: number;
  frozen: boolean;
  onChanged: () => void;
}

/** Stage 7: a room function seen from another room (or from outside the house). */
export const GO_TO_ROOM_HINT = 'Перейдите в эту комнату, чтобы этим воспользоваться.';

/**
 * Why the acting character can't use the room now (null = it can):
 * frozen house, room under construction, asleep, away from the house,
 * not standing in this room.
 */
export const blockReason = (room: FeatureRoom, acting: ActingCharacter, houseLocationId: number, frozen: boolean) => {
  if (frozen) return 'Дом заморожен за неуплату налога.';
  if (room.level < 1) return 'Комната ещё строится.';
  if (acting.asleep_room_id != null) return 'Персонаж спит — сначала проснитесь.';
  if (acting.reading_room_id != null) return 'Персонаж читает — сначала закончите чтение.';
  if (acting.location_id == null || acting.location_id !== houseLocationId) return 'Дойдите до дома, чтобы пользоваться комнатой.';
  // Stage 7: room functions work only for the character standing in this very room.
  if (acting.room_id !== room.id) return GO_TO_ROOM_HINT;
  return null;
};

/** The type's explanation plus its numbers (profession, stacks) under the room header. */
export const RoomTypeInfo = ({ room }: { room: FeatureRoom }) => {
  const hint = roomTypeHint(room.room_type);
  const profession = room.profession_slug
    ? PROFESSION_NAME_BY_SLUG[room.profession_slug] ?? room.profession_slug
    : roomProfessionName(room.room_type);
  const perk = room.level >= 1 ? levelPerk(room.room_type, room.level) : null;
  if (!hint && !profession && room.storage_stacks == null) return null;
  return (
    <div className="flex flex-col gap-1.5 text-xs">
      {hint && <p className="text-white/55 leading-relaxed">{hint}</p>}
      <div className="flex items-center gap-x-4 gap-y-1 flex-wrap">
        {isProfessionRoom(room.room_type) && profession && (
          <span className="flex items-center gap-1.5 text-gold-light">
            <Hammer size={13} className="shrink-0" />
            Профессия: {profession}{perk ? ` · сейчас ${perk}` : ''}
          </span>
        )}
        {room.storage_stacks != null && (
          <span className="flex items-center gap-1.5 text-gold-light">
            <Package size={13} className="shrink-0" />
            {room.room_type === 'cellar' ? 'Добавляет к кладовой' : 'Вмещает'} {room.storage_stacks} {cellsWord(room.storage_stacks)}
          </span>
        )}
      </div>
    </div>
  );
};

/** The type's explanation and the current level's numbers — the «i» tooltip of the room's panel. */
export const roomInfoContent = (room: FeatureRoom): ReactNode => {
  const hint = roomTypeHint(room.room_type);
  const profession = room.profession_slug
    ? PROFESSION_NAME_BY_SLUG[room.profession_slug] ?? room.profession_slug
    : roomProfessionName(room.room_type);
  const perk = room.level >= 1 ? levelPerk(room.room_type, room.level) : null;
  const lines: string[] = [];
  if (perk) lines.push(`Сейчас, ур. ${room.level}: ${perk}.`);
  if (isProfessionRoom(room.room_type) && profession) lines.push(`Профессия: ${profession}.`);
  if (room.storage_stacks != null) {
    lines.push(`${room.room_type === 'cellar' ? 'Добавляет к кладовой' : 'Вмещает'} ${room.storage_stacks} ${cellsWord(room.storage_stacks)}.`);
  }
  if (!hint && lines.length === 0) return null;
  return (
    <span className="flex flex-col gap-1.5">
      {hint && <span>{hint}</span>}
      {lines.map((l) => <span key={l} className="text-gold-light">{l}</span>)}
    </span>
  );
};

// --- Garden beds ---

const harvestToast = (r: HarvestResult) => {
  const name = r.item?.name ?? 'урожай';
  const parts = [`+${r.added} ${name}`];
  if (r.xp_awarded > 0) parts.push(`+${r.xp_awarded} опыта травничества`);
  let text = parts.join(', ');
  if (r.added < r.quantity) text += ` (в сумку поместилось ${r.added} из ${r.quantity})`;
  if (r.rank_up) text += ' — новый ранг травничества!';
  return text;
};

interface BedTileProps {
  bed: GardenBed;
  canHarvest: boolean;
  /** Why the character can't act here now (frozen, not in the room…). */
  reason: string | null;
  busy: boolean;
  onHarvest: () => void;
  onGrown: () => void;
}

const BedItem = ({ image, name, size = 'w-9 h-9' }: { image: string | null | undefined; name: string; size?: string }) => (
  <span className={`${size} rounded-[8px] overflow-hidden bg-black/40 border border-white/10 shrink-0 flex items-center justify-center`}>
    {image ? <img src={image} alt={name} className="w-full h-full object-cover" /> : <Sprout size={16} className="text-white/40" />}
  </span>
);

/** Shared box of a bed tile (planted, ready or empty). */
const TILE = 'w-full min-h-[92px] flex flex-col items-center justify-center gap-1.5 p-2 rounded-card border text-center transition-colors duration-200 ease-site';

/** A planted bed: what grows, a thin progress bar and the time left — or a gold «Собрать». */
const BedTile = ({ bed, canHarvest, reason, busy, onHarvest, onGrown }: BedTileProps) => {
  const left = useTimeLeft(bed.ready ? null : bed.ready_at, onGrown);
  const ready = bed.ready || (left != null && left <= 0);
  const resultName = bed.result?.name ?? 'Урожай';
  const start = parseServerDate(bed.planted_at)?.getTime() ?? null;
  const end = parseServerDate(bed.ready_at)?.getTime() ?? null;
  const progress = ready ? 1 : start != null && end != null && end > start && left != null
    ? Math.min(1, Math.max(0, 1 - left / (end - start)))
    : 0;
  const harvestReason = !ready ? null
    : !canHarvest ? 'Выросло — собрать может тот, кто сажал, или хозяин.'
    : reason;
  const tip = (
    <TipBody reason={harvestReason}
      hint={
        <span className="flex flex-col gap-0.5">
          <span className="text-white">{resultName}{bed.quantity > 1 ? ` ×${bed.quantity}` : ''}</span>
          <span>Посажено: {bed.seed?.name ?? 'семя'}</span>
          {bed.planted_by && <span>Посадил(а): {bed.planted_by.name}</span>}
          {!ready && left != null && <span>Вырастет через {formatLeft(left)}</span>}
        </span>
      } />
  );
  const pics = (
    <span className="flex items-center gap-1">
      <BedItem image={bed.seed?.image} name={bed.seed?.name ?? 'Семя'} size="w-6 h-6" />
      <span className="text-white/35 text-[10px]">→</span>
      <BedItem image={bed.result?.image} name={resultName} size="w-8 h-8" />
    </span>
  );

  if (ready) {
    const disabled = busy || harvestReason != null;
    return (
      <WithTooltip content={tip} tapToggle={disabled} className="block min-w-0">
        <button type="button" disabled={disabled} onClick={onHarvest}
          className={`${TILE} border-gold/60 bg-gold/[0.08] hover:bg-gold/[0.14] shadow-[0_0_14px_rgba(240,217,92,0.15)] disabled:opacity-60 disabled:pointer-events-none`}>
          {pics}
          <span className="flex items-center gap-1 text-gold-light text-[11px] font-medium uppercase tracking-[0.04em]">
            <Check size={12} />{busy ? 'Сбор...' : 'Собрать'}
          </span>
        </button>
      </WithTooltip>
    );
  }
  return (
    <WithTooltip content={tip} tapToggle className="block min-w-0">
      <div className={`${TILE} border-white/[0.1] bg-white/[0.03]`}>
        {pics}
        <span className="w-full max-w-[96px] h-1 rounded-full bg-white/10 overflow-hidden">
          <span className="block h-full rounded-full bg-gradient-to-r from-gold-dark to-gold-light" style={{ width: `${Math.round(progress * 100)}%` }} />
        </span>
        <span className="flex items-center gap-1 text-white/55 text-[10.5px] leading-tight">
          <Clock size={11} className="shrink-0" />{left != null ? formatLeft(left) : 'Растёт'}
        </span>
      </div>
    </WithTooltip>
  );
};

interface SeedPickerProps {
  roomId: number;
  roomType: RoomType;
  characterId: number;
  bedNo: number;
  onClose: () => void;
  onPlanted: () => void;
}

/** Picks one of the acting character's seeds and plants it into the bed. */
const SeedPicker = ({ roomId, roomType, characterId, bedNo, onClose, onPlanted }: SeedPickerProps) => {
  const [seeds, setSeeds] = useState<SeedOption[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [planting, setPlanting] = useState(false);

  useEffect(() => {
    let alive = true;
    getRoomSeeds(roomId, characterId)
      .then((list) => alive && setSeeds(list))
      .catch((e) => {
        if (!alive) return;
        const msg = apiErrorMessage(e, 'Не удалось загрузить семена');
        setError(msg);
        toast.error(msg);
      });
    return () => {
      alive = false;
    };
  }, [roomId, characterId]);

  const plant = async (seed: SeedOption) => {
    setPlanting(true);
    try {
      await plantSeed(roomId, characterId, seed.inventory_item_id, bedNo);
      toast.success(`«${seed.name}» посажено — вырастет через ${formatBuildHours(seed.grow_hours)}`);
      onPlanted();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось посадить'));
    } finally {
      setPlanting(false);
    }
  };

  const what = roomType === 'apiary' ? 'Что поставить в улей' : 'Что посадить';
  return (
    <ModalShell open onClose={onClose} title={`${what} — ${roomType === 'apiary' ? 'улей' : 'грядка'} ${bedNo}`}
      icon={<Sprout size={18} className="text-gold" />} size="md" dismissible={!planting}>
      {error && <p className="text-site-red text-sm">{error}</p>}
      {!error && seeds == null && <div className="w-7 h-7 border-4 border-white/30 border-t-gold rounded-full animate-spin mx-auto" />}
      {seeds != null && seeds.length === 0 && (
        <p className="text-white/60 text-sm">
          В сумке нет семян, которые растут {isGardenRoom(roomType) ? GARDEN_ROOM_PLACE[roomType] : 'здесь'}.
        </p>
      )}
      {seeds != null && seeds.length > 0 && (
        <div className="flex flex-col gap-2">
          {seeds.map((seed) => (
            <button key={seed.inventory_item_id} type="button" disabled={planting} onClick={() => void plant(seed)}
              className="flex items-center gap-3 p-2.5 rounded-card border border-white/[0.08] bg-white/[0.03] hover:border-gold/50 hover:bg-gold/[0.06] text-left transition-colors duration-200 ease-site disabled:opacity-50 min-w-0">
              <BedItem image={seed.image} name={seed.name} />
              <span className="flex flex-col gap-0.5 min-w-0 flex-1">
                <span className="text-white text-sm leading-tight break-words">
                  {seed.name}<span className="text-white/45"> ×{seed.quantity}</span>
                </span>
                <span className="text-white/55 text-[11px] leading-tight break-words">
                  Вырастет: {seed.result?.name ?? 'урожай'}{seed.result_quantity > 1 ? ` ×${seed.result_quantity}` : ''}
                  {' '}· {formatBuildHours(seed.grow_hours)}
                  {seed.herbalism_xp > 0 ? ` · +${seed.herbalism_xp} опыта травничества` : ''}
                </span>
              </span>
              <Sprout size={16} className="text-gold shrink-0" />
            </button>
          ))}
        </div>
      )}
    </ModalShell>
  );
};

/**
 * Beds of a garden, greenhouse or apiary: planted ones with their countdown and
 * «Собрать», empty ones with «Посадить» for a character let into the room.
 */
export const GardenBeds = ({ room, acting, houseLocationId, frozen, onChanged }: ActorProps) => {
  const dispatch = useAppDispatch();
  const [busyBed, setBusyBed] = useState<number | null>(null);
  const [picking, setPicking] = useState<number | null>(null);
  if (!isGardenRoom(room.room_type) || room.level < 1) return null;

  const total = room.beds_total ?? 0;
  const byNo = new Map((room.beds ?? []).map((b) => [b.bed_no, b]));
  const character = acting?.character ?? null;
  const reason = acting ? blockReason(room, acting, houseLocationId, frozen) : null;
  const allowed = acting != null && acting.room_ids.includes(room.id);
  const word = (n: number) => bedsWord(room.room_type, n);

  const harvest = async (bed: GardenBed) => {
    if (!character) return;
    setBusyBed(bed.bed_no);
    try {
      const r = await harvestBed(room.id, character.id, bed.bed_no);
      toast.success(harvestToast(r));
      onChanged();
      void dispatch(getMe());
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось собрать урожай'));
    } finally {
      setBusyBed(null);
    }
  };

  const noun = room.room_type === 'apiary' ? 'улей' : 'грядка';
  const emptyReason = !character ? null
    : !allowed ? 'Хозяин не пускал этого персонажа сюда — сажать нельзя.'
    : reason;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Sprout size={13} className="text-gold shrink-0" />
        <span className="text-white/60 text-[11px] uppercase tracking-[0.06em]">
          {room.room_type === 'apiary' ? 'Ульи' : 'Грядки'}
        </span>
        <span className="text-white/40 text-[11px]">{byNo.size}/{total}</span>
        <InfoTooltip size={12} label="Как работают грядки"
          content={`Посаженное растёт само; собрать урожай может тот, кто сажал, или хозяин. Здесь ${total} ${word(total)}.`} />
      </div>
      {total === 0 && <p className="text-white/40 text-xs">Пока нет мест для посадки.</p>}
      <div className="grid grid-cols-2 min-[480px]:grid-cols-3 lg:grid-cols-4 gap-2">
        {Array.from({ length: total }, (_, i) => i + 1).map((no) => {
          const bed = byNo.get(no);
          if (bed) {
            const canHarvest = character != null && (acting!.is_owner || bed.planted_by?.id === character.id);
            return (
              <BedTile key={no} bed={bed} canHarvest={canHarvest} reason={reason}
                busy={busyBed === no} onHarvest={() => void harvest(bed)} onGrown={onChanged} />
            );
          }
          const disabled = !character || emptyReason != null;
          return (
            <WithTooltip key={no} tapToggle={disabled} className="block min-w-0"
              content={character
                ? <TipBody reason={emptyReason} hint={`${noun[0].toUpperCase()}${noun.slice(1)} ${no} пуст${room.room_type === 'apiary' ? '' : 'а'} — ${room.room_type === 'apiary' ? 'поставьте' : 'посадите'} что-нибудь из сумки.`} />
                : `Пустое место: ${noun} ${no}.`}>
              <button type="button" disabled={disabled} onClick={() => setPicking(no)}
                className={`${TILE} border-dashed border-white/20 text-white/55 hover:border-gold/60 hover:text-gold hover:bg-gold/[0.05] disabled:opacity-50 disabled:pointer-events-none`}>
                <Sprout size={20} className="shrink-0" />
                <span className="text-[11px] font-medium uppercase tracking-[0.04em]">{character ? 'Посадить' : 'Пусто'}</span>
              </button>
            </WithTooltip>
          );
        })}
      </div>
      {picking != null && character && (
        <SeedPicker roomId={room.id} roomType={room.room_type} characterId={character.id} bedNo={picking}
          onClose={() => setPicking(null)}
          onPlanted={() => {
            setPicking(null);
            onChanged();
          }} />
      )}
    </div>
  );
};

// --- Bath ---

/** «Попариться» once per 24 h: restores a share of health, mana, energy and stamina. */
export const BathControl = ({ room, acting, houseLocationId, frozen, onChanged }: ActorProps) => {
  const dispatch = useAppDispatch();
  const [busy, setBusy] = useState(false);
  const character = acting?.character ?? null;
  const nextAt = acting?.bath_next_at ?? null;
  const left = useTimeLeft(nextAt, onChanged);
  if (room.room_type !== 'bath' || room.level < 1 || !acting || !character) return null;
  if (!acting.room_ids.includes(room.id)) return null;

  const percent = BATH_RESTORE_PERCENT_BY_LEVEL[room.level] ?? 0;
  const cooling = nextAt != null && left != null && left > 0;
  const reason = blockReason(room, acting, houseLocationId, frozen);

  const bathe = async () => {
    setBusy(true);
    try {
      const r = await batheInRoom(room.id, character.id);
      const { health, mana, energy, stamina } = r.restored;
      toast.success(`${character.name} парится: здоровье +${health}, мана +${mana}, энергия +${energy}, выносливость +${stamina}`);
      onChanged();
      void dispatch(getMe());
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось попариться'));
    } finally {
      setBusy(false);
    }
  };

  const coolReason = cooling ? `Баня ещё не остыла — снова можно через ${formatLeft(left!)}.` : null;
  return (
    <RoomAction icon={Bath} label={busy ? 'Парится...' : 'Попариться'}
      sub={cooling ? `через ${formatLeftShort(left!)}` : `+${percent} %`}
      disabled={busy || cooling || reason != null} reason={coolReason ?? reason} onClick={() => void bathe()}
      hint={`Восстанавливает ${percent}% здоровья, маны, энергии и выносливости; раз в ${BATH_COOLDOWN_HOURS} ч.`} />
  );
};
