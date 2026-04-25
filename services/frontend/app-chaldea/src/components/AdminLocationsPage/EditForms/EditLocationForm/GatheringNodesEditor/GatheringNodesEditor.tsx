/**
 * GatheringNodesEditor — admin sub-component embedded into <EditLocationForm>.
 *
 * Responsibilities (FEAT-128 task #24):
 *  - On mount: load list of gathering nodes for the current location
 *    via `adminListGatheringNodes(locationId)` thunk.
 *  - Permission gate: hide the editor (with a small note) for users that
 *    do not have any `gathering:*` permission. Admin role bypasses the gate.
 *  - List nodes via <NodeRow> (view + inline edit + delete + manual restore).
 *  - "+ Добавить ноду" inline form for creating a new node.
 *  - Surface API errors in Russian via toast.
 *
 * Constraints: Tailwind only, no React.FC, mobile responsive.
 */
import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../../../redux/store';
import {
  selectPermissions,
  selectRole,
} from '../../../../../redux/slices/userSlice';
import { hasModuleAccess } from '../../../../../utils/permissions';
import {
  adminListGatheringNodes,
  adminCreateGatheringNode,
  selectAdminGatheringNodes,
  selectGatheringIsAdminLoading,
  selectGatheringError,
  clearGatheringError,
} from '../../../../../redux/slices/gatheringSlice';
import type {
  GatheringCategory,
  GatheringNodeAdminCreate,
} from '../../../../../types/gathering';
import useDebounce from '../../../../../hooks/useDebounce';
import NodeRow from './NodeRow';

interface GatheringNodesEditorProps {
  locationId: number;
}

interface ItemSearchResult {
  id: number;
  name: string;
  rarity?: string;
}

interface CreateFormState {
  node_name: string;
  category: GatheringCategory;
  result_item_id: number;
  result_item_name: string;
  result_quantity_per_gather: number;
  stamina_per_gather: number;
  daily_bank_max: number;
  allow_concurrent_gather: boolean;
  is_enabled: boolean;
}

const CATEGORY_OPTIONS: { value: GatheringCategory; label: string }[] = [
  { value: 'ore', label: 'Руда' },
  { value: 'herb', label: 'Травы' },
  { value: 'wood', label: 'Дерево' },
];

const INITIAL_FORM: CreateFormState = {
  node_name: '',
  category: 'ore',
  result_item_id: 0,
  result_item_name: '',
  result_quantity_per_gather: 1,
  stamina_per_gather: 1,
  daily_bank_max: 10,
  allow_concurrent_gather: false,
  is_enabled: true,
};

const GatheringNodesEditor = ({ locationId }: GatheringNodesEditorProps) => {
  const dispatch = useAppDispatch();
  const role = useAppSelector(selectRole);
  const permissions = useAppSelector(selectPermissions);
  const nodes = useAppSelector(selectAdminGatheringNodes);
  const isAdminLoading = useAppSelector(selectGatheringIsAdminLoading);
  const error = useAppSelector(selectGatheringError);

  // Permission check: admin bypasses, otherwise need any gathering:* perm.
  const canManage = useMemo(
    () => role === 'admin' || hasModuleAccess(permissions, 'gathering'),
    [role, permissions],
  );

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<CreateFormState>(INITIAL_FORM);

  // Item search state for the create form
  const [searchQuery, setSearchQuery] = useState('');
  const debouncedQuery = useDebounce(searchQuery);
  const [searchResults, setSearchResults] = useState<ItemSearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // Load nodes when locationId changes.
  useEffect(() => {
    if (!canManage) return;
    if (!locationId || locationId <= 0) return;
    dispatch(adminListGatheringNodes(locationId));
  }, [dispatch, locationId, canManage]);

  // Surface slice errors to the user (visible feedback per CLAUDE.md mandate).
  useEffect(() => {
    if (error) {
      toast.error(error);
      dispatch(clearGatheringError());
    }
  }, [error, dispatch]);

  // Item search query
  useEffect(() => {
    if (!debouncedQuery) {
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    axios
      .get('/inventory/items', {
        params: { q: debouncedQuery, page: 1, page_size: 20 },
      })
      .then((res) => {
        const data = res.data;
        const items = Array.isArray(data) ? data : (data.items ?? []);
        setSearchResults(items);
      })
      .catch(() => toast.error('Не удалось найти предметы'))
      .finally(() => setSearchLoading(false));
  }, [debouncedQuery]);

  const filteredNodes = useMemo(
    () => nodes.filter((n) => n.location_id === locationId),
    [nodes, locationId],
  );

  // Permission gate ─────────────────────────────────────────────────────────
  if (!canManage) {
    return (
      <div className="mt-4 w-full">
        <p className="text-sm text-white/60">
          Нет прав на управление нодами
        </p>
      </div>
    );
  }

  const resetCreateForm = () => {
    setForm(INITIAL_FORM);
    setSearchQuery('');
    setSearchResults([]);
  };

  const handlePickItem = (item: ItemSearchResult) => {
    setForm((p) => ({
      ...p,
      result_item_id: item.id,
      result_item_name: item.name,
    }));
    setSearchQuery('');
    setSearchResults([]);
  };

  const validateCreate = (): boolean => {
    if (!form.node_name.trim()) {
      toast.error('Введите название ноды');
      return false;
    }
    if (!Number.isInteger(form.result_item_id) || form.result_item_id <= 0) {
      toast.error('Выберите предмет (ID > 0)');
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

  const handleCreate = async () => {
    if (!validateCreate()) return;
    const body: GatheringNodeAdminCreate = {
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
        adminCreateGatheringNode({ locationId, body }),
      ).unwrap();
      toast.success('Нода создана');
      resetCreateForm();
      setShowCreate(false);
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось создать ноду');
    }
  };

  const handleCancelCreate = () => {
    resetCreateForm();
    setShowCreate(false);
  };

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="mt-4 w-full">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h3 className="text-white font-medium">Ноды добычи</h3>
        {!showCreate && (
          <button
            type="button"
            onClick={() => setShowCreate(true)}
            className="px-3 py-1.5 bg-blue-500/20 text-white text-sm rounded hover:bg-blue-500/30 transition-colors"
          >
            + Добавить ноду
          </button>
        )}
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="mb-4 bg-black/40 border border-blue-500/30 rounded p-3 sm:p-4 flex flex-col gap-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className="text-[#8ab3d5] text-xs uppercase">Название</span>
              <input
                type="text"
                value={form.node_name}
                onChange={(e) =>
                  setForm((p) => ({ ...p, node_name: e.target.value }))
                }
                placeholder="Например: Богатая жила меди"
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

            <div className="flex flex-col gap-1 sm:col-span-2">
              <span className="text-[#8ab3d5] text-xs uppercase">
                Предмет (результат сбора)
              </span>
              {form.result_item_id > 0 && (
                <div className="flex items-center gap-2 text-sm bg-black/30 border border-white/10 rounded px-2 py-1">
                  <span className="text-white">
                    {form.result_item_name || `Предмет #${form.result_item_id}`}
                  </span>
                  <span className="text-white/40 text-xs">
                    ID: {form.result_item_id}
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      setForm((p) => ({
                        ...p,
                        result_item_id: 0,
                        result_item_name: '',
                      }))
                    }
                    className="ml-auto text-xs text-site-red hover:text-white transition-colors"
                  >
                    Сбросить
                  </button>
                </div>
              )}
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Поиск предмета по названию..."
                className="w-full p-2 bg-black/30 border border-white/10 rounded text-[#d4e6f3] focus:border-site-blue/50 focus:outline-none"
              />
              {searchLoading && (
                <div className="flex items-center gap-2 text-white/50 text-xs">
                  <div className="w-3 h-3 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
                  Поиск...
                </div>
              )}
              {searchResults.length > 0 && (
                <div className="flex flex-col gap-1 max-h-[200px] overflow-y-auto gold-scrollbar bg-black/30 rounded">
                  {searchResults.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => handlePickItem(item)}
                      className="flex items-center gap-2 px-3 py-2 rounded text-left text-sm transition-colors hover:bg-white/[0.07]"
                    >
                      <span className="text-white">{item.name}</span>
                      <span className="text-white/40 text-xs">
                        ID: {item.id}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>

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
              onClick={handleCreate}
              disabled={isAdminLoading}
              className="px-4 py-2 bg-site-blue text-white rounded hover:bg-[#5d8fa8] transition-colors disabled:opacity-50"
            >
              {isAdminLoading ? 'Создание...' : 'Создать'}
            </button>
            <button
              type="button"
              onClick={handleCancelCreate}
              disabled={isAdminLoading}
              className="px-4 py-2 bg-white/10 text-white rounded hover:bg-white/20 transition-colors disabled:opacity-50"
            >
              Отмена
            </button>
          </div>
        </div>
      )}

      {/* List */}
      <div className="flex flex-col gap-3 max-h-[500px] overflow-y-auto gold-scrollbar pr-1">
        {isAdminLoading && filteredNodes.length === 0 && (
          <div className="text-center text-white/60 py-3 text-sm">
            Загрузка...
          </div>
        )}
        {!isAdminLoading && filteredNodes.length === 0 && (
          <div className="text-center text-[#8ab3d5] py-3 text-sm">
            Нет нод в этой локации
          </div>
        )}
        {filteredNodes.map((node) => (
          <NodeRow
            key={node.id}
            locationId={locationId}
            node={node}
            canEdit={canManage}
          />
        ))}
      </div>
    </div>
  );
};

export default GatheringNodesEditor;
