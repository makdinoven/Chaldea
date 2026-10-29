import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Trash2 } from 'lucide-react';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import { adminSetBuildCost, ROOM_TYPE_LABEL, type BuildCost, type RoomType } from '../../../api/houses';
import { searchItemsCatalog } from '../../../api/adminCharacters';
import type { ItemData } from '../CharactersPage/types';
import { apiErrorMessage } from '../../../api/errors';
import { FIELD, LABEL } from '../../pages/EpisodesPage/EpisodeFormModal';
import { useCurrency } from '../../../hooks/useCurrency';

interface BuildCostModalProps {
  roomType: RoomType;
  level: number;
  /** The current cost, null when this step isn't configured yet. */
  cost: BuildCost | null;
  onClose: () => void;
  onSaved: () => void;
}

interface MaterialRow {
  item_id: number;
  name: string;
  image: string | null;
  quantity: number;
}

const LOOKUP_DEBOUNCE_MS = 300;
const MAX_GOLD = 1_000_000_000;
const MAX_BUILD_HOURS = 24 * 365;
const MAX_QUANTITY = 10_000;

const clampInt = (v: string, min: number, max: number) => Math.min(max, Math.max(min, Math.floor(Number(v) || 0)));

/** Admin: gold, build time and materials of one build step (room type × level). */
const BuildCostModal = ({ roomType, level, cost, onClose, onSaved }: BuildCostModalProps) => {
  const { forms } = useCurrency();
  const [gold, setGold] = useState(cost?.gold ?? 0);
  const [hours, setHours] = useState(cost?.build_hours ?? 0);
  const [rows, setRows] = useState<MaterialRow[]>(
    (cost?.items ?? []).map((i) => ({
      item_id: i.item_id,
      name: i.name ?? `Предмет #${i.item_id}`,
      image: i.image,
      quantity: i.quantity,
    })),
  );
  const [query, setQuery] = useState('');
  const [options, setOptions] = useState<ItemData[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (query.trim().length < 1) {
      setOptions([]);
      return undefined;
    }
    const t = setTimeout(() => {
      searchItemsCatalog(query.trim(), 1, 20)
        .then(setOptions)
        .catch((e) => toast.error(apiErrorMessage(e, 'Не удалось найти предметы')));
    }, LOOKUP_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [query]);

  const addItem = (item: ItemData) => {
    setRows((prev) => (prev.some((r) => r.item_id === item.id)
      ? prev
      : [...prev, { item_id: item.id, name: item.name, image: item.image, quantity: 1 }]));
    setQuery('');
    setOptions([]);
  };

  const save = async () => {
    setSaving(true);
    try {
      await adminSetBuildCost(roomType, level, {
        gold,
        build_hours: hours,
        items: rows.map((r) => ({ item_id: r.item_id, quantity: r.quantity })),
      });
      toast.success('Стоимость сохранена');
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить стоимость'));
      setSaving(false);
    }
  };

  return (
    <ModalShell
      open
      onClose={onClose}
      title={`${ROOM_TYPE_LABEL[roomType]} — ${level === 1 ? 'постройка (ур. 1)' : `улучшение до ур. ${level}`}`}
      size="md"
      dismissible={!saving}
      closeOnBackdrop={false}
      footer={
        <>
          <button type="button" onClick={onClose} disabled={saving} className="btn-line w-full sm:w-auto !px-5">Отмена</button>
          <button type="button" onClick={() => void save()} disabled={saving}
            className="btn-blue w-full sm:w-auto !px-6 disabled:opacity-50">
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="flex flex-col gap-1.5">
            <span className={LABEL}>{forms.name}</span>
            <input type="number" min={0} max={MAX_GOLD} value={gold}
              onChange={(e) => setGold(clampInt(e.target.value, 0, MAX_GOLD))} className={FIELD} />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className={LABEL}>Время стройки (часы)</span>
            <input type="number" min={0} max={MAX_BUILD_HOURS} value={hours}
              onChange={(e) => setHours(clampInt(e.target.value, 0, MAX_BUILD_HOURS))} className={FIELD} />
          </label>
        </div>

        <div className="flex flex-col gap-2">
          <span className={LABEL}>Материалы</span>
          {rows.length === 0 && <p className="text-white/40 text-xs italic">Без материалов.</p>}
          {rows.map((row) => (
            <div key={row.item_id} className="flex items-center gap-2.5 bg-black/30 border border-white/[0.07] rounded-card p-2">
              <span className="w-9 h-9 rounded-[8px] overflow-hidden bg-black/40 border border-white/10 shrink-0 block">
                {row.image && <img src={row.image} alt="" className="w-full h-full object-cover" />}
              </span>
              <span className="text-white text-sm flex-1 min-w-0 truncate">
                {row.name} <span className="text-white/35 text-xs">#{row.item_id}</span>
              </span>
              <input type="number" min={1} max={MAX_QUANTITY} value={row.quantity} aria-label="Количество"
                onChange={(e) => {
                  const q = clampInt(e.target.value, 1, MAX_QUANTITY);
                  setRows((prev) => prev.map((r) => (r.item_id === row.item_id ? { ...r, quantity: q } : r)));
                }}
                className="w-20 bg-black/40 border border-white/10 rounded-card text-white text-sm px-2 py-1.5 focus:outline-none focus:border-site-blue/50" />
              <button type="button" title="Убрать" onClick={() => setRows((prev) => prev.filter((r) => r.item_id !== row.item_id))}
                className="w-8 h-8 flex items-center justify-center text-white/40 hover:text-site-red transition-colors shrink-0">
                <Trash2 size={15} />
              </button>
            </div>
          ))}
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Добавить: название предмета" className={FIELD} />
          {options.length > 0 && (
            <div className="bg-black/80 border border-white/10 rounded-card divide-y divide-white/5 max-h-56 overflow-y-auto gold-scrollbar">
              {options.map((o) => (
                <button key={o.id} type="button" onClick={() => addItem(o)}
                  className="w-full text-left px-3 py-2 text-sm text-white hover:bg-white/[0.06] transition-colors flex items-center gap-2">
                  <span className="w-7 h-7 rounded-[6px] overflow-hidden bg-black/40 shrink-0 block">
                    {o.image && <img src={o.image} alt="" className="w-full h-full object-cover" />}
                  </span>
                  <span className="truncate">{o.name}</span>
                  <span className="text-white/40 text-xs shrink-0">#{o.id}</span>
                </button>
              ))}
            </div>
          )}
          <span className="text-white/40 text-xs">Материалы берутся из сумки хозяина — только обычные стопки (без заточки и самоцветов).</span>
        </div>
      </div>
    </ModalShell>
  );
};

export default BuildCostModal;
