import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { BookOpen, Orbit, PenLine, Pickaxe, HeartPulse, type LucideIcon } from 'lucide-react';
import {
  HOUSE_BUFF_HOURS,
  LIBRARY_PERCENT_PER_HOUR,
  percentText,
  prayAtShrine,
  SHRINE_BLESSING_LABEL,
  SHRINE_BLESSINGS,
  SHRINE_COOLDOWN_HOURS,
  startReading,
  stopReading,
  stopReadingText,
  type ShrineBlessing,
} from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import { useAppDispatch } from '../../../redux/store';
import { getMe } from '../../../redux/slices/userSlice';
import { parseServerDate } from '../../../utils/serverDate';
import { InfoTooltip } from '../../CommonComponents/InfoTooltip';
import { formatLeft, formatLeftShort, useTimeLeft } from './building';
import { buffText, formatDayTime } from './HouseBuffs';
import { blockReason, type ActorProps, type FeatureRoom } from './RoomFeatures';
import RoomAction from './RoomAction';

/*
  FEAT-180 stage 6b — the library (sit down to read, stop and get the XP
  blessing), the shrine (one of three blessings once a day) and the return
  circle (what a home teleport scroll does here). Used by the plan panel and
  the room page.
*/

/** How often the «читает уже …» line re-renders. */
const ELAPSED_TICK_MS = 30_000;

/** Milliseconds since `iso`, ticking; null without a start. */
const useElapsed = (iso: string | null | undefined): number | null => {
  const start = parseServerDate(iso ?? null)?.getTime() ?? null;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (start == null) return undefined;
    const t = setInterval(() => setNow(Date.now()), ELAPSED_TICK_MS);
    return () => clearInterval(t);
  }, [start]);
  return start == null ? null : Math.max(0, now - start);
};

/** Icon of each shrine blessing button. */
const SHRINE_BLESSING_ICON: Record<ShrineBlessing, LucideIcon> = {
  gathering_xp: Pickaxe,
  regen: HeartPulse,
  post_xp: PenLine,
};

/** What each blessing raises — the start of its tooltip. */
const SHRINE_BLESSING_HINT: Record<ShrineBlessing, string> = {
  gathering_xp: 'Опыт за сбор ресурсов',
  regen: 'Скорость восстановления',
  post_xp: 'Опыт за посты',
};

// --- Library ---

/** «Читать» / «Закончить чтение» in a library, the cap of its level and the running blessing. */
export const LibraryControl = ({ room, acting, houseLocationId, frozen, onChanged }: ActorProps) => {
  const dispatch = useAppDispatch();
  const [busy, setBusy] = useState(false);
  const elapsed = useElapsed(acting?.reading_since);
  if (room.room_type !== 'library' || room.level < 1) return null;

  const character = acting?.character ?? null;
  const cap = room.library_cap ?? null;
  const readingHere = acting?.reading_room_id === room.id;
  const readingElsewhere = acting?.reading_room_id != null && !readingHere;
  const allowed = acting != null && acting.room_ids.includes(room.id);
  const blessing = (acting?.buffs ?? []).find((b) => b.source === 'library') ?? null;

  const refresh = () => {
    onChanged();
    // The lock banner comes from /users/me.
    void dispatch(getMe());
  };

  const read = async () => {
    if (!character) return;
    setBusy(true);
    try {
      await startReading(room.id, character.id);
      toast.success(`${character.name} садится читать`);
      refresh();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сесть за книги'));
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    if (!character) return;
    setBusy(true);
    try {
      const r = await stopReading(character.id);
      if (r.value > 0) toast.success(stopReadingText(r));
      else toast(stopReadingText(r));
      refresh();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось закончить чтение'));
    } finally {
      setBusy(false);
    }
  };

  const reason = acting && !readingHere && !readingElsewhere ? blockReason(room, acting, houseLocationId, frozen) : null;
  const capLine = cap != null ? `Предел этой библиотеки: +${percentText(cap)} % ко всему опыту.` : null;
  const how = `Каждый полный час чтения — +${LIBRARY_PERCENT_PER_HOUR} % ко всему опыту на ${HOUSE_BUFF_HOURS} ч после окончания. `
    + 'Пока персонаж читает, он ничем другим не занят.';
  const hint = (
    <span className="flex flex-col gap-1">
      <span>{how}</span>
      {capLine && <span className="text-gold-light">{capLine}</span>}
      {blessing && <span className="text-gold-light">Сейчас: {buffText(blessing)}</span>}
    </span>
  );
  if (!character) return null;

  if (readingHere || readingElsewhere) {
    return (
      <RoomAction icon={BookOpen} tone="active" label={busy ? 'Закрываем книгу...' : 'Закончить чтение'}
        sub={readingHere
          ? `читает ${elapsed != null ? formatLeftShort(elapsed) : ''}`.trim()
          : 'в другой библиотеке'}
        disabled={busy} onClick={() => void stop()}
        hint={readingHere
          ? <span className="flex flex-col gap-1"><span>{character.name} читает с {formatDayTime(acting?.reading_since)}{elapsed != null ? ` (${formatLeft(elapsed)})` : ''}.</span>{hint}</span>
          : `${character.name} читает в другой библиотеке.`} />
    );
  }
  const notAllowed = !allowed ? 'Хозяин не пускал этого персонажа сюда — читать нельзя.' : null;
  return (
    <RoomAction icon={BookOpen} label={busy ? 'Садимся...' : 'Читать'}
      sub={cap != null ? `до +${percentText(cap)} %` : null}
      disabled={busy || notAllowed != null || reason != null} reason={notAllowed ?? reason} hint={hint}
      onClick={() => void read()} />
  );
};

// --- Shrine ---

/** Three blessings to pick from once per 24 h, the cooldown and the running shrine blessing. */
export const ShrineControl = ({ room, acting, houseLocationId, frozen, onChanged }: ActorProps) => {
  const dispatch = useAppDispatch();
  const [busy, setBusy] = useState<ShrineBlessing | null>(null);
  const nextAt = acting?.pray_next_at ?? null;
  const left = useTimeLeft(nextAt, onChanged);
  if (room.room_type !== 'shrine' || room.level < 1) return null;

  const character = acting?.character ?? null;
  const value = room.shrine_bonus ?? 0;
  const blessing = (acting?.buffs ?? []).find((b) => b.source === 'shrine') ?? null;
  const allowed = acting != null && acting.room_ids.includes(room.id);
  const cooling = nextAt != null && left != null && left > 0;
  const reason = acting ? blockReason(room, acting, houseLocationId, frozen) : null;

  const pray = async (kind: ShrineBlessing) => {
    if (!character) return;
    setBusy(kind);
    try {
      const r = await prayAtShrine(room.id, character.id, kind);
      toast.success(`Святилище благословляет: ${SHRINE_BLESSING_LABEL[r.blessing].toLowerCase()} +${percentText(r.value)} % на 24 ч`);
      onChanged();
      void dispatch(getMe());
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Святилище не ответило'));
    } finally {
      setBusy(null);
    }
  };

  if (!character) return null;
  const notAllowed = !allowed ? 'Хозяин не пускал этого персонажа сюда — молиться нельзя.' : null;
  const coolReason = cooling ? `Святилище ещё не услышит вас — снова можно через ${formatLeft(left!)}.` : null;
  const why = notAllowed ?? coolReason ?? reason;
  const hint = (kind: ShrineBlessing) => (
    <span className="flex flex-col gap-1">
      <span>{SHRINE_BLESSING_HINT[kind]} +{percentText(value)} % на {HOUSE_BUFF_HOURS} ч.</span>
      <span>Молиться можно раз в {SHRINE_COOLDOWN_HOURS} ч; новая молитва заменяет прежнее благословение святилища.</span>
      {blessing && <span className="text-gold-light">Сейчас: {buffText(blessing)}</span>}
    </span>
  );
  return (
    <>
      {SHRINE_BLESSINGS.map((kind) => (
        <RoomAction key={kind} icon={SHRINE_BLESSING_ICON[kind]}
          label={busy === kind ? 'Молитва...' : SHRINE_BLESSING_LABEL[kind]}
          sub={cooling ? `через ${formatLeftShort(left!)}` : `+${percentText(value)} %`}
          tone={blessing?.kind === kind ? 'active' : 'default'}
          disabled={busy != null || why != null} reason={why} hint={hint(kind)}
          onClick={() => void pray(kind)} />
      ))}
    </>
  );
};

// --- Return circle ---

/** The keep chance of the circle's level and how the scrolls work. */
export const ReturnCircleInfo = ({ room }: { room: FeatureRoom }) => {
  if (room.room_type !== 'return_circle' || room.level < 1) return null;
  const chance = room.circle_keep_chance ?? 0;
  return (
    <span className="inline-flex items-center gap-1.5 self-start max-w-full px-3 py-1.5 rounded-full border border-gold-dark/40 bg-gold/[0.05] text-gold-light text-xs">
      <Orbit size={13} className="shrink-0" />
      <span className="break-words">{chance > 0 ? `Свиток сохраняется: ${percentText(chance)} %` : 'Свиток расходуется всегда'}</span>
      <InfoTooltip size={13} label="Как работает круг возвращения"
        content={'Прочтите «Свиток возвращения» в инвентаре — он перенесёт персонажа в локацию этого дома. '
          + 'Хозяин и жильцы, которых пустили в круг, могут возвращаться сюда. '
          + (chance > 0 ? `С шансом ${percentText(chance)} % свиток не тратится.` : 'Свиток при этом расходуется.')} />
    </span>
  );
};
