import { useState } from 'react';
import toast from 'react-hot-toast';
import { Moon, Sun } from 'lucide-react';
import { isSleepRoom, sleepInRoom, wakeUp, type ActingCharacter, type HouseRoom } from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import { useAppDispatch } from '../../../redux/store';
import { getMe } from '../../../redux/slices/userSlice';
import { GO_TO_ROOM_HINT } from './RoomFeatures';
import RoomAction from './RoomAction';

interface SleepControlProps {
  room: HouseRoom;
  /** The character the viewer acts through here. */
  acting: ActingCharacter | null;
  /** Location of the house — sleeping needs the character standing there. */
  houseLocationId: number;
  onChanged: () => void;
  className?: string;
  /** The house is frozen for an unpaid tax — nobody may lie down. */
  frozen?: boolean;
}

const formatFactor = (f: number) => `×${f.toLocaleString('ru-RU', { maximumFractionDigits: 1 })}`;

/**
 * FEAT-180 — «Лечь спать» / «Проснуться» in a bedroom (stage 6b: or a guest room). While asleep the
 * character is activity-locked everywhere until woken; rest goes faster by the
 * bedroom's `sleep_factor`. Nothing is rendered for rooms that are not built
 * bedrooms or for characters the owner didn't let in.
 */
const SleepControl = ({ room, acting, houseLocationId, onChanged, className = '', frozen = false }: SleepControlProps) => {
  const dispatch = useAppDispatch();
  const [busy, setBusy] = useState(false);
  const character = acting?.character;
  if (!isSleepRoom(room.room_type) || !acting || !character) return null;

  const asleepHere = acting.asleep_room_id === room.id;
  const asleepElsewhere = acting.asleep_room_id != null && !asleepHere;
  const allowed = acting.room_ids.includes(room.id);
  if (!asleepHere && (!allowed || room.level < 1)) return null;

  const run = async (action: () => Promise<unknown>, ok: string, fail: string) => {
    setBusy(true);
    try {
      await action();
      toast.success(ok);
      onChanged();
      // The lock banner and rest status come from /users/me.
      void dispatch(getMe());
    } catch (e) {
      toast.error(apiErrorMessage(e, fail));
    } finally {
      setBusy(false);
    }
  };

  const wake = () => void run(() => wakeUp(character.id), `${character.name} просыпается`, 'Не удалось проснуться');

  const kind = room.room_type === 'guest_room' ? 'гостевой' : 'спальне';
  const factor = room.sleep_factor != null ? formatFactor(room.sleep_factor) : null;
  const hint = `Во сне восстановление ${factor ?? 'быстрее'}, но персонаж ничего не может делать, пока не проснётся.`;

  if (asleepHere || asleepElsewhere) {
    return (
      <RoomAction icon={Sun} label={busy ? 'Пробуждение...' : 'Проснуться'} tone="active" onClick={wake} disabled={busy}
        sub={asleepHere ? `${character.name} спит здесь` : `${character.name} спит в другой комнате`}
        hint={asleepHere ? `${character.name} спит в этой ${kind}. ${hint}` : `${character.name} спит в другой комнате дома.`}
        className={className} />
    );
  }

  const here = acting.location_id != null && acting.location_id === houseLocationId;
  // Stage 7: lying down needs the character standing in this very room.
  const inRoom = acting.room_id === room.id;
  const reading = acting.reading_room_id != null;
  const reason = frozen
    ? 'Дом заморожен за неуплату налога — спать нельзя.'
    : reading
    ? 'Персонаж читает в библиотеке — сначала закончите чтение.'
    : !here
    ? 'Дойдите до дома, чтобы лечь спать.'
    : !inRoom
    ? GO_TO_ROOM_HINT
    : null;
  return (
    <RoomAction icon={Moon} label={busy ? 'Укладываемся...' : 'Лечь спать'} sub={factor ? `сон ${factor}` : null}
      disabled={busy || reason != null} reason={reason} hint={hint} className={className}
      onClick={() => void run(() => sleepInRoom(room.id, character.id), `${character.name} засыпает`, 'Не удалось лечь спать')} />
  );
};

export default SleepControl;
