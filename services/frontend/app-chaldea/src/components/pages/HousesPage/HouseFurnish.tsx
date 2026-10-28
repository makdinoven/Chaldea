import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import toast from 'react-hot-toast';
import { Armchair, MapPin, Moon } from 'lucide-react';
import {
  placeFurniture,
  removeFurniture,
  FURNITURE_GROUP_LABEL,
  ROOM_TYPE_LABEL,
  type ActingCharacter,
  type FurnitureGroup,
  type House,
} from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import type { InventoryItem } from '../../../redux/slices/profileSlice';
import { furnitureBonusText, furnitureFitsRoom, itemFurnitureBonus } from '../../../utils/furniture';
import { FurnitureIcon } from './FurnitureIcon';

interface HouseFurnishProps {
  house: House;
  /** The owner's acting entry (carries where the owner stands). */
  owner: ActingCharacter;
  onChanged: () => void;
}

const ACTION_BTN =
  'shrink-0 px-3 py-1.5 rounded-[9px] border text-[11px] font-medium transition-colors duration-200 ease-site whitespace-nowrap disabled:opacity-40 disabled:hover:bg-transparent';

/** What one furniture group does, for the room header line. */
const GROUP_FURNITURE_HINT: Record<FurnitureGroup, string> = {
  hall: 'украшения — их видят гости',
  bedroom: 'крепче сон',
  storage: 'больше ячеек',
  workshop: 'больше опыта и удвоений профессии',
};

/**
 * FEAT-180 stage 3 — the owner furnishes built rooms with furniture items from
 * the bag. A room holds as many pieces as its level; each piece gives its room
 * a bonus (hall pieces only decorate). Needs the owner awake at the house.
 */
const HouseFurnish = ({ house, owner, onChanged }: HouseFurnishProps) => {
  const characterId = owner.character?.id ?? null;
  const [bag, setBag] = useState<InventoryItem[] | null>(null);
  const [busy, setBusy] = useState(false);

  const loadBag = useCallback(async () => {
    if (characterId == null) return;
    try {
      const { data } = await axios.get<InventoryItem[]>(`/inventory/${characterId}/items`);
      setBag(data);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось загрузить сумку хозяина'));
      setBag([]);
    }
  }, [characterId]);

  useEffect(() => {
    void loadBag();
  }, [loadBag]);

  const atHouse = owner.location_id != null && owner.location_id === house.location_id;
  const asleep = owner.asleep_room_id != null;
  const reading = owner.reading_room_id != null;
  const canAct = atHouse && !asleep && !reading && characterId != null;
  const hasTrophyHall = house.rooms.some((r) => r.room_type === 'trophy_hall');

  const act = async (action: () => Promise<unknown>, ok: string, fail: string) => {
    setBusy(true);
    try {
      await action();
      toast.success(ok);
      onChanged();
      await loadBag();
    } catch (e) {
      toast.error(apiErrorMessage(e, fail));
    } finally {
      setBusy(false);
    }
  };

  const furnitureInBag = (bag ?? []).filter((row) => row.item.item_type === 'furniture');
  // Gardens and the bath take no furniture (stage 6a).
  const furnishable = house.rooms.flatMap((room) => (room.furniture_group ? [{ room, group: room.furniture_group }] : []));

  return (
    <div className="flex flex-col gap-5">
      <section className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 p-4 sm:p-5 flex flex-col gap-2">
        <h2 className="gold-text text-sm font-medium uppercase tracking-[0.08em] flex items-center gap-2">
          <Armchair size={15} />Обстановка
        </h2>
        <p className="text-white/50 text-xs leading-relaxed">
          Расставляйте мебель из сумки хозяина. В комнату помещается столько предметов, каков её уровень.
          Мебель спальни делает сон крепче, кладовой (подходит и для погреба) — добавляет ячеек, мастерской —
          усиливает профессию любой мастерской (кузницы, лаборатории, кухни…), а гостиную она просто украшает.
          Гостевая берёт мебель спальни. В огород, оранжерею, пасеку, баню, библиотеку, святилище и круг возвращения
          мебель не ставят. Убранная мебель возвращается в сумку.
        </p>
        {hasTrophyHall && (
          <p className="text-white/50 text-xs leading-relaxed">
            Элитные трофеи вешают в самом трофейном зале: выберите его на плане дома.
          </p>
        )}
        {!atHouse && (
          <p className="flex items-center gap-1.5 text-gold-light text-xs bg-gold/10 border border-gold-dark/30 rounded-card px-3 py-2">
            <MapPin size={13} className="shrink-0" />
            <span>
              Дойдите до дома, чтобы расставлять мебель:{' '}
              <Link to={`/location/${house.location_id}`} className="site-link">{house.location_name ?? 'локация дома'}</Link>
            </span>
          </p>
        )}
        {atHouse && asleep && (
          <p className="flex items-center gap-1.5 text-gold-light text-xs bg-gold/10 border border-gold-dark/30 rounded-card px-3 py-2">
            <Moon size={13} className="shrink-0" />Проснитесь, чтобы расставлять мебель.
          </p>
        )}
        {atHouse && !asleep && reading && (
          <p className="flex items-center gap-1.5 text-gold-light text-xs bg-gold/10 border border-gold-dark/30 rounded-card px-3 py-2">
            <Moon size={13} className="shrink-0" />Закончите чтение, чтобы расставлять мебель.
          </p>
        )}
      </section>

      {furnishable.length === 0 && (
        <p className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] p-4 text-white/60 text-sm">
          В доме пока нет комнат, куда можно поставить мебель.
        </p>
      )}

      {furnishable.map(({ room, group }) => {
        const placed = room.furniture ?? [];
        const built = room.level >= 1;
        const slots = room.furniture_slots ?? room.level;
        const free = Math.max(0, slots - placed.length);
        const fitting = furnitureInBag.filter((row) => furnitureFitsRoom(row.item, room));
        return (
          <article key={room.id}
            className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] p-3 sm:p-4 flex flex-col gap-3">
            <div className="flex items-center gap-x-2 gap-y-1 flex-wrap">
              <span className="text-white text-sm font-medium break-words">{room.name}</span>
              <span className="text-gold text-[11px] uppercase tracking-[0.06em]">{ROOM_TYPE_LABEL[room.room_type]}</span>
              {built && (
                <span className={`px-2 py-0.5 rounded-full border text-[11px] ${
                  free > 0 ? 'border-gold-dark/50 text-gold-light' : 'border-white/15 text-white/55'
                }`}>
                  Мебель: {placed.length}/{slots}
                </span>
              )}
              <span className="text-white/35 text-[11px]">{GROUP_FURNITURE_HINT[group]}</span>
            </div>

            {!built ? (
              <p className="text-white/45 text-xs">Комната ещё строится — мебель можно будет поставить после стройки.</p>
            ) : (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {placed.map((piece) => (
                    <div key={piece.id} className="flex items-center gap-3 p-2.5 rounded-card bg-white/[0.03] border border-white/[0.06] min-w-0">
                      <FurnitureIcon name={piece.name} image={piece.image} rarity={piece.rarity} />
                      <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                        <span className="text-white text-[13px] font-medium truncate">{piece.name}</span>
                        <span className="text-gold-light/80 text-[11px] truncate">{furnitureBonusText(group, piece)}</span>
                      </div>
                      <button type="button" disabled={busy || !canAct}
                        title={!atHouse ? 'Дойдите до дома, чтобы расставлять мебель' : undefined}
                        onClick={() => characterId != null && void act(
                          () => removeFurniture(house.id, room.id, piece.id, characterId),
                          `«${piece.name}» убрана в сумку`, 'Не удалось убрать мебель')}
                        className={`${ACTION_BTN} border-white/20 text-white/70 hover:bg-white/10`}>
                        Убрать
                      </button>
                    </div>
                  ))}
                  {Array.from({ length: free }, (_, i) => (
                    <div key={`free-${i}`}
                      className="flex items-center gap-3 p-2.5 rounded-card border border-dashed border-white/10 text-white/35 text-xs">
                      <div className="item-cell item-cell-empty !w-11 !h-11 shrink-0" />
                      Свободное место
                    </div>
                  ))}
                </div>

                <div className="flex flex-col gap-2 pt-2 border-t border-white/[0.06]">
                  <span className="text-white/45 text-[11px] uppercase tracking-[0.06em]">Поставить из сумки</span>
                  {free === 0 && (
                    <p className="text-white/45 text-xs">Улучшите комнату, чтобы поставить больше.</p>
                  )}
                  {bag == null && <span className="text-white/30 text-xs">Загрузка сумки...</span>}
                  {bag != null && fitting.length === 0 && (
                    <p className="text-white/35 text-xs italic">
                      В сумке нет мебели группы «{FURNITURE_GROUP_LABEL[group]}».
                    </p>
                  )}
                  {fitting.length > 0 && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {fitting.map((row) => (
                        <div key={row.id} className="flex items-center gap-3 p-2.5 rounded-card bg-white/[0.03] border border-white/[0.06] min-w-0">
                          <div className="relative shrink-0">
                            <FurnitureIcon name={row.item.name} image={row.item.image} rarity={row.item.item_rarity} />
                            {row.quantity > 1 && (
                              <span className="absolute -bottom-1 -right-1 z-10 min-w-[18px] h-[18px] flex items-center justify-center text-[10px] font-medium text-white bg-site-bg rounded-full border border-white/30 px-1">
                                {row.quantity}
                              </span>
                            )}
                          </div>
                          <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                            <span className="text-white text-[13px] font-medium truncate">{row.item.name}</span>
                            <span className="text-gold-light/80 text-[11px] truncate">
                              {furnitureBonusText(group, itemFurnitureBonus(row.item))}
                            </span>
                          </div>
                          <button type="button" disabled={busy || !canAct || free === 0}
                            title={!atHouse ? 'Дойдите до дома, чтобы расставлять мебель'
                              : free === 0 ? 'Улучшите комнату, чтобы поставить больше' : undefined}
                            onClick={() => characterId != null && void act(
                              () => placeFurniture(house.id, room.id, characterId, row.id),
                              `«${row.item.name}» поставлена в «${room.name}»`, 'Не удалось поставить мебель')}
                            className={`${ACTION_BTN} border-gold/40 text-gold hover:bg-gold/15`}>
                            Поставить
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            )}
          </article>
        );
      })}
    </div>
  );
};

export default HouseFurnish;
