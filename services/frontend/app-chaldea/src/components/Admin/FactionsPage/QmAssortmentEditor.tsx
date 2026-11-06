// FEAT-206 — the faction quartermaster's assortment (one per faction, shared by all its quartermasters).
// On-market items restock in the 6 h tick toward «Норма запаса» (bought from the HQ region's market);
// off-market items (scrolls, recipes, legendary+) are restocked only by the admin — their norm stays 0.
import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Trash2 } from 'lucide-react';
import {
  FACTION_QM_PRICE_MAX,
  FACTION_QM_STOCK_MAX,
  adminCreateQmItem,
  adminDeleteQmItem,
  adminFactionQmItems,
  adminUpdateQmItem,
  type FactionQmItemAdmin,
  type FactionQmItemInput,
  type FactionRankAdmin,
} from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import { EntityPicker } from '../DungeonsPage/editor/pickers';
import ConfirmDialog from '../../pages/LocationPage/ConfirmDialog';
import { FIELD, INT_RE, LABEL, OPTION, SIGNED_INT_RE, toInt } from './adminShared';

interface QmAssortmentEditorProps {
  factionId: number;
  ranks: FactionRankAdmin[];
  canEdit: boolean;
}

interface RowForm {
  item_id: number | null;
  price: string;
  min_rank_id: number | null;
  stock: string;
  restock_target: string;
  is_active: boolean;
  sort_order: string;
}

const EMPTY: RowForm = {
  item_id: null,
  price: '',
  min_rank_id: null,
  stock: '0',
  restock_target: '0',
  is_active: true,
  sort_order: '0',
};

const formOf = (r: FactionQmItemAdmin): RowForm => ({
  item_id: r.item_id,
  price: String(r.price),
  min_rank_id: r.min_rank_id,
  stock: String(r.stock),
  restock_target: String(r.restock_target),
  is_active: r.is_active,
  sort_order: String(r.sort_order),
});

const fail = (message: string): null => {
  toast.error(message);
  return null;
};

/** Client-side bounds (the server re-checks); returns the body or shows a toast and returns null. */
const bodyOf = (f: RowForm, offMarket: boolean): FactionQmItemInput | null => {
  if (f.item_id == null) return fail('Выберите предмет');
  const price = toInt(f.price);
  if (price == null || price < 1 || price > FACTION_QM_PRICE_MAX) return fail(`Цена: от 1 до ${FACTION_QM_PRICE_MAX}`);
  const stock = toInt(f.stock);
  if (stock == null || stock < 0 || stock > FACTION_QM_STOCK_MAX) return fail(`Запас: от 0 до ${FACTION_QM_STOCK_MAX}`);
  const target = toInt(f.restock_target) ?? 0;
  if (target < 0 || target > FACTION_QM_STOCK_MAX) return fail(`Норма запаса: от 0 до ${FACTION_QM_STOCK_MAX}`);
  if (offMarket && target > 0) {
    return fail('Этот предмет не продаётся на рынке — запас пополняет только администратор');
  }
  return {
    item_id: f.item_id,
    price,
    min_rank_id: f.min_rank_id,
    stock,
    restock_target: target,
    is_active: f.is_active,
    sort_order: toInt(f.sort_order) ?? 0,
  };
};

const RowFields = ({
  form,
  set,
  ranks,
  offMarket,
  ro,
  itemEditable,
}: {
  form: RowForm;
  set: <K extends keyof RowForm>(k: K, v: RowForm[K]) => void;
  ranks: FactionRankAdmin[];
  offMarket: boolean;
  ro: boolean;
  itemEditable: boolean;
}) => (
  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
    {itemEditable && (
      <div className="flex flex-col gap-1 min-w-0 sm:col-span-2 lg:col-span-3">
        <span className={LABEL}>Предмет</span>
        <EntityPicker kind="item" value={form.item_id} onChange={(id) => set('item_id', id)} />
      </div>
    )}
    <label className="flex flex-col gap-1 min-w-0">
      <span className={LABEL}>Цена (до скидки)</span>
      <input inputMode="numeric" value={form.price} disabled={ro} onChange={(e) => INT_RE.test(e.target.value) && set('price', e.target.value)} className={FIELD} />
    </label>
    <label className="flex flex-col gap-1 min-w-0">
      <span className={LABEL}>Минимальное звание</span>
      <select
        value={form.min_rank_id ?? ''}
        disabled={ro}
        onChange={(e) => set('min_rank_id', e.target.value === '' ? null : Number(e.target.value))}
        className={FIELD}
      >
        <option value="" className={OPTION}>
          Любой участник
        </option>
        {[...ranks]
          .sort((a, b) => a.sort_order - b.sort_order)
          .map((r) => (
            <option key={r.id} value={r.id} className={OPTION}>
              {r.name}
              {r.qm_discount_pct ? ` (скидка ${r.qm_discount_pct} %)` : ''}
            </option>
          ))}
      </select>
    </label>
    <label className="flex flex-col gap-1 min-w-0">
      <span className={LABEL}>Запас сейчас</span>
      <input inputMode="numeric" value={form.stock} disabled={ro} onChange={(e) => INT_RE.test(e.target.value) && set('stock', e.target.value)} className={FIELD} />
    </label>
    <label className="flex flex-col gap-1 min-w-0">
      <span className={LABEL}>Норма запаса (пополнение)</span>
      <input
        inputMode="numeric"
        value={offMarket ? '0' : form.restock_target}
        disabled={ro || offMarket}
        onChange={(e) => INT_RE.test(e.target.value) && set('restock_target', e.target.value)}
        className={FIELD}
      />
      <span className="text-white/40 text-xs">
        {offMarket
          ? 'Предмета нет на рынке — пополняет только администратор'
          : '0 — не пополнять; иначе фракция докупает с рынка края штаба'}
      </span>
    </label>
    <label className="flex flex-col gap-1 min-w-0">
      <span className={LABEL}>Порядок</span>
      <input inputMode="numeric" value={form.sort_order} disabled={ro} onChange={(e) => SIGNED_INT_RE.test(e.target.value) && set('sort_order', e.target.value)} className={FIELD} />
    </label>
    <label className="flex items-center gap-2 cursor-pointer select-none self-end pb-1">
      <input
        type="checkbox"
        checked={form.is_active}
        disabled={ro}
        onChange={(e) => set('is_active', e.target.checked)}
        className="w-4 h-4 accent-gold shrink-0"
      />
      <span className="text-white/85 text-sm">В продаже</span>
    </label>
  </div>
);

const ExistingRow = ({
  row,
  ranks,
  canEdit,
  onSaved,
  onDelete,
}: {
  row: FactionQmItemAdmin;
  ranks: FactionRankAdmin[];
  canEdit: boolean;
  onSaved: (r: FactionQmItemAdmin) => void;
  onDelete: (r: FactionQmItemAdmin) => void;
}) => {
  const [form, setForm] = useState<RowForm>(() => formOf(row));
  const [saving, setSaving] = useState(false);
  useEffect(() => setForm(formOf(row)), [row]);
  const set = <K extends keyof RowForm>(k: K, v: RowForm[K]) => setForm((f) => ({ ...f, [k]: v }));
  const dirty = JSON.stringify(form) !== JSON.stringify(formOf(row));

  const save = async () => {
    const body = bodyOf(form, row.off_market);
    if (!body) return;
    setSaving(true);
    try {
      onSaved(await adminUpdateQmItem(row.id, body));
      toast.success('Товар сохранён');
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить товар'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white/[0.03] rounded-card p-3 flex flex-col gap-3 min-w-0">
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-10 h-10 rounded bg-black/40 overflow-hidden shrink-0 flex items-center justify-center">
          {row.item?.image ? <img src={row.item.image} alt="" className="w-full h-full object-cover" /> : <span aria-hidden>📦</span>}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-white text-sm break-words">{row.item?.name ?? `Предмет #${row.item_id}`}</p>
          <p className="text-white/45 text-xs break-words">
            {row.off_market ? 'не продаётся на рынке' : `группа рынка: ${row.group ?? '—'}`}
            {!row.is_active ? ' · снят с продажи' : ''}
          </p>
        </div>
        {canEdit && (
          <button
            type="button"
            onClick={() => onDelete(row)}
            className="text-site-red hover:text-white transition-colors p-1 shrink-0"
            aria-label="Убрать из ассортимента"
            title="Убрать из ассортимента"
          >
            <Trash2 size={16} />
          </button>
        )}
      </div>
      <RowFields form={form} set={set} ranks={ranks} offMarket={row.off_market} ro={!canEdit} itemEditable={false} />
      {canEdit && dirty && (
        <div className="flex flex-col sm:flex-row gap-2">
          <button type="button" className="btn-blue !w-full sm:!w-auto !text-sm !px-6 disabled:opacity-50" disabled={saving} onClick={() => void save()}>
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
          <button type="button" className="btn-line !w-full sm:!w-auto !text-sm" disabled={saving} onClick={() => setForm(formOf(row))}>
            Отменить
          </button>
        </div>
      )}
    </div>
  );
};

const QmAssortmentEditor = ({ factionId, ranks, canEdit }: QmAssortmentEditorProps) => {
  const [rows, setRows] = useState<FactionQmItemAdmin[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [newForm, setNewForm] = useState<RowForm>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<FactionQmItemAdmin | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setRows(await adminFactionQmItems(factionId));
    } catch (e) {
      setError(apiErrorMessage(e, 'Не удалось загрузить ассортимент интенданта'));
    }
  }, [factionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const setNew = <K extends keyof RowForm>(k: K, v: RowForm[K]) => setNewForm((f) => ({ ...f, [k]: v }));

  const create = async () => {
    const body = bodyOf(newForm, false);
    if (!body) return;
    setSaving(true);
    try {
      await adminCreateQmItem(factionId, body);
      toast.success('Товар добавлен');
      setNewForm(EMPTY);
      setAdding(false);
      void load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось добавить товар'));
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!deleting) return;
    const row = deleting;
    setDeleting(null);
    try {
      await adminDeleteQmItem(row.id);
      toast.success('Товар убран из ассортимента');
      void load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось убрать товар'));
    }
  };

  return (
    <section className="gray-bg p-4 sm:p-6 flex flex-col gap-3 min-w-0">
      <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Ассортимент интенданта</h3>
      <p className="text-white/40 text-xs">
        Один ассортимент на фракцию — его продают все её интенданты. Деньги за покупки идут в казну фракции; цена
        уменьшается на скидку звания покупателя.
      </p>
      {error && (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-site-red text-sm">{error}</p>
          <button type="button" className="btn-line !w-auto !text-xs !py-1 !px-3" onClick={() => void load()}>
            Повторить
          </button>
        </div>
      )}
      {rows && rows.length === 0 && <p className="text-white/50 text-sm">Ассортимент пуст.</p>}
      <div className="flex flex-col gap-2">
        {rows?.map((r) => (
          <ExistingRow
            key={r.id}
            row={r}
            ranks={ranks}
            canEdit={canEdit}
            onSaved={(updated) => setRows((prev) => (prev ? prev.map((x) => (x.id === updated.id ? updated : x)) : prev))}
            onDelete={setDeleting}
          />
        ))}
      </div>

      {canEdit &&
        (adding ? (
          <div className="bg-white/[0.03] rounded-card p-3 flex flex-col gap-3 min-w-0 border border-gold/20">
            <span className="text-white/85 text-sm">Новый товар</span>
            <RowFields form={newForm} set={setNew} ranks={ranks} offMarket={false} ro={false} itemEditable />
            <p className="text-white/40 text-xs">
              Для свитков, рецептов и предметов легендарной редкости и выше норму запаса оставьте 0 — их на рынке нет.
            </p>
            <div className="flex flex-col sm:flex-row gap-2">
              <button type="button" className="btn-blue !w-full sm:!w-auto !text-sm !px-6 disabled:opacity-50" disabled={saving} onClick={() => void create()}>
                {saving ? 'Добавление...' : 'Добавить'}
              </button>
              <button
                type="button"
                className="btn-line !w-full sm:!w-auto !text-sm"
                disabled={saving}
                onClick={() => {
                  setAdding(false);
                  setNewForm(EMPTY);
                }}
              >
                Отмена
              </button>
            </div>
          </div>
        ) : (
          <button type="button" onClick={() => setAdding(true)} className="text-sm text-site-blue hover:text-white transition-colors self-start">
            + Добавить товар
          </button>
        ))}

      {deleting && (
        <ConfirmDialog
          title="Убрать товар"
          message={`Убрать «${deleting.item?.name ?? `#${deleting.item_id}`}» из ассортимента? Оставшийся запас (${deleting.stock} шт.) пропадёт; прошлые покупки останутся в журнале.`}
          confirmLabel="Убрать"
          danger
          onConfirm={() => void remove()}
          onCancel={() => setDeleting(null)}
        />
      )}
    </section>
  );
};

export default QmAssortmentEditor;
