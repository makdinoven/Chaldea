import { useState } from 'react';
import { Eraser, Lock, MousePointer2, Plus, Square, Trash2 } from 'lucide-react';
import {
  HOUSE_LAYERS,
  LAYER_LABEL,
  layerRoomTypes,
  PLAN_GRID_MAX,
  PLAN_GRID_MIN,
  ROOM_TYPE_LABEL,
  type HouseLayer,
  type PlanCellKind,
  type PlotCellInput,
  type PlotDetail,
  type PlotKind,
  type PlotLayerInput,
  type PlotRoomInput,
  type RoomType,
} from '../../../api/houses';
import { FIELD, LABEL } from '../../pages/EpisodesPage/EpisodeFormModal';
import ImageField from '../../pages/EpisodesPage/ImageField';
import { ROOM_TYPE_ICON } from '../../pages/HousesPage/building';

/*
  FEAT-180 stage 5 — the admin's plan editor of a plot: grid size, layers (the
  first floor is always there and free; others may cost the owner gold to
  open), the places on each layer (open ones are usable at once, extensions
  the owner buys one by one) and, for a ready house, the template room in a
  place.
*/

export interface EditorCell {
  kind: PlanCellKind;
  /** Narrowed room types; empty = every type the layer allows. */
  allowed: RoomType[];
}

export interface EditorRoom {
  room_type: RoomType;
  name: string;
  description: string;
  image_url: string | null;
}

export interface EditorPlan {
  grid_w: number;
  grid_h: number;
  extension_price: number | null;
  /** On/off and the unlock price (null = free) of each layer; floor1 is always on and free. */
  layers: Record<HouseLayer, { on: boolean; price: number | null }>;
  /** Keyed by `layer:x:y`. */
  cells: Record<string, EditorCell>;
  rooms: Record<string, EditorRoom>;
}

const keyOf = (layer: HouseLayer, x: number, y: number) => `${layer}:${x}:${y}`;
const parseKey = (key: string) => {
  const [layer, x, y] = key.split(':');
  return { layer: layer as HouseLayer, x: Number(x), y: Number(y) };
};
const placeLabel = (key: string) => {
  const { layer, x, y } = parseKey(key);
  return `${LAYER_LABEL[layer]}, ряд ${y + 1}, место ${x + 1}`;
};

const emptyLayers = (): EditorPlan['layers'] => ({
  floor1: { on: true, price: null },
  floor2: { on: false, price: null },
  basement: { on: false, price: null },
  yard: { on: false, price: null },
});

const templateRoom = (type: RoomType): EditorRoom => ({
  room_type: type,
  name: ROOM_TYPE_LABEL[type],
  description: '',
  image_url: null,
});

/** A new plot: a 3×2 first floor with three open places and a hall, bedroom and storage. */
export const defaultPlan = (): EditorPlan => {
  const types: RoomType[] = ['hall', 'bedroom', 'storage'];
  const cells: EditorPlan['cells'] = {};
  const rooms: EditorPlan['rooms'] = {};
  types.forEach((t, x) => {
    cells[keyOf('floor1', x, 0)] = { kind: 'open', allowed: [] };
    rooms[keyOf('floor1', x, 0)] = templateRoom(t);
  });
  return { grid_w: 3, grid_h: 2, extension_price: null, layers: emptyLayers(), cells, rooms };
};

/** Fills the editor from GET /plots/{id}. */
export const planFromPlot = (d: PlotDetail): EditorPlan => {
  const layers = emptyLayers();
  d.plan.layers.forEach((l) => {
    layers[l.layer] = { on: true, price: l.layer === 'floor1' ? null : l.unlock_price };
  });
  const cells: EditorPlan['cells'] = {};
  const keyById = new Map<number, string>();
  d.plan.cells.forEach((c) => {
    const key = keyOf(c.layer, c.x, c.y);
    keyById.set(c.id, key);
    const all = layerRoomTypes(c.layer);
    const narrowed = all.some((t) => !c.allowed_types.includes(t));
    cells[key] = { kind: c.kind, allowed: narrowed ? all.filter((t) => c.allowed_types.includes(t)) : [] };
  });
  const rooms: EditorPlan['rooms'] = {};
  d.rooms.forEach((r) => {
    const key = r.cell_id != null ? keyById.get(r.cell_id) : undefined;
    if (key) rooms[key] = { room_type: r.room_type, name: r.name, description: r.description, image_url: r.image_url };
  });
  return {
    grid_w: d.plan.width || d.grid_w,
    grid_h: d.plan.height || d.grid_h,
    extension_price: d.plan.extension_price ?? d.extension_price,
    layers,
    cells,
    rooms,
  };
};

const isFree = (plan: EditorPlan, layer: HouseLayer) => layer === 'floor1' || plan.layers[layer].price == null;
const effectiveTypes = (cell: EditorCell, layer: HouseLayer) => (cell.allowed.length ? cell.allowed : layerRoomTypes(layer));
const liveCells = (plan: EditorPlan) =>
  Object.entries(plan.cells).filter(([key]) => {
    const { layer, x, y } = parseKey(key);
    return plan.layers[layer].on && x < plan.grid_w && y < plan.grid_h;
  });

/** Same rules as the server; returns a Russian error or null. */
export const validatePlan = (plan: EditorPlan, kind: PlotKind): string | null => {
  const cells = liveCells(plan);
  if (cells.length === 0) return 'Добавьте на план хотя бы одно место';
  if (cells.some(([, c]) => c.kind === 'extension') && plan.extension_price == null) {
    return 'На плане есть пристройки — укажите цену пристройки';
  }
  if (!cells.some(([key, c]) => c.kind === 'open' && isFree(plan, parseKey(key).layer))) {
    return 'Нужно хотя бы одно открытое место на бесплатном слое (например, на 1 этаже)';
  }
  if (kind === 'empty') return null;
  // Rooms on switched-off layers or outside the grid are dropped on save.
  const liveKeys = new Set(cells.map(([k]) => k));
  const rooms = Object.entries(plan.rooms).filter(([k]) => liveKeys.has(k));
  if (rooms.length === 0) return 'Поставьте на план хотя бы одну комнату';
  for (const [key, room] of rooms) {
    const cell = plan.cells[key];
    const { layer } = parseKey(key);
    if (cell.kind !== 'open' || !isFree(plan, layer)) {
      return `Комната «${room.name}»: шаблонные комнаты ставятся только на открытые места бесплатных слоёв (${placeLabel(key)})`;
    }
    if (!effectiveTypes(cell, layer).includes(room.room_type)) {
      return `${placeLabel(key)}: тип «${ROOM_TYPE_LABEL[room.room_type]}» здесь не разрешён`;
    }
    if (!room.name.trim()) return `${placeLabel(key)}: у комнаты должно быть название`;
  }
  return null;
};

/** The plan part of the admin plot body. */
export const planToBody = (plan: EditorPlan, kind: PlotKind) => {
  const layers: PlotLayerInput[] = HOUSE_LAYERS.filter((l) => plan.layers[l].on).map((l) => ({
    layer: l,
    unlock_price: isFree(plan, l) ? null : plan.layers[l].price,
  }));
  const live = liveCells(plan);
  const cells: PlotCellInput[] = live.map(([key, c]) => ({ ...parseKey(key), kind: c.kind, allowed_types: c.allowed }));
  const rooms: PlotRoomInput[] = kind === 'empty'
    ? []
    : Object.entries(plan.rooms)
      .filter(([key]) => live.some(([k]) => k === key))
      .map(([key, r]) => ({ ...r, name: r.name.trim(), ...parseKey(key) }));
  return { grid_w: plan.grid_w, grid_h: plan.grid_h, extension_price: plan.extension_price, layers, cells, rooms };
};

type Mode = 'select' | 'open' | 'extension' | 'erase';

const MODES: { mode: Mode; label: string; Icon: typeof Plus }[] = [
  { mode: 'select', label: 'Выбор', Icon: MousePointer2 },
  { mode: 'open', label: 'Открытое', Icon: Square },
  { mode: 'extension', label: 'Пристройка', Icon: Lock },
  { mode: 'erase', label: 'Стереть', Icon: Eraser },
];

const clampGrid = (v: number) => Math.min(PLAN_GRID_MAX, Math.max(PLAN_GRID_MIN, Math.round(v) || PLAN_GRID_MIN));
const priceOrNull = (v: string) => (v.trim() === '' || Number(v) <= 0 ? null : Math.round(Number(v)));

interface PlotPlanEditorProps {
  plan: EditorPlan;
  onChange: (updater: (p: EditorPlan) => EditorPlan) => void;
  kind: PlotKind;
}

const PlotPlanEditor = ({ plan, onChange, kind }: PlotPlanEditorProps) => {
  const [layer, setLayer] = useState<HouseLayer>('floor1');
  const [mode, setMode] = useState<Mode>('select');
  const [selected, setSelected] = useState<string | null>(null);
  const shownLayer: HouseLayer = plan.layers[layer].on ? layer : 'floor1';

  const setSize = (side: 'grid_w' | 'grid_h', value: number) =>
    onChange((p) => {
      const next = { ...p, [side]: clampGrid(value) };
      // Places outside the new grid are dropped with their rooms.
      const inside = (key: string) => {
        const { x, y } = parseKey(key);
        return x < next.grid_w && y < next.grid_h;
      };
      next.cells = Object.fromEntries(Object.entries(p.cells).filter(([k]) => inside(k)));
      next.rooms = Object.fromEntries(Object.entries(p.rooms).filter(([k]) => inside(k)));
      return next;
    });

  const setLayerState = (l: HouseLayer, patch: Partial<{ on: boolean; price: number | null }>) =>
    onChange((p) => ({ ...p, layers: { ...p.layers, [l]: { ...p.layers[l], ...patch } } }));

  const setCell = (key: string, cell: EditorCell | null) =>
    onChange((p) => {
      const cells = { ...p.cells };
      const rooms = { ...p.rooms };
      if (cell) cells[key] = cell;
      else delete cells[key];
      // A template room only stands on an open place.
      if (!cell || cell.kind !== 'open') delete rooms[key];
      return { ...p, cells, rooms };
    });

  const setRoom = (key: string, room: EditorRoom | null) =>
    onChange((p) => {
      const rooms = { ...p.rooms };
      if (room) rooms[key] = room;
      else delete rooms[key];
      return { ...p, rooms };
    });

  const clickCell = (key: string) => {
    const cell = plan.cells[key];
    if (mode === 'select') {
      setSelected(cell ? key : null);
      return;
    }
    if (mode === 'erase') {
      setCell(key, null);
      if (selected === key) setSelected(null);
      return;
    }
    setCell(key, { kind: mode, allowed: cell?.allowed ?? [] });
    setSelected(key);
  };

  const sel = selected && plan.cells[selected] && parseKey(selected).layer === shownLayer ? selected : null;
  const selCell = sel ? plan.cells[sel] : null;
  const selRoom = sel ? plan.rooms[sel] ?? null : null;
  const layerTypes = layerRoomTypes(shownLayer);
  const roomsAllowedHere = selCell != null && selCell.kind === 'open' && isFree(plan, shownLayer);

  const rows = Array.from({ length: plan.grid_h }, (_, y) => y);
  const cols = Array.from({ length: plan.grid_w }, (_, x) => x);

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Ширина</span>
          <input type="number" min={PLAN_GRID_MIN} max={PLAN_GRID_MAX} value={plan.grid_w}
            onChange={(e) => setSize('grid_w', Number(e.target.value))} className={FIELD} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Высота</span>
          <input type="number" min={PLAN_GRID_MIN} max={PLAN_GRID_MAX} value={plan.grid_h}
            onChange={(e) => setSize('grid_h', Number(e.target.value))} className={FIELD} />
        </label>
        <label className="flex flex-col gap-1.5 col-span-2 sm:col-span-1">
          <span className={LABEL}>Цена пристройки</span>
          <input type="number" min={1} placeholder="нет пристроек" value={plan.extension_price ?? ''}
            onChange={(e) => onChange((p) => ({ ...p, extension_price: priceOrNull(e.target.value) }))} className={FIELD} />
        </label>
      </div>

      <div className="flex flex-col gap-2">
        <span className={LABEL}>Слои</span>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {HOUSE_LAYERS.map((l) => (
            <div key={l} className="flex items-center gap-2 bg-black/30 border border-white/[0.07] rounded-card px-3 py-2 min-w-0">
              <label className="flex items-center gap-2 text-sm text-white shrink-0">
                <input type="checkbox" checked={plan.layers[l].on} disabled={l === 'floor1'}
                  onChange={(e) => setLayerState(l, { on: e.target.checked })} className="accent-gold" />
                {LAYER_LABEL[l]}
              </label>
              {l === 'floor1' ? (
                <span className="ml-auto text-white/40 text-xs">всегда, бесплатно</span>
              ) : plan.layers[l].on ? (
                <input type="number" min={1} placeholder="бесплатно" value={plan.layers[l].price ?? ''}
                  onChange={(e) => setLayerState(l, { price: priceOrNull(e.target.value) })}
                  className="ml-auto w-28 min-w-0 bg-black/50 border border-white/10 rounded-card text-white text-sm px-3 py-1.5 focus:outline-none focus:border-site-blue/50 placeholder:text-white/30" />
              ) : null}
            </div>
          ))}
        </div>
        <span className="text-white/40 text-xs">Цена слоя — сколько хозяин заплатит, чтобы его открыть. Пусто — слой открыт сразу.</span>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          {HOUSE_LAYERS.filter((l) => plan.layers[l].on).map((l) => (
            <button key={l} type="button" onClick={() => { setLayer(l); setSelected(null); }}
              className={`chip-outline rounded-full px-3 py-1.5 text-xs font-medium flex items-center gap-1.5 ${l === shownLayer ? 'chip-outline-active' : ''}`}>
              {!isFree(plan, l) && <Lock size={11} />}{LAYER_LABEL[l]}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-4 gap-1.5 sm:max-w-md">
          {MODES.map(({ mode: m, label, Icon }) => (
            <button key={m} type="button" onClick={() => setMode(m)}
              className={`chip-outline rounded-card px-1 sm:px-2 py-2 text-[11px] sm:text-xs flex flex-col sm:flex-row items-center justify-center gap-1 min-w-0 ${m === mode ? 'chip-outline-active' : ''}`}>
              <Icon size={14} className="shrink-0" /><span className="truncate max-w-full">{label}</span>
            </button>
          ))}
        </div>
        <span className="text-white/40 text-xs">
          Выберите режим и нажимайте на клетки: «Открытое» — место доступно сразу после покупки, «Пристройка» — хозяин докупает его.
        </span>
      </div>

      <div className="grid gap-1.5 w-full"
        style={{ gridTemplateColumns: `repeat(${plan.grid_w}, minmax(0, 1fr))`, maxWidth: `${plan.grid_w * 5.5}rem` }}>
        {rows.map((y) => cols.map((x) => {
          const key = keyOf(shownLayer, x, y);
          const cell = plan.cells[key];
          const room = plan.rooms[key];
          const ring = sel === key ? 'ring-2 ring-gold/80' : '';
          const base = `relative aspect-square min-w-0 rounded-[10px] flex flex-col items-center justify-center gap-0.5 p-1 text-center transition-colors duration-200 ease-site ${ring}`;
          if (!cell) {
            return (
              <button key={key} type="button" onClick={() => clickCell(key)} title="Нет места"
                className={`${base} border border-white/[0.05] hover:border-white/20`} />
            );
          }
          const Icon = room ? ROOM_TYPE_ICON[room.room_type] : null;
          return (
            <button key={key} type="button" onClick={() => clickCell(key)}
              className={`${base} ${cell.kind === 'open'
                ? 'border border-dashed border-site-blue/50 bg-site-blue/[0.06]'
                : 'border border-gold-dark/40 bg-gold/[0.06]'}`}>
              {cell.kind === 'extension' && <Lock size={10} className="absolute top-1 right-1 text-gold/70" />}
              {cell.allowed.length > 0 && <span className="absolute top-1 left-1 w-1.5 h-1.5 rounded-full bg-site-blue" title="Типы ограничены" />}
              {Icon ? <Icon size={16} className="text-gold shrink-0" /> : null}
              <span className="text-[10px] text-white/60 leading-tight truncate w-full">
                {room ? room.name : cell.kind === 'open' ? 'место' : 'пристр.'}
              </span>
            </button>
          );
        }))}
      </div>

      {selCell && sel && (
        <div className="bg-black/30 border border-white/[0.07] rounded-card p-3 flex flex-col gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-white text-sm font-medium">{placeLabel(sel)}</span>
            <button type="button" onClick={() => { setCell(sel, null); setSelected(null); }}
              className="ml-auto flex items-center gap-1 text-xs text-white/40 hover:text-site-red transition-colors">
              <Trash2 size={13} />Убрать место
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:max-w-xs">
            {(['open', 'extension'] as PlanCellKind[]).map((k) => (
              <button key={k} type="button" onClick={() => setCell(sel, { ...selCell, kind: k })}
                className={`chip-outline rounded-card px-3 py-1.5 text-xs ${selCell.kind === k ? 'chip-outline-active' : ''}`}>
                {k === 'open' ? 'Открытое' : 'Пристройка'}
              </button>
            ))}
          </div>
          <div className="flex flex-col gap-1.5">
            <span className={LABEL}>Какие комнаты можно строить</span>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {layerTypes.map((t) => (
                <label key={t} className="flex items-center gap-2 text-sm text-white/80">
                  <input type="checkbox" className="accent-gold" checked={selCell.allowed.includes(t)}
                    onChange={(e) => setCell(sel, {
                      ...selCell,
                      allowed: e.target.checked
                        ? layerTypes.filter((x) => x === t || selCell.allowed.includes(x))
                        : selCell.allowed.filter((x) => x !== t),
                    })} />
                  {ROOM_TYPE_LABEL[t]}
                </label>
              ))}
            </div>
            <span className="text-white/40 text-xs">Ничего не отмечено — можно любые комнаты этого слоя.</span>
          </div>

          {kind === 'ready' && (roomsAllowedHere ? (
            selRoom ? (
              <div className="flex flex-col gap-2.5 pt-3 border-t border-white/[0.06]">
                <div className="flex items-center gap-2">
                  <span className={LABEL}>Комната</span>
                  <button type="button" onClick={() => setRoom(sel, null)}
                    className="ml-auto flex items-center gap-1 text-xs text-white/40 hover:text-site-red transition-colors">
                    <Trash2 size={13} />Убрать комнату
                  </button>
                </div>
                <select value={selRoom.room_type}
                  onChange={(e) => setRoom(sel, { ...selRoom, room_type: e.target.value as RoomType })}
                  className="bg-black/50 border border-white/10 rounded-card text-white text-sm px-3 py-1.5 focus:outline-none focus:border-gold/50 self-start">
                  {effectiveTypes(selCell, shownLayer).map((t) => <option key={t} value={t}>{ROOM_TYPE_LABEL[t]}</option>)}
                </select>
                <input value={selRoom.name} maxLength={120} placeholder="Название"
                  onChange={(e) => setRoom(sel, { ...selRoom, name: e.target.value })} className={FIELD} />
                <textarea value={selRoom.description} maxLength={5000} placeholder="Описание"
                  onChange={(e) => setRoom(sel, { ...selRoom, description: e.target.value })} className={`${FIELD} resize-y min-h-[60px]`} />
                <ImageField label="Картинка комнаты" value={selRoom.image_url}
                  onChange={(url) => setRoom(sel, { ...selRoom, image_url: url })} />
              </div>
            ) : (
              <button type="button" onClick={() => setRoom(sel, templateRoom(effectiveTypes(selCell, shownLayer)[0]))}
                className="self-start flex items-center gap-1 text-xs text-site-blue hover:text-white transition-colors">
                <Plus size={14} />Поставить комнату
              </button>
            )
          ) : (
            <span className="text-white/40 text-xs">Шаблонные комнаты ставятся только на открытые места бесплатных слоёв.</span>
          ))}
        </div>
      )}
    </div>
  );
};

export default PlotPlanEditor;
