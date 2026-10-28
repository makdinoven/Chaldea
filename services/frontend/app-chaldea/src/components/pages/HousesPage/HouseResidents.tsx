import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { DoorOpen, UserMinus } from 'lucide-react';
import {
  addResident,
  inviteGuest,
  removeGuest,
  removeResident,
  ROOM_TYPE_LABEL,
  searchCharacters,
  updateResident,
  type House,
  type HouseChar,
  type HouseResident,
} from '../../../api/houses';
import { formatDayTime } from './HouseBuffs';
import { apiErrorMessage } from '../../../api/errors';
import ConfirmDialog from '../LocationPage/ConfirmDialog';
import { FIELD } from '../EpisodesPage/EpisodeFormModal';
import CharAvatar from './CharAvatar';

interface HouseResidentsProps {
  house: House;
  /** The viewer's owning character, when the viewer owns the house. */
  ownerCharacterId: number | null;
  onChanged: () => void;
}

interface Confirm {
  title: string;
  message: string;
  label: string;
  action: () => Promise<unknown>;
  done: string;
}

interface ResidentRowProps {
  house: House;
  resident: HouseResident;
  ownerCharacterId: number | null;
  /** The viewer's own character lives here under this row. */
  isMine: boolean;
  /** This resident inherits the house (stage 4). */
  isHeir: boolean;
  onAsk: (confirm: Confirm) => void;
  onChanged: () => void;
}

const sameSet = (a: number[], b: number[]) => a.length === b.length && a.every((x) => b.includes(x));

/** One resident: the owner ticks rooms and storage rights; the resident may move out. */
const ResidentRow = ({ house, resident, ownerCharacterId, isMine, isHeir, onAsk, onChanged }: ResidentRowProps) => {
  const [rooms, setRooms] = useState<number[]>(resident.room_ids);
  const [canTake, setCanTake] = useState(resident.can_take);
  const [canPut, setCanPut] = useState(resident.can_put);
  const [saving, setSaving] = useState(false);
  const manage = ownerCharacterId != null;

  useEffect(() => {
    setRooms(resident.room_ids);
    setCanTake(resident.can_take);
    setCanPut(resident.can_put);
  }, [resident]);

  const dirty = !sameSet(rooms, resident.room_ids) || canTake !== resident.can_take || canPut !== resident.can_put;
  const name = resident.character?.name ?? `Персонаж #${resident.id}`;

  const save = async () => {
    if (ownerCharacterId == null) return;
    setSaving(true);
    try {
      await updateResident(house.id, resident.id, {
        character_id: ownerCharacterId,
        room_ids: rooms,
        can_take: canTake,
        can_put: canPut,
      });
      toast.success('Права жильца сохранены');
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить права'));
    } finally {
      setSaving(false);
    }
  };

  const toggleRoom = (roomId: number) =>
    setRooms((cur) => (cur.includes(roomId) ? cur.filter((x) => x !== roomId) : [...cur, roomId]));

  const allowed = house.rooms.filter((r) => resident.room_ids.includes(r.id));

  return (
    <article className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] p-4 flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <CharAvatar src={resident.character?.avatar} />
        <p className="text-white text-sm flex-1 min-w-0 flex items-center flex-wrap gap-x-2 gap-y-1">
          <span className="truncate min-w-0">{name}{isMine && <span className="text-white/40"> (ваш персонаж)</span>}</span>
          {isHeir && (
            <span className="px-2 py-0.5 rounded-full border border-gold/50 text-gold text-[10px] uppercase tracking-[0.06em] whitespace-nowrap">
              наследник
            </span>
          )}
        </p>
        {manage && !isMine && (
          <button type="button" title="Выселить"
            className="w-8 h-8 flex items-center justify-center rounded-[8px] text-white/40 hover:text-site-red transition-colors"
            onClick={() => onAsk({
              title: 'Выселить жильца',
              message: `${name} больше не сможет заходить в дом. Его посты останутся.`,
              label: 'Выселить',
              action: () => removeResident(house.id, resident.id, ownerCharacterId!),
              done: 'Жилец выселен',
            })}>
            <UserMinus size={16} />
          </button>
        )}
        {isMine && resident.character && (
          <button type="button" className="text-white/50 hover:text-site-red text-sm shrink-0"
            onClick={() => onAsk({
              title: 'Съехать',
              message: `${name} перестанет быть жильцом этого дома. Вернуться можно будет только по приглашению хозяина.`,
              label: 'Съехать',
              action: () => removeResident(house.id, resident.id, resident.character!.id),
              done: 'Вы съехали',
            })}>
            Съехать
          </button>
        )}
      </div>

      {manage ? (
        <>
          <div className="flex flex-col gap-1.5">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Может заходить и писать</span>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-1.5">
              {house.rooms.map((room) => (
                <label key={room.id} className="flex items-center gap-2 cursor-pointer text-sm text-white/80 min-w-0">
                  <input type="checkbox" checked={rooms.includes(room.id)} onChange={() => toggleRoom(room.id)} className="accent-gold shrink-0" />
                  <span className="truncate">{room.name}</span>
                  <span className="text-white/35 text-xs shrink-0">{ROOM_TYPE_LABEL[room.room_type]}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-5">
            <label className="flex items-center gap-2 cursor-pointer text-sm text-white/80">
              <input type="checkbox" checked={canTake} onChange={(e) => setCanTake(e.target.checked)} className="accent-gold" />
              Может брать из кладовой
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm text-white/80">
              <input type="checkbox" checked={canPut} onChange={(e) => setCanPut(e.target.checked)} className="accent-gold" />
              Может класть в кладовую
            </label>
            <button type="button" onClick={() => void save()} disabled={!dirty || saving}
              className="btn-blue !w-full sm:!w-auto !px-5 !py-1.5 !text-xs sm:ml-auto disabled:opacity-40">
              {saving ? 'Сохранение...' : 'Сохранить'}
            </button>
          </div>
        </>
      ) : (
        <div className="flex flex-col gap-1 text-xs text-white/55">
          <span>Комнаты: {allowed.length ? allowed.map((r) => r.name).join(', ') : 'нет'}</span>
          <span>
            Кладовая: {[resident.can_take && 'может брать', resident.can_put && 'может класть'].filter(Boolean).join(', ') || 'нет доступа'}
          </span>
        </div>
      )}
    </article>
  );
};

/** Characters by name for the search box (debounced, from 2 letters). */
const useCharacterSearch = (enabled: boolean, query: string): HouseChar[] => {
  const [found, setFound] = useState<HouseChar[]>([]);
  useEffect(() => {
    if (!enabled || query.trim().length < 2) {
      setFound([]);
      return undefined;
    }
    const t = setTimeout(() => {
      searchCharacters(query.trim())
        .then(setFound)
        .catch((e) => toast.error(apiErrorMessage(e, 'Поиск не удался')));
    }, 300);
    return () => clearTimeout(t);
  }, [enabled, query]);
  return found;
};

/** Residents of a house; the owner adds, configures and evicts them. Stage 6b: guests too. */
const HouseResidents = ({ house, ownerCharacterId, onChanged }: HouseResidentsProps) => {
  const [query, setQuery] = useState('');
  const [guestQuery, setGuestQuery] = useState('');
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const manage = ownerCharacterId != null;
  const found = useCharacterSearch(manage, query);
  const foundGuests = useCharacterSearch(manage, guestQuery);
  const myResidentIds = new Set(
    house.acting.filter((a) => !a.is_owner && !a.is_guest).map((a) => a.character?.id).filter((x): x is number => x != null),
  );
  const myGuests = house.acting.filter((a) => a.is_guest && a.character);
  const guests = house.guests ?? [];
  const guestIds = new Set(guests.map((g) => g.character?.id));
  const taken = new Set([house.owner?.id, ...house.residents.map((r) => r.character?.id)]);
  const hasGuestRooms = house.rooms.some((r) => r.room_type === 'guest_room');
  const isMember = manage || myResidentIds.size > 0;

  const run = async (job: () => Promise<unknown>, done: string, failed: string) => {
    try {
      await job();
      toast.success(done);
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e, failed));
    }
  };

  return (
    <div className="flex flex-col gap-5">
      {manage && (
        <section className="flex flex-col gap-2">
          <input value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Поселить персонажа: начните вводить имя" className={FIELD} />
          <p className="text-white/35 text-xs">Новый жилец сразу получает доступ к гостиным; остальные комнаты и кладовую отметьте ниже.</p>
          {found.length > 0 && (
            <div className="bg-black/60 border border-white/10 rounded-card divide-y divide-white/5">
              {found.map((c) => (
                <div key={c.id} className="flex items-center gap-3 px-3 py-2">
                  <CharAvatar src={c.avatar} size="w-7 h-7" />
                  <span className="text-white text-sm flex-1 truncate">{c.name}</span>
                  {taken.has(c.id) ? (
                    <span className="text-white/40 text-xs">уже живёт здесь</span>
                  ) : (
                    <button type="button" className="text-site-blue hover:text-white text-xs"
                      onClick={() => void run(async () => {
                        await addResident(house.id, ownerCharacterId!, c.id);
                        setQuery('');
                      }, `${c.name} — теперь жилец`, 'Не удалось поселить')}>
                      Поселить
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {isMember && house.residents.length === 0 ? (
        <p className="text-white/40 text-sm italic">
          {manage ? 'В доме пока живёте только вы — поселите друзей через поиск.' : 'Других жильцов нет.'}
        </p>
      ) : house.residents.length > 0 && (
        <div className="flex flex-col gap-3">
          {house.residents.map((r) => (
            <ResidentRow
              key={r.id}
              house={house}
              resident={r}
              ownerCharacterId={ownerCharacterId}
              isMine={r.character != null && myResidentIds.has(r.character.id)}
              isHeir={r.character != null && house.heir?.id === r.character.id}
              onAsk={setConfirm}
              onChanged={onChanged}
            />
          ))}
        </div>
      )}

      {/* ── Guests (stage 6b) ── */}
      {(isMember || myGuests.length > 0) && (
        <section className="flex flex-col gap-3 pt-2 border-t border-white/[0.07]">
          <h2 className="gold-text text-sm font-medium uppercase tracking-[0.08em] flex items-center gap-2">
            <DoorOpen size={15} />Гости
          </h2>
          <p className="text-white/45 text-xs leading-relaxed">
            Гости хозяина могут заходить в гостевые комнаты и спать там. В остальные комнаты и кладовую их не пускают.
            {!hasGuestRooms && ' В доме пока нет гостевой — её можно построить на плане.'}
          </p>

          {myGuests.map((a) => (
            <div key={a.character!.id}
              className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/30 p-3 sm:p-4 flex flex-col sm:flex-row sm:items-center gap-3">
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <CharAvatar src={a.character!.avatar} />
                <span className="text-white text-sm truncate">{a.character!.name}</span>
                <span className="px-2 py-0.5 rounded-full border border-site-blue/50 text-site-blue text-[10px] uppercase tracking-[0.06em] shrink-0">
                  гость
                </span>
              </div>
              <button type="button" className="btn-line !w-full sm:!w-auto !px-5 !py-1.5 !text-xs shrink-0"
                onClick={() => setConfirm({
                  title: 'Уйти из гостей',
                  message: `${a.character!.name} больше не сможет заходить в гостевые комнаты этого дома (если спит здесь — проснётся).`,
                  label: 'Уйти',
                  action: () => removeGuest(house.id, a.character!.id, a.character!.id),
                  done: 'Вы больше не гость этого дома',
                })}>
                Уйти из гостей
              </button>
            </div>
          ))}

          {manage && (
            <div className="flex flex-col gap-2">
              <input value={guestQuery} onChange={(e) => setGuestQuery(e.target.value)}
                placeholder="Пригласить гостя: начните вводить имя" className={FIELD} />
              {foundGuests.length > 0 && (
                <div className="bg-black/60 border border-white/10 rounded-card divide-y divide-white/5">
                  {foundGuests.map((c) => (
                    <div key={c.id} className="flex items-center gap-3 px-3 py-2">
                      <CharAvatar src={c.avatar} size="w-7 h-7" />
                      <span className="text-white text-sm flex-1 truncate">{c.name}</span>
                      {taken.has(c.id) ? (
                        <span className="text-white/40 text-xs">живёт здесь</span>
                      ) : guestIds.has(c.id) ? (
                        <span className="text-white/40 text-xs">уже гость</span>
                      ) : (
                        <button type="button" className="text-site-blue hover:text-white text-xs"
                          onClick={() => void run(async () => {
                            await inviteGuest(house.id, ownerCharacterId!, c.id);
                            setGuestQuery('');
                          }, `${c.name} — теперь гость дома`, 'Не удалось пригласить')}>
                          Пригласить
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {isMember && (guests.length === 0 ? (
            <p className="text-white/40 text-sm italic">Гостей нет.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {guests.map((g) => g.character && (
                <div key={g.character.id}
                  className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] p-3 flex items-center gap-3 min-w-0">
                  <CharAvatar src={g.character.avatar} />
                  <span className="flex flex-col min-w-0 flex-1">
                    <span className="text-white text-sm truncate">{g.character.name}</span>
                    <span className="text-white/40 text-[11px]">приглашён(а) {formatDayTime(g.invited_at)}</span>
                  </span>
                  {manage && (
                    <button type="button" title="Отказать в гостеприимстве"
                      className="w-8 h-8 flex items-center justify-center rounded-[8px] text-white/40 hover:text-site-red transition-colors shrink-0"
                      onClick={() => setConfirm({
                        title: 'Отказать гостю',
                        message: `${g.character!.name} больше не сможет заходить в гостевые комнаты (если спит здесь — проснётся).`,
                        label: 'Отказать',
                        action: () => removeGuest(house.id, g.character!.id, ownerCharacterId!),
                        done: 'Гость больше не приглашён',
                      })}>
                      <UserMinus size={16} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          ))}
        </section>
      )}

      {confirm && (
        <ConfirmDialog
          title={confirm.title}
          message={confirm.message}
          confirmLabel={confirm.label}
          danger
          onCancel={() => setConfirm(null)}
          onConfirm={() => {
            const c = confirm;
            setConfirm(null);
            void run(c.action, c.done, 'Не получилось');
          }}
        />
      )}
    </div>
  );
};

export default HouseResidents;
