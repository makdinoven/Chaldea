import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Armchair, Hammer, Lock, MessageSquare, Plus } from 'lucide-react';
import {
  getBuildCosts,
  MAX_ROOM_LEVEL,
  planStats,
  ROOM_TYPE_LABEL,
  unlockCell,
  unlockLayer,
  type ActingCharacter,
  type BuildCost,
  type House,
  type HouseLayer,
  type HouseRoom,
  type PlanCell,
} from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import ConfirmDialog from '../LocationPage/ConfirmDialog';
import { BuildStatus, formatLeft, levelPerk, ROOM_TYPE_ICON, useTimeLeft } from './building';
import { AtHouseHint, BuildRoomForm, RoomBuildActions, useHouseAction } from './HouseBuild';
import FurnitureThumbs from './FurnitureIcon';
import { RoomTypeInfo } from './RoomFeatures';
import { ReturnCircleInfo } from './RoomBlessings';
import TrophyHall from './TrophyHall';
import { useCurrency } from '../../../hooks/useCurrency';

/*
  FEAT-180 stage 5 — the house plan: a grid per layer (floors, basement, yard)
  where every cell holds one room. The owner builds on free places, buys
  extension places and opens paid layers here; everyone else sees it read-only.
*/

interface HousePlanProps {
  house: House;
  /** The character the viewer acts through (owner or resident), if any. */
  acting: ActingCharacter | null;
  /** The owner's acting entry, when the viewer controls the owner. */
  ownerActing: ActingCharacter | null;
  frozen: boolean;
  onChanged: () => void;
}

type Selection = { kind: 'cell'; id: number } | { kind: 'room'; id: number } | null;

type Confirm = { kind: 'layer'; layer: HouseLayer; label: string; price: number } | { kind: 'cell'; cell: PlanCell; price: number };

const gold = (n: number) => n.toLocaleString('ru-RU');

/** «стройка · 3 ч» under a cell while a room is being built. */
const CellBuildBadge = ({ room, onDone }: { room: HouseRoom; onDone: () => void }) => {
  const left = useTimeLeft(room.upgrade_complete_at, onDone);
  return (
    <span className="hidden sm:block text-[10px] text-gold-light leading-tight truncate w-full">
      {left != null && left > 0 ? formatLeft(left) : 'стройка'}
    </span>
  );
};

const HousePlan = ({ house, acting, ownerActing, frozen, onChanged }: HousePlanProps) => {
  const navigate = useNavigate();
  const { plan } = house;
  const [layer, setLayer] = useState<HouseLayer>(() => plan.layers[0]?.layer ?? 'floor1');
  const [sel, setSel] = useState<Selection>(null);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [costs, setCosts] = useState<BuildCost[] | null>(null);
  const { busy, act } = useHouseAction(onChanged);
  const { format, forms } = useCurrency();

  const ownerId = ownerActing?.character?.id ?? null;
  const atHouse = ownerActing?.location_id != null && ownerActing.location_id === house.location_id;

  useEffect(() => {
    if (ownerId == null) return;
    getBuildCosts()
      .then(setCosts)
      .catch((e) => toast.error(apiErrorMessage(e, 'Не удалось загрузить стоимость стройки')));
  }, [ownerId]);

  const roomById = useMemo(() => new Map(house.rooms.map((r) => [r.id, r])), [house.rooms]);
  const cellById = useMemo(() => new Map(plan.cells.map((c) => [c.id, c])), [plan.cells]);
  const cellAt = useMemo(
    () => new Map(plan.cells.filter((c) => c.layer === layer).map((c) => [`${c.x}:${c.y}`, c])),
    [plan.cells, layer],
  );
  const homeless = house.rooms.filter((r) => r.cell_id == null || !cellById.has(r.cell_id));
  const layerInfo = plan.layers.find((l) => l.layer === layer) ?? plan.layers[0];
  const stats = planStats(plan);

  const roomOfCell = (cell: PlanCell): HouseRoom | null => {
    if (cell.room_id != null) return roomById.get(cell.room_id) ?? null;
    return house.rooms.find((r) => r.cell_id === cell.id) ?? null;
  };

  const clickCell = (cell: PlanCell) => {
    const room = roomOfCell(cell);
    // A visitor with nothing to do here goes straight into a room they may read.
    if (room && !acting && room.can_read && room.level >= 1) {
      navigate(`/houses/${house.id}/room/${room.id}`);
      return;
    }
    setSel({ kind: 'cell', id: cell.id });
  };

  const selectedCell = sel?.kind === 'cell' ? cellById.get(sel.id) ?? null : null;
  const selectedRoom = sel?.kind === 'room'
    ? roomById.get(sel.id) ?? null
    : selectedCell ? roomOfCell(selectedCell) : null;

  const runConfirm = (c: Confirm) => {
    setConfirm(null);
    if (ownerId == null) return;
    if (c.kind === 'layer') {
      void act(() => unlockLayer(house.id, c.layer, ownerId), `${c.label}: открыто`, 'Не удалось открыть');
    } else {
      void act(() => unlockCell(house.id, c.cell.id, ownerId), 'Место куплено', 'Не удалось купить место');
    }
  };

  const ownerProps = ownerId != null
    ? { house, characterId: ownerId, costs, atHouse, frozen, busy, act }
    : null;

  const renderCell = (x: number, y: number) => {
    const cell = cellAt.get(`${x}:${y}`);
    if (!cell) return <div key={`${x}:${y}`} aria-hidden className="aspect-square" />;
    const room = roomOfCell(cell);
    const selected = selectedCell?.id === cell.id;
    const ring = selected ? 'ring-2 ring-gold/80' : '';
    const base = `relative aspect-square min-w-0 rounded-[10px] flex flex-col items-center justify-center gap-0.5 p-1 text-center transition-colors duration-200 ease-site ${ring}`;

    if (room) {
      const Icon = ROOM_TYPE_ICON[room.room_type];
      const building = room.upgrade_to_level != null;
      return (
        <button key={cell.id} type="button" onClick={() => clickCell(cell)} title={`${room.name} — ${ROOM_TYPE_LABEL[room.room_type]}`}
          className={`${base} bg-white/[0.06] border border-gold-dark/40 hover:border-gold/70 ${room.level < 1 ? 'opacity-70' : ''}`}>
          {building && <Hammer size={11} className="absolute top-1 right-1 text-gold-light" />}
          {!room.is_open && <Lock size={10} className="absolute top-1 left-1 text-white/40" />}
          <Icon size={18} className="text-gold shrink-0" />
          <span className="hidden sm:block text-white text-[11px] leading-tight truncate w-full">{room.name}</span>
          <span className="text-white/55 text-[10px] leading-tight">{room.level >= 1 ? `ур. ${room.level}` : '—'}</span>
          {building && <CellBuildBadge room={room} onDone={onChanged} />}
        </button>
      );
    }
    if (!cell.unlocked) {
      const price = cell.kind === 'extension' && layerInfo?.unlocked ? plan.extension_price : null;
      return (
        <button key={cell.id} type="button" onClick={() => clickCell(cell)}
          title={cell.kind === 'extension' ? 'Пристройка' : 'Этаж закрыт'}
          className={`${base} bg-black/20 border border-white/10 text-white/40 hover:border-white/25`}>
          <Lock size={15} className="shrink-0" />
          {price != null && <span className="text-[10px] text-gold/80 leading-tight truncate w-full">{gold(price)}</span>}
        </button>
      );
    }
    return (
      <button key={cell.id} type="button" onClick={() => clickCell(cell)} title="Свободное место"
        className={`${base} border border-dashed border-white/25 hover:border-site-blue/60 text-white/40 hover:text-site-blue`}>
        {ownerId != null && !frozen && <Plus size={18} />}
      </button>
    );
  };

  const renderPanel = () => {
    if (selectedRoom) {
      return <RoomInfo house={house} room={selectedRoom} acting={acting} ownerActing={ownerActing} frozen={frozen} onChanged={onChanged}
        owner={ownerProps && <RoomBuildActions key={selectedRoom.id} room={selectedRoom} {...ownerProps} />} />;
    }
    if (!selectedCell) {
      return (
        <p className="text-white/50 text-sm">
          {ownerId != null
            ? 'Выберите клетку на плане: комнату — чтобы её улучшить, свободное место — чтобы построить новую.'
            : 'Выберите комнату на плане, чтобы узнать о ней больше.'}
        </p>
      );
    }
    const cellLayer = plan.layers.find((l) => l.layer === selectedCell.layer);
    if (cellLayer && !cellLayer.unlocked) {
      return <p className="text-white/55 text-sm">{cellLayer.label} пока закрыт — сначала его нужно открыть.</p>;
    }
    if (!selectedCell.unlocked) {
      const price = plan.extension_price;
      return (
        <div className="flex flex-col gap-3">
          <h3 className="gold-text text-sm font-medium uppercase tracking-[0.08em]">Пристройка</h3>
          <p className="text-white/55 text-sm">
            Место для ещё одной комнаты. {price != null ? `Стоит ${format(price)}.` : 'Цена не задана — обратитесь к администрации.'}
          </p>
          {ownerProps && price != null && (
            <>
              {!atHouse && <AtHouseHint house={house} what="покупать места" />}
              <button type="button" disabled={busy || !atHouse || frozen}
                onClick={() => setConfirm({ kind: 'cell', cell: selectedCell, price })}
                className="btn-blue !w-full sm:!w-auto !px-6 self-start disabled:opacity-50">
                Купить место за {format(price)}
              </button>
            </>
          )}
        </div>
      );
    }
    return (
      <div className="flex flex-col gap-3">
        <h3 className="gold-text text-sm font-medium uppercase tracking-[0.08em]">Свободное место</h3>
        {ownerProps ? (
          <>
            {!atHouse && <AtHouseHint house={house} />}
            <BuildRoomForm key={selectedCell.id} cell={selectedCell} {...ownerProps} />
          </>
        ) : (
          <p className="text-white/55 text-sm">
            Здесь можно построить: {selectedCell.allowed_types.map((t) => ROOM_TYPE_LABEL[t].toLowerCase()).join(', ')}.
          </p>
        )}
      </div>
    );
  };

  const rows = Array.from({ length: plan.height }, (_, y) => y);
  const cols = Array.from({ length: plan.width }, (_, x) => x);

  return (
    <div className="flex flex-col lg:flex-row gap-4 lg:gap-6 lg:items-start">
      <section className="w-full lg:w-[440px] shrink-0 flex flex-col gap-3">
        <div className="flex items-center gap-x-3 gap-y-2 flex-wrap">
          {plan.layers.length > 1 ? plan.layers.map((l) => (
            <button key={l.layer} type="button" onClick={() => { setLayer(l.layer); setSel(null); }}
              className={`chip-outline rounded-full px-3 py-1.5 text-xs font-medium flex items-center gap-1.5 ${l.layer === layer ? 'chip-outline-active' : ''}`}>
              {!l.unlocked && <Lock size={11} />}{l.label}
            </button>
          )) : (
            <span className="gold-text text-sm font-medium uppercase tracking-[0.08em]">{layerInfo?.label ?? 'План'}</span>
          )}
          <span className="text-white/45 text-xs ml-auto">Места: {stats.taken}/{stats.usable}{stats.total > stats.usable ? ` (всего ${stats.total})` : ''}</span>
        </div>

        {layerInfo && !layerInfo.unlocked && (
          <div className="flex flex-col gap-2 text-sm text-white/60 bg-white/[0.03] border border-white/[0.07] rounded-card p-3">
            <span className="flex items-center gap-1.5"><Lock size={14} className="shrink-0 text-gold" />{layerInfo.label} закрыт.</span>
            {ownerProps && layerInfo.unlock_price != null && (
              <>
                {!atHouse && <AtHouseHint house={house} what="открыть его" />}
                <button type="button" disabled={busy || !atHouse || frozen}
                  onClick={() => setConfirm({ kind: 'layer', layer: layerInfo.layer, label: layerInfo.label, price: layerInfo.unlock_price! })}
                  className="btn-blue !w-full sm:!w-auto !px-5 !py-1.5 !text-xs self-start disabled:opacity-50">
                  Открыть за {format(layerInfo.unlock_price)}
                </button>
              </>
            )}
          </div>
        )}

        <div className="grid gap-1.5 sm:gap-2 w-full"
          style={{ gridTemplateColumns: `repeat(${plan.width}, minmax(0, 1fr))`, maxWidth: `${plan.width * 6}rem` }}>
          {rows.map((y) => cols.map((x) => renderCell(x, y)))}
        </div>

        {homeless.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <span className="text-white/45 text-[11px] uppercase tracking-[0.06em]">Без места на плане</span>
            <div className="flex flex-wrap gap-1.5">
              {homeless.map((r) => (
                <button key={r.id} type="button" onClick={() => setSel({ kind: 'room', id: r.id })}
                  className={`chip-outline rounded-full px-3 py-1 text-xs ${sel?.kind === 'room' && sel.id === r.id ? 'chip-outline-active' : ''}`}>
                  {r.name}
                </button>
              ))}
            </div>
          </div>
        )}

        {ownerProps && (
          <p className="text-white/40 text-[11px] leading-relaxed">
            Каждая ступень стоит {forms.genitive} и материалов из сумки хозяина и строится сама. Комнаты растут до {MAX_ROOM_LEVEL}-го уровня:
            кладовая и погреб вмещают больше вещей, спальня даёт более крепкий сон, на огороде больше грядок, баня восстанавливает
            больше сил, а мастерская профессии даёт больший бонус своей профессии.
          </p>
        )}
      </section>

      <section className="flex-1 min-w-0 bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] p-4 sm:p-5">
        {renderPanel()}
      </section>

      {confirm && (
        <ConfirmDialog
          title={confirm.kind === 'layer' ? `Открыть: ${confirm.label}` : 'Купить место'}
          message={confirm.kind === 'layer'
            ? `${confirm.label} откроется за ${format(confirm.price)} — на нём можно будет строить комнаты.`
            : `Купить ещё одно место под комнату за ${format(confirm.price)}?`}
          confirmLabel={`Заплатить ${gold(confirm.price)}`}
          onCancel={() => setConfirm(null)}
          onConfirm={() => runConfirm(confirm)}
        />
      )}
    </div>
  );
};

interface RoomInfoProps {
  house: House;
  room: HouseRoom;
  acting: ActingCharacter | null;
  /** The owner's acting entry, when the viewer controls the owner (trophies). */
  ownerActing: ActingCharacter | null;
  frozen: boolean;
  onChanged: () => void;
  /** The owner's upgrade/demolish block, when the viewer is the owner. */
  owner: ReactNode;
}

/** A room picked on the plan: what it is, entering, sleep and — for the owner — building. */
const RoomInfo = ({ house, room, acting, ownerActing, frozen, onChanged, owner }: RoomInfoProps) => {
  const built = room.level >= 1;
  const trophyHall = room.room_type === 'trophy_hall';
  const Icon = ROOM_TYPE_ICON[room.room_type];
  const perk = built ? levelPerk(room.room_type, room.level) : null;
  return (
    <div className="flex flex-col gap-3">
      {room.image_url && (
        <div className="aspect-[16/8] rounded-card overflow-hidden bg-black/40">
          <img src={room.image_url} alt="" className="w-full h-full object-cover" />
        </div>
      )}
      <div className="flex items-center gap-2 flex-wrap">
        <Icon size={16} className="text-gold shrink-0" />
        <h3 className="text-white text-base font-medium break-words">{room.name}</h3>
        <span className="text-gold text-[11px] uppercase tracking-[0.06em]">{ROOM_TYPE_LABEL[room.room_type]}</span>
        {built && (
          <span className="px-2 py-0.5 rounded-full border border-gold-dark/50 text-gold-light text-[11px]">
            Ур. {room.level}{perk ? ` · ${perk}` : ''}
          </span>
        )}
        {!room.is_open && <span className="flex items-center gap-1 text-gold text-[11px]"><Lock size={12} />Закрыта</span>}
      </div>
      {room.description && <p className="text-white/60 text-sm whitespace-pre-wrap break-words">{room.description}</p>}
      <BuildStatus room={room} className="text-xs" />
      {!trophyHall && <FurnitureThumbs group={room.furniture_group} furniture={room.furniture ?? []} />}
      <RoomTypeInfo room={room} />
      <div className="flex items-center gap-x-3 gap-y-1 flex-wrap text-xs text-white/45">
        <span className="flex items-center gap-1"><MessageSquare size={13} />{room.posts_count}</span>
        {built && room.furniture_group != null && (
          <span className="flex items-center gap-1">
            <Armchair size={13} />Мебель: {(room.furniture ?? []).length}/{room.furniture_slots ?? room.level}
          </span>
        )}
        {!room.can_read && <span>Только для жильцов</span>}
      </div>
      {room.can_read && built && (
        <Link to={`/houses/${house.id}/room/${room.id}`} className="btn-line !w-full sm:!w-auto !px-6 !py-1.5 !text-sm self-start text-center">
          {acting?.room_id === room.id ? 'Вернуться в комнату' : 'Открыть комнату'}
        </Link>
      )}
      {/* Stage 7: sleep, bath, beds, reading and prayer live in the room itself (only there do they work). */}
      <ReturnCircleInfo room={room} />
      <TrophyHall houseId={house.id} houseLocationId={house.location_id} room={room} owner={ownerActing}
        houseBonus={house.trophy_bonus ?? 0} frozen={frozen} onChanged={onChanged} />
      {owner}
    </div>
  );
};

export default HousePlan;
