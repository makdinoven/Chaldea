import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  TouchSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import { Backpack, Minus, Package, Plus, Search } from 'lucide-react';
import {
  getStorage,
  putIntoStorage,
  takeFromStorage,
  type ActingCharacter,
  type StorageState,
} from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import type { InventoryItem } from '../../../redux/slices/profileSlice';
import { shownRarity } from '../../../constants/items';
import { cellsWord } from '../../../utils/furniture';
import { ITEM_TYPE_ICONS } from '../../ProfilePage/constants';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import RoomAction from './RoomAction';

/*
  FEAT-180 — the house's shared storage (one for all storage rooms and the
  cellar). On the room page it is a button of the action bar («Открыть
  кладовую», used / capacity); the button opens a modal with two inventory-like
  grids — what lies in the storage and the character's bag. A click on a cell
  opens a small panel with the quantity and «Положить» / «Взять»; a cell can
  also be dragged onto the other grid (the whole stack moves). Looking is
  allowed from anywhere; putting and taking only standing in a storage room or
  the cellar of this house.
*/

const STORAGE_HINT =
  'Общая кладовая дома — одна на все кладовые и погреб. Класть и брать вещи можно, только стоя в кладовой или погребе этого дома.';
const GUEST_REASON = 'Гости кладовой не пользуются';
const GO_TO_STORAGE = 'Сначала перейдите в кладовую или погреб этого дома';
const FROZEN_REASON = 'Дом заморожен за неуплату налога — кладовую можно только смотреть.';

/** The storage state as the API returns it (the frozen flag is sent but not in the shared type). */
type FullStorageState = StorageState & { frozen?: boolean };

type Side = 'storage' | 'bag';

/** One stack shown in a grid — a storage row or a bag row, brought to one shape. */
interface CellItem {
  id: number;
  name: string;
  image: string | null;
  itemType: string | null;
  rarity: string | null;
  quantity: number;
  identified: boolean;
  enhancement: number;
  /** Extra facts for the action panel: sharpening, wear. */
  note?: string;
}

const storageCells = (state: FullStorageState): CellItem[] =>
  state.items.map((i) => {
    const parts: string[] = [];
    if (!i.is_identified) parts.push('не опознан');
    if (i.enhancement_points_spent > 0) parts.push(`заточка +${i.enhancement_points_spent}`);
    if (i.current_durability != null && i.max_durability > 0) parts.push(`прочность ${i.current_durability}/${i.max_durability}`);
    return {
      id: i.id,
      name: i.name,
      image: i.image_url,
      itemType: i.item_type,
      rarity: i.rarity,
      quantity: i.quantity,
      identified: i.is_identified,
      enhancement: i.enhancement_points_spent,
      note: parts.join(' · ') || undefined,
    };
  });

const bagCells = (bag: InventoryItem[]): CellItem[] =>
  bag.map((row) => {
    const parts: string[] = [];
    if (row.is_identified === false) parts.push('не опознан');
    if ((row.enhancement_points_spent ?? 0) > 0) parts.push(`заточка +${row.enhancement_points_spent}`);
    const maxDur = row.item.max_durability ?? 0;
    if (row.current_durability != null && maxDur > 0) parts.push(`прочность ${row.current_durability}/${maxDur}`);
    return {
      id: row.id,
      name: row.item.name,
      image: row.item.image ?? null,
      itemType: row.item.item_type ?? null,
      rarity: row.item.item_rarity ?? null,
      quantity: row.quantity,
      identified: row.is_identified !== false,
      enhancement: row.enhancement_points_spent ?? 0,
      note: parts.join(' · ') || undefined,
    };
  });

const rarityClassOf = (itemType: string | null, rarity: string | null) => {
  const visible = shownRarity(itemType, rarity);
  return visible && visible !== 'common' ? `rarity-${visible}` : '';
};

/** The item picture inside a round cell (image, else the type icon, else a box). */
const CellPicture = ({ item }: { item: CellItem }) => {
  const icon = item.image ?? (item.itemType ? ITEM_TYPE_ICONS[item.itemType] : undefined);
  if (!icon) return <Package size={20} className="text-white/40" />;
  return (
    <img src={icon} alt={item.name} draggable={false}
      className={`${item.image ? 'w-full h-full object-cover' : 'w-1/2 h-1/2 opacity-70'} ${item.identified ? '' : 'grayscale'}`} />
  );
};

/** A square cell in the look of the profile inventory: rarity frame, quantity and sharpening badges. */
const StorageCell = ({ item, side, selected, onSelect }: { item: CellItem; side: Side; selected: boolean; onSelect: () => void }) => {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `${side}:${item.id}`,
    data: { side, id: item.id } satisfies DragData,
  });
  return (
  <button type="button" ref={setNodeRef} {...attributes} {...listeners} onClick={onSelect} title={item.name}
    aria-label={`${item.name}${item.quantity > 1 ? ` ×${item.quantity}` : ''}`}
    aria-pressed={selected}
    className={`relative block w-full focus-visible:outline-none group touch-manipulation ${isDragging ? 'opacity-40' : ''}`}>
    <span className={`item-cell w-full h-auto aspect-square ${rarityClassOf(item.itemType, item.rarity)} group-hover:scale-105 ${item.identified ? '' : 'opacity-60'} ${selected ? 'shadow-[0_0_0_2px_#76a6bd,0_0_14px_rgba(118,166,189,0.55)]' : ''} group-focus-visible:shadow-[0_0_0_2px_#f0d95c]`}>
      <CellPicture item={item} />
      {!item.identified && (
        <span className="absolute inset-0 flex items-center justify-center text-sm font-medium text-gold drop-shadow-lg pointer-events-none">???</span>
      )}
    </span>
    {item.quantity > 1 && (
      <span className="absolute -bottom-1 -right-1 z-10 min-w-[20px] h-[20px] flex items-center justify-center text-[10px] font-medium text-white bg-site-bg rounded-full border border-white/30 px-1 pointer-events-none">
        {item.quantity}
      </span>
    )}
    {item.enhancement > 0 && (
      <span className="absolute -top-1 -right-1 z-10 min-w-[20px] h-[20px] flex items-center justify-center text-[10px] font-medium text-gold bg-site-bg rounded-full border border-gold/40 px-1 pointer-events-none">
        +{item.enhancement}
      </span>
    )}
  </button>
  );
};

/** What a dragged cell carries. */
interface DragData {
  side: Side;
  id: number;
}

interface ActionPanelProps {
  item: CellItem;
  actionLabel: string;
  /** Why the action is unavailable; null — it can be done. */
  reason: string | null;
  onAction: (quantity: number) => Promise<void>;
}

/** The small panel under a grid for the picked stack: name, quantity stepper, the action button. */
const ActionPanel = ({ item, actionLabel, reason, onAction }: ActionPanelProps) => {
  const [count, setCount] = useState(item.quantity);
  const [busy, setBusy] = useState(false);
  useEffect(() => setCount(item.quantity), [item.id, item.quantity]);

  const clamp = (n: number) => Math.min(Math.max(1, Math.floor(n) || 1), item.quantity);
  const act = async () => {
    setBusy(true);
    try {
      await onAction(clamp(count));
    } finally {
      setBusy(false);
    }
  };
  const disabled = reason != null || busy;
  const STEP = 'w-8 h-8 shrink-0 flex items-center justify-center rounded-[8px] border border-white/10 text-white/70 hover:text-white hover:border-gold/50 transition-colors duration-200 ease-site disabled:opacity-40 disabled:pointer-events-none';

  return (
    <div className="shrink-0 flex flex-col gap-2.5 p-3 sm:p-3.5 border-t border-white/[0.08] bg-black/20">
      <div className="flex items-center gap-3 min-w-0">
        <span className={`item-cell ${rarityClassOf(item.itemType, item.rarity)} !w-10 !h-10 shrink-0`}>
          <CellPicture item={item} />
        </span>
        <span className="flex flex-col gap-0.5 min-w-0 flex-1">
          <span className="text-white text-[13px] font-medium leading-tight break-words">
            {item.name}{item.quantity > 1 && <span className="text-white/45 font-normal"> ×{item.quantity}</span>}
          </span>
          {item.note && <span className="text-white/45 text-[11px] leading-tight break-words">{item.note}</span>}
        </span>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {item.quantity > 1 && (
          <div className="flex items-center gap-1.5">
            <button type="button" className={STEP} aria-label="Меньше" disabled={disabled || count <= 1}
              onClick={() => setCount((c) => clamp(c - 1))}>
              <Minus size={14} />
            </button>
            <input type="number" min={1} max={item.quantity} value={count} disabled={disabled}
              onChange={(e) => setCount(Number(e.target.value))} onBlur={() => setCount((c) => clamp(c))}
              aria-label="Количество"
              className="w-14 h-8 bg-black/40 border border-white/10 rounded-[8px] text-white text-sm text-center px-1 focus:outline-none focus:border-site-blue/50 disabled:opacity-50" />
            <button type="button" className={STEP} aria-label="Больше" disabled={disabled || count >= item.quantity}
              onClick={() => setCount((c) => clamp(c + 1))}>
              <Plus size={14} />
            </button>
            <button type="button" disabled={disabled || count === item.quantity} onClick={() => setCount(item.quantity)}
              className="px-2 h-8 rounded-[8px] text-white/60 text-[11px] hover:text-white transition-colors duration-200 ease-site disabled:opacity-40 disabled:pointer-events-none">
              Все
            </button>
          </div>
        )}
        <button type="button" onClick={() => void act()} disabled={disabled}
          className="ml-auto px-4 h-8 rounded-[9px] border border-gold/40 text-gold text-xs font-medium hover:bg-gold/15 transition-colors duration-200 ease-site whitespace-nowrap disabled:opacity-40 disabled:pointer-events-none">
          {busy ? '...' : actionLabel}
        </button>
      </div>
      {reason && <p className="text-gold-light/80 text-[11px] leading-snug">{reason}</p>}
    </div>
  );
};

interface GridPanelProps {
  title: string;
  icon: typeof Package;
  counter?: { text: string; full: boolean };
  items: CellItem[];
  empty: string;
  notes: string[];
  selectedId: number | null;
  onSelect: (id: number | null) => void;
  actionLabel: string;
  reason: string | null;
  onAction: (id: number, quantity: number) => Promise<void>;
  search?: { value: string; onChange: (v: string) => void };
  className?: string;
  side: Side;
  /** A cell of the other grid is being dragged and may be dropped here. */
  dropActive: boolean;
}

/** One side of the modal: a header, an inner-scrolling grid of cells and the picked stack's panel. */
const GridPanel = ({
  title, icon: Icon, counter, items, empty, notes, selectedId, onSelect, actionLabel, reason, onAction, search, className = '',
  side, dropActive,
}: GridPanelProps) => {
  const picked = items.find((i) => i.id === selectedId) ?? null;
  const { setNodeRef, isOver } = useDroppable({ id: `drop-${side}`, data: { side } });
  const frame = dropActive
    ? isOver ? 'border-gold/70 bg-gold/[0.07] shadow-[0_0_18px_rgba(240,217,92,0.18)]' : 'border-gold-dark/50 border-dashed'
    : 'border-white/[0.08] bg-white/[0.02]';
  return (
    <section ref={setNodeRef} className={`flex flex-col min-w-0 min-h-0 h-[58dvh] md:h-[60vh] rounded-card border overflow-hidden transition-colors duration-200 ease-site ${frame} ${className}`}>
      <div className="shrink-0 flex items-center gap-2.5 px-3.5 sm:px-4 py-3 border-b border-white/[0.07]">
        <Icon size={15} className="text-gold shrink-0" />
        <h4 className="gold-text text-[12px] font-medium uppercase tracking-[0.08em]">{title}</h4>
        {counter && (
          <span className={`ml-auto text-xs ${counter.full ? 'text-site-red' : 'text-white/55'}`}>{counter.text}</span>
        )}
      </div>
      {search && (
        <div className="shrink-0 px-3.5 sm:px-4 pt-3">
          <label className="flex items-center gap-2 border-b border-white/15 focus-within:border-site-blue/60 transition-colors duration-200">
            <Search size={14} className="text-white/40 shrink-0" />
            <input type="search" value={search.value} onChange={(e) => search.onChange(e.target.value)}
              placeholder="Найти в сумке" aria-label="Найти в сумке"
              className="flex-1 min-w-0 bg-transparent py-1.5 text-white text-sm placeholder:text-white/35 focus:outline-none" />
          </label>
        </div>
      )}
      <div className="flex-1 min-h-0 overflow-y-auto gold-scrollbar p-3.5 sm:p-4">
        {notes.map((n) => <p key={n} className="text-white/45 text-xs mb-3">{n}</p>)}
        {items.length === 0 ? (
          <p className="text-white/40 text-sm italic">{empty}</p>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(54px,1fr))] gap-2.5 sm:gap-3 p-1">
            {items.map((item) => (
              <StorageCell key={item.id} item={item} side={side} selected={item.id === selectedId}
                onSelect={() => onSelect(item.id === selectedId ? null : item.id)} />
            ))}
          </div>
        )}
      </div>
      {picked && (
        <ActionPanel item={picked} actionLabel={actionLabel} reason={reason} onAction={(n) => onAction(picked.id, n)} />
      )}
    </section>
  );
};

interface StorageModalProps {
  houseId: number;
  characterId: number;
  state: FullStorageState;
  onState: (s: FullStorageState) => void;
  onClose: () => void;
}

/** «Кладовая дома»: the storage and the bag side by side (tabs on a phone). */
const StorageModal = ({ houseId, characterId, state, onState, onClose }: StorageModalProps) => {
  const [bag, setBag] = useState<InventoryItem[] | null>(null);
  const [bagError, setBagError] = useState<string | null>(null);
  const [tab, setTab] = useState<Side>('storage');
  const [picked, setPicked] = useState<{ side: Side; id: number } | null>(null);
  const [query, setQuery] = useState('');

  const loadBag = useCallback(async () => {
    try {
      const { data } = await axios.get<InventoryItem[]>(`/inventory/${characterId}/items`);
      setBag(data);
      setBagError(null);
    } catch (e) {
      const msg = apiErrorMessage(e, 'Не удалось загрузить сумку персонажа');
      setBagError(msg);
      toast.error(msg);
    }
  }, [characterId]);

  useEffect(() => {
    void loadBag();
  }, [loadBag]);

  const take = async (storageItemId: number, quantity: number) => {
    try {
      onState(await takeFromStorage(houseId, characterId, storageItemId, quantity));
      toast.success('Взято из кладовой');
      await loadBag();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось взять предмет'));
    }
  };

  const put = async (inventoryItemId: number, quantity: number) => {
    try {
      onState(await putIntoStorage(houseId, characterId, inventoryItemId, quantity));
      toast.success('Положено в кладовую');
      await loadBag();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось положить предмет'));
    }
  };

  const stored = useMemo(() => storageCells(state), [state]);
  const bagItems = useMemo(() => (bag ? bagCells(bag) : []), [bag]);
  const q = query.trim().toLowerCase();
  const shownBag = q ? bagItems.filter((i) => i.name.toLowerCase().includes(q)) : bagItems;

  const full = state.used >= state.capacity;
  const placeReason = state.frozen ? FROZEN_REASON : (state.in_storage ?? state.at_house) ? null : GO_TO_STORAGE;
  const takeReason = placeReason ?? (state.can_take ? null : 'Хозяин не разрешил вам брать из кладовой.');
  const putReason = placeReason ?? (state.can_put ? null : 'Хозяин не разрешил вам класть в кладовую.');

  const select = (side: Side) => (id: number | null) => setPicked(id == null ? null : { side, id });

  // Drag a cell onto the other grid: the whole stack moves (like the inventory).
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 5 } }),
  );
  const [dragging, setDragging] = useState<DragData | null>(null);
  const draggedItem = dragging
    ? (dragging.side === 'storage' ? stored : bagItems).find((i) => i.id === dragging.id) ?? null
    : null;
  const onDragStart = (e: DragStartEvent) => setDragging((e.active.data.current as DragData | undefined) ?? null);
  const onDragEnd = (e: DragEndEvent) => {
    setDragging(null);
    const from = e.active.data.current as DragData | undefined;
    const to = (e.over?.data.current as { side?: Side } | undefined)?.side;
    if (!from || !to || to === from.side) return;
    const item = (from.side === 'storage' ? stored : bagItems).find((i) => i.id === from.id);
    if (!item) return;
    const why = from.side === 'bag' ? putReason : takeReason;
    if (why) {
      toast.error(why);
      return;
    }
    setPicked(null);
    void (from.side === 'bag' ? put(item.id, item.quantity) : take(item.id, item.quantity));
  };
  const TAB = 'flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium uppercase tracking-[0.06em] border-b-2 transition-colors duration-200 ease-site';

  return (
    <ModalShell open onClose={onClose} title="Кладовая дома" icon={<Package size={18} className="text-gold" />} size="xl"
      bodyClassName="p-3 sm:p-5">
      <div className="flex flex-col gap-3">
        {placeReason && (
          <p className="text-gold-light text-xs sm:text-sm rounded-card border border-gold-dark/30 bg-gold/[0.06] px-3 py-2">
            {placeReason}{placeReason === GO_TO_STORAGE ? ' — пока можно только смотреть.' : ''}
          </p>
        )}

        <p className="hidden md:block text-white/40 text-[11px]">
          Перетащите предмет в другую половину, чтобы переложить всю стопку, или нажмите на него, чтобы выбрать количество.
        </p>

        {/* Phone: tabs instead of two panels side by side */}
        <div className="flex md:hidden border-b border-white/10" role="tablist">
          <button type="button" role="tab" aria-selected={tab === 'storage'} onClick={() => setTab('storage')}
            className={`${TAB} ${tab === 'storage' ? 'border-gold text-gold' : 'border-transparent text-white/55'}`}>
            <Package size={13} />Кладовая <span className="normal-case tracking-normal text-white/45">{state.used}/{state.capacity}</span>
          </button>
          <button type="button" role="tab" aria-selected={tab === 'bag'} onClick={() => setTab('bag')}
            className={`${TAB} ${tab === 'bag' ? 'border-gold text-gold' : 'border-transparent text-white/55'}`}>
            <Backpack size={13} />Сумка
          </button>
        </div>

        <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd} onDragCancel={() => setDragging(null)}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4">
          <GridPanel
            className={tab === 'storage' ? '' : 'hidden md:flex'}
            title="В кладовой"
            icon={Package}
            counter={{ text: `${state.used} / ${state.capacity} ${cellsWord(state.capacity)}`, full }}
            items={stored}
            empty="Кладовая пуста."
            notes={[]}
            selectedId={picked?.side === 'storage' ? picked.id : null}
            onSelect={select('storage')}
            actionLabel="Взять"
            reason={takeReason}
            onAction={take}
            side="storage"
            dropActive={dragging?.side === 'bag'}
          />
          <GridPanel
            className={tab === 'bag' ? '' : 'hidden md:flex'}
            title="Сумка"
            icon={Backpack}
            items={shownBag}
            empty={bagError ?? (bag == null ? 'Загрузка...' : q ? 'Ничего не нашлось.' : 'Сумка пуста.')}
            notes={state.can_put && full ? ['Кладовая заполнена — новые стопки не поместятся.'] : []}
            selectedId={picked?.side === 'bag' ? picked.id : null}
            onSelect={select('bag')}
            actionLabel="Положить"
            reason={putReason}
            onAction={put}
            search={{ value: query, onChange: setQuery }}
            side="bag"
            dropActive={dragging?.side === 'storage'}
          />
        </div>
        <DragOverlay dropAnimation={null}>
          {draggedItem && (
            <span className={`item-cell w-[54px] h-[54px] ${rarityClassOf(draggedItem.itemType, draggedItem.rarity)} shadow-[0_8px_24px_rgba(0,0,0,0.6)] cursor-grabbing`}>
              <CellPicture item={draggedItem} />
            </span>
          )}
        </DragOverlay>
        </DndContext>
      </div>
    </ModalShell>
  );
};

interface StorageControlProps {
  houseId: number;
  acting: ActingCharacter;
}

/**
 * «Открыть кладовую» in the room's action bar (storage rooms and the cellar):
 * shows used / capacity and opens the storage modal. Guests cannot use it.
 */
const StorageControl = ({ houseId, acting }: StorageControlProps) => {
  const character = acting.character;
  const characterId = character?.id ?? null;
  const guest = acting.is_guest === true;
  const [state, setState] = useState<FullStorageState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    if (characterId == null || guest) return;
    try {
      setState(await getStorage(houseId, characterId));
      setError(null);
    } catch (e) {
      const msg = apiErrorMessage(e, 'Не удалось открыть кладовую');
      setError(msg);
      toast.error(msg);
    }
  }, [houseId, characterId, guest]);

  // A different character — forget the other one's storage view.
  useEffect(() => {
    setState(null);
    setError(null);
  }, [characterId]);

  // Reload when the character or the room they stand in changes (`in_storage` depends on it).
  useEffect(() => {
    void load();
  }, [load, acting.room_id]);

  if (!character) return null;

  const sub = guest
    ? null
    : error
      ? 'недоступна'
      : state
        ? `${state.used} / ${state.capacity} ${cellsWord(state.capacity)}`
        : '...';
  const reason = guest ? GUEST_REASON : error;

  return (
    <>
      <RoomAction icon={Package} label="Открыть кладовую" sub={sub}
        disabled={guest || error != null || state == null} reason={reason} hint={STORAGE_HINT}
        onClick={() => {
          setOpen(true);
          void load();
        }} />
      {open && state && (
        <StorageModal houseId={houseId} characterId={character.id} state={state} onState={setState}
          onClose={() => setOpen(false)} />
      )}
    </>
  );
};

export default StorageControl;
