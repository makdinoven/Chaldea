/**
 * NodeRow — single gathering node row inside <GatheringNodesEditor>.
 *
 * View mode: shows summary fields + buttons "Изменить" / "Удалить" / "Восстановить запас".
 * Edit mode: inline form with inputs for all editable fields (validated on save).
 *
 * Per FEAT-128 task #24:
 *  - PUT/DELETE/restore endpoints take only node_id (no location_id) — already
 *    encapsulated in `gatheringApi.adminUpdateNode/adminDeleteNode/adminRestoreNode`.
 *  - All user-facing strings are Russian.
 *  - Tailwind only, mobile responsive at 360px+.
 */
import { useState } from 'react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../../../redux/store';
import {
  adminUpdateGatheringNode,
  adminDeleteGatheringNode,
  adminRestoreGatheringNode,
  selectGatheringIsAdminLoading,
} from '../../../../../redux/slices/gatheringSlice';
import type {
  GatheringCategory,
  GatheringNodeAdminListItem,
  GatheringNodeAdminUpdate,
} from '../../../../../types/gathering';

interface NodeRowProps {
  locationId: number;
  node: GatheringNodeAdminListItem;
  canEdit: boolean;
}

interface EditFormState {
  node_name: string;
  category: GatheringCategory;
  result_item_id: number;
  result_quantity_per_gather: number;
  stamina_per_gather: number;
  daily_bank_max: number;
  allow_concurrent_gather: boolean;
  is_enabled: boolean;
}

const CATEGORY_LABEL: Record<GatheringCategory, string> = {
  ore: 'Руда',
  herb: 'Травы',
  wood: 'Дерево',
};

const CATEGORY_OPTIONS: { value: GatheringCategory; label: string }[] = [
  { value: 'ore', label: 'Руда' },
  { value: 'herb', label: 'Травы' },
  { value: 'wood', label: 'Дерево' },
];

const formatDate = (iso: string | null): string => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('ru-RU');
  } catch {
    return iso;
  }
};

const NodeRow = ({ locationId, node, canEdit }: NodeRowProps) => {
  const dispatch = useAppDispatch();
  const isAdminLoading = useAppSelector(selectGatheringIsAdminLoading);

  const [isEditing, setIsEditing] = useState(false);
  const [form, setForm] = useState<EditFormState>({
    node_name: node.node_name,
    category: node.category,
    result_item_id: node.result_item_id,
    result_quantity_per_gather: node.result_quantity_per_gather,
    stamina_per_gather: node.stamina_per_gather,
    daily_bank_max: node.daily_bank_max,
    allow_concurrent_gather: node.allow_concurrent_gather,
    is_enabled: node.is_enabled,
  });

  const startEdit = () => {
    setForm({
      node_name: node.node_name,
      category: node.category,
      result_item_id: node.result_item_id,
      result_quantity_per_gather: node.result_quantity_per_gather,
      stamina_per_gather: node.stamina_per_gather,
      daily_bank_max: node.daily_bank_max,
      allow_concurrent_gather: node.allow_concurrent_gather,
      is_enabled: node.is_enabled,
    });
    setIsEditing(true);
  };

  const cancelEdit = () => {
    setIsEditing(false);
  };

  const validate = (): boolean => {
    if (!form.node_name.trim()) {
      toast.error('Введите название ноды');
      return false;
    }
    if (!Number.isInteger(form.result_item_id) || form.result_item_id <= 0) {
      toast.error('Укажите корректный ID предмета');
      return false;
    }
    if (form.result_quantity_per_gather < 1) {
      toast.error('Количество за один сбор должно быть не меньше 1');
      return false;
    }
    if (form.stamina_per_gather < 1) {
      toast.error('Стамина за один сбор должна быть не меньше 1');
      return false;
    }
    if (form.daily_bank_max < 1) {
      toast.error('Дневной запас должен быть не меньше 1');
      return false;
    }
    return true;
  };

  const handleSave = async () => {
    if (!validate()) return;

    const body: GatheringNodeAdminUpdate = {
      node_name: form.node_name.trim(),
      category: form.category,
      result_item_id: form.result_item_id,
      result_quantity_per_gather: form.result_quantity_per_gather,
      stamina_per_gather: form.stamina_per_gather,
      daily_bank_max: form.daily_bank_max,
      allow_concurrent_gather: form.allow_concurrent_gather,
      is_enabled: form.is_enabled,
    };

    try {
      await dispatch(
        adminUpdateGatheringNode({
          locationId,
          nodeId: node.id,
          body,
        }),
      ).unwrap();
      toast.success('Нода обновлена');
      setIsEditing(false);
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось обновить ноду');
    }
  };

  const handleDelete = async () => {
    const confirmed = window.confirm(`Удалить ноду «${node.node_name}»?`);
    if (!confirmed) return;
    try {
      await dispatch(
        adminDeleteGatheringNode({ locationId, nodeId: node.id }),
      ).unwrap();
      toast.success('Нода удалена');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось удалить ноду');
    }
  };

  const handleRestore = async () => {
    try {
      await dispatch(
        adminRestoreGatheringNode({ locationId, nodeId: node.id }),
      ).unwrap();
      toast.success('Запас ноды восстановлен');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось восстановить запас');
    }
  };

  // ── View mode ────────────────────────────────────────────────────────────
  if (!isEditing) {
    return (
      <div className="bg-black/30 border border-white/10 rounded p-3 sm:p-4 flex flex-col gap-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[#a8c6df] font-medium break-words">
                {node.node_name}
              </span>
              <span className="text-xs text-[#8ab3d5] uppercase tracking-wider">
                {CATEGORY_LABEL[node.category]}
              </span>
              {!node.is_enabled && (
                <span className="text-xs bg-site-red/20 text-site-red px-2 py-0.5 rounded">
                  Выключена
                </span>
              )}
              {node.depleted_at && (
                <span className="text-xs bg-yellow-500/20 text-yellow-300 px-2 py-0.5 rounded">
                  Истощена
                </span>
              )}
            </div>
            <div className="mt-1 text-xs text-white/60">
              ID: {node.id}
            </div>
          </div>
          {canEdit && (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={startEdit}
                disabled={isAdminLoading}
                className="px-3 py-1.5 bg-blue-500/20 text-white text-sm rounded hover:bg-blue-500/30 transition-colors disabled:opacity-50"
              >
                Изменить
              </button>
              <button
                type="button"
                onClick={handleRestore}
                disabled={isAdminLoading}
                className="px-3 py-1.5 bg-green-500/20 text-white text-sm rounded hover:bg-green-500/30 transition-colors disabled:opacity-50"
                title="Сбросить запас до максимума и снять состояние истощения"
              >
                Восстановить запас
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={isAdminLoading}
                className="px-3 py-1.5 bg-red-500/20 text-white text-sm rounded hover:bg-red-500/30 transition-colors disabled:opacity-50"
              >
                Удалить
              </button>
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2 text-xs text-[#d4e6f3]">
          <div>
            <div className="text-white/50 uppercase">Предмет</div>
            <div className="truncate">
              {node.result_item_name || `#${node.result_item_id}`}
              <span className="text-white/40"> (ID: {node.result_item_id})</span>
            </div>
          </div>
          <div>
            <div className="text-white/50 uppercase">Кол-во / сбор</div>
            <div>{node.result_quantity_per_gather}</div>
          </div>
          <div>
            <div className="text-white/50 uppercase">Стамина</div>
            <div>{node.stamina_per_gather}</div>
          </div>
          <div>
            <div className="text-white/50 uppercase">Запас (тек./макс.)</div>
            <div>
              {node.current_bank} / {node.daily_bank_max}
            </div>
          </div>
          <div>
            <div className="text-white/50 uppercase">Параллельный сбор</div>
            <div>{node.allow_concurrent_gather ? 'Да' : 'Нет'}</div>
          </div>
          <div>
            <div className="text-white/50 uppercase">Истощена</div>
            <div>{formatDate(node.depleted_at)}</div>
          </div>
          <div>
            <div className="text-white/50 uppercase">Восстановится</div>
            <div>{formatDate(node.restore_at)}</div>
          </div>
        </div>
      </div>
    );
  }

  // ── Edit mode ────────────────────────────────────────────────────────────
  return (
    <div className="bg-black/40 border border-blue-500/30 rounded p-3 sm:p-4 flex flex-col gap-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className="text-[#8ab3d5] text-xs uppercase">Название</span>
          <input
            type="text"
            value={form.node_name}
            onChange={(e) =>
              setForm((p) => ({ ...p, node_name: e.target.value }))
            }
            className="w-full p-2 bg-black/30 border border-white/10 rounded text-[#d4e6f3] focus:border-site-blue/50 focus:outline-none"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[#8ab3d5] text-xs uppercase">Категория</span>
          <select
            value={form.category}
            onChange={(e) =>
              setForm((p) => ({
                ...p,
                category: e.target.value as GatheringCategory,
              }))
            }
            className="w-full p-2 bg-black/30 border border-white/10 rounded text-[#d4e6f3] focus:border-site-blue/50 focus:outline-none"
          >
            {CATEGORY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[#8ab3d5] text-xs uppercase">
            ID предмета (результат)
          </span>
          <input
            type="number"
            min={1}
            value={form.result_item_id || ''}
            onChange={(e) =>
              setForm((p) => ({
                ...p,
                result_item_id:
                  e.target.value === '' ? 0 : Number(e.target.value),
              }))
            }
            className="w-full p-2 bg-black/30 border border-white/10 rounded text-[#d4e6f3] focus:border-site-blue/50 focus:outline-none"
          />
          {node.result_item_name && (
            <span className="text-xs text-white/50">
              Текущий: {node.result_item_name}
            </span>
          )}
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[#8ab3d5] text-xs uppercase">
            Количество / сбор
          </span>
          <input
            type="number"
            min={1}
            value={form.result_quantity_per_gather}
            onChange={(e) =>
              setForm((p) => ({
                ...p,
                result_quantity_per_gather:
                  e.target.value === '' ? 1 : Number(e.target.value),
              }))
            }
            className="w-full p-2 bg-black/30 border border-white/10 rounded text-[#d4e6f3] focus:border-site-blue/50 focus:outline-none"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[#8ab3d5] text-xs uppercase">
            Стамина / сбор
          </span>
          <input
            type="number"
            min={1}
            value={form.stamina_per_gather}
            onChange={(e) =>
              setForm((p) => ({
                ...p,
                stamina_per_gather:
                  e.target.value === '' ? 1 : Number(e.target.value),
              }))
            }
            className="w-full p-2 bg-black/30 border border-white/10 rounded text-[#d4e6f3] focus:border-site-blue/50 focus:outline-none"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[#8ab3d5] text-xs uppercase">
            Дневной запас
          </span>
          <input
            type="number"
            min={1}
            value={form.daily_bank_max}
            onChange={(e) =>
              setForm((p) => ({
                ...p,
                daily_bank_max:
                  e.target.value === '' ? 1 : Number(e.target.value),
              }))
            }
            className="w-full p-2 bg-black/30 border border-white/10 rounded text-[#d4e6f3] focus:border-site-blue/50 focus:outline-none"
          />
        </label>

        <label className="flex items-center gap-2 text-[#d4e6f3] cursor-pointer">
          <input
            type="checkbox"
            checked={form.allow_concurrent_gather}
            onChange={(e) =>
              setForm((p) => ({
                ...p,
                allow_concurrent_gather: e.target.checked,
              }))
            }
            className="w-4 h-4"
          />
          Разрешить параллельный сбор
        </label>

        <label className="flex items-center gap-2 text-[#d4e6f3] cursor-pointer">
          <input
            type="checkbox"
            checked={form.is_enabled}
            onChange={(e) =>
              setForm((p) => ({ ...p, is_enabled: e.target.checked }))
            }
            className="w-4 h-4"
          />
          Включена
        </label>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleSave}
          disabled={isAdminLoading}
          className="px-4 py-2 bg-site-blue text-white rounded hover:bg-[#5d8fa8] transition-colors disabled:opacity-50"
        >
          {isAdminLoading ? 'Сохранение...' : 'Сохранить'}
        </button>
        <button
          type="button"
          onClick={cancelEdit}
          disabled={isAdminLoading}
          className="px-4 py-2 bg-white/10 text-white rounded hover:bg-white/20 transition-colors disabled:opacity-50"
        >
          Отмена
        </button>
      </div>
    </div>
  );
};

export default NodeRow;
