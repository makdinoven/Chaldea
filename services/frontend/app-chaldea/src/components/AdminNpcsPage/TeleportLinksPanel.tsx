import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useSelector } from 'react-redux';
import { BASE_URL } from '../../api/api';
import { useAppDispatch } from '../../redux/store';
import type { RootState } from '../../redux/store';
import {
  fetchAdminTeleportLinks,
  createTeleportLink,
  updateTeleportLink,
  deleteTeleportLink,
  selectAdminTeleportLinks,
  selectAdminTeleportLoading,
  selectAdminTeleportSaving,
  type TeleportLink,
} from '../../redux/slices/teleportSlice';

interface TeleportMasterOption {
  id: number;
  name: string;
  location_name?: string | null;
}

interface AdminNpcListItem {
  id: number;
  name: string;
  npc_role?: string | null;
  location_name?: string | null;
}

interface TeleportLinksPanelProps {
  npcId: number;
}

const TOOLTIP_TEXT =
  'Изменение стоимости одной стороны не обновляет обратную связь автоматически';

const TeleportLinksPanel = ({ npcId }: TeleportLinksPanelProps) => {
  const dispatch = useAppDispatch();
  const links = useSelector((state: RootState) => selectAdminTeleportLinks(npcId)(state)) ?? [];
  const loading = useSelector(selectAdminTeleportLoading);
  const saving = useSelector(selectAdminTeleportSaving);

  const [search, setSearch] = useState('');
  const [searchResults, setSearchResults] = useState<TeleportMasterOption[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState<TeleportMasterOption | null>(null);
  const [costGold, setCostGold] = useState<number>(0);
  const [bidirectional, setBidirectional] = useState<boolean>(true);

  const [editingLinkId, setEditingLinkId] = useState<number | null>(null);
  const [editingCost, setEditingCost] = useState<number>(0);

  // Cache: target NPC info for already-known links (for showing names)
  const [targetCache, setTargetCache] = useState<Record<number, TeleportMasterOption>>({});

  // Load links on mount / npc change
  useEffect(() => {
    if (npcId) {
      dispatch(fetchAdminTeleportLinks(npcId));
    }
  }, [dispatch, npcId]);

  // Search NPCs filtered by teleport_master role
  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setSearching(true);
      try {
        const params: Record<string, string> = {
          npc_role: 'teleport_master',
          page: '1',
          page_size: '20',
        };
        if (search.trim()) params.q = search.trim();
        const res = await axios.get(`${BASE_URL}/characters/admin/npcs`, { params });
        const data = res.data;
        const items: AdminNpcListItem[] = Array.isArray(data) ? data : (data.items ?? []);
        if (cancelled) return;
        const mapped: TeleportMasterOption[] = items
          .filter((n) => n.id !== npcId)
          .map((n) => ({ id: n.id, name: n.name, location_name: n.location_name ?? null }));
        setSearchResults(mapped);
      } catch {
        if (!cancelled) {
          toast.error('Не удалось загрузить список Мастеров Телепорта');
          setSearchResults([]);
        }
      } finally {
        if (!cancelled) setSearching(false);
      }
    };
    const handle = setTimeout(run, 250);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [search, npcId]);

  // Fetch missing target NPC names for displayed links
  useEffect(() => {
    const missing = links
      .map((l) => l.to_npc_id)
      .filter((id) => !(id in targetCache));
    if (missing.length === 0) return;
    let cancelled = false;
    (async () => {
      const fresh: Record<number, TeleportMasterOption> = {};
      await Promise.all(
        missing.map(async (id) => {
          try {
            const res = await axios.get(`${BASE_URL}/characters/admin/npcs/${id}`);
            const npc = res.data;
            fresh[id] = {
              id,
              name: npc?.name ?? `НПС #${id}`,
              location_name: npc?.location_name ?? npc?.current_location?.name ?? null,
            };
          } catch {
            fresh[id] = { id, name: `НПС #${id}`, location_name: null };
          }
        }),
      );
      if (!cancelled && Object.keys(fresh).length > 0) {
        setTargetCache((prev) => ({ ...prev, ...fresh }));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [links]);

  const handleSelectTarget = useCallback((opt: TeleportMasterOption) => {
    setSelectedTarget(opt);
    setSearch(opt.name);
    setSearchResults([]);
  }, []);

  const handleAdd = useCallback(async () => {
    if (!selectedTarget) {
      toast.error('Выберите целевого Мастера Телепорта');
      return;
    }
    if (selectedTarget.id === npcId) {
      toast.error('Нельзя связать NPC с самим собой');
      return;
    }
    if (costGold < 0 || Number.isNaN(costGold)) {
      toast.error('Стоимость должна быть неотрицательным числом');
      return;
    }
    const result = await dispatch(
      createTeleportLink({
        from_npc_id: npcId,
        to_npc_id: selectedTarget.id,
        cost_gold: Math.floor(costGold),
        bidirectional,
      }),
    );
    if (createTeleportLink.fulfilled.match(result)) {
      setSelectedTarget(null);
      setSearch('');
      setCostGold(0);
      setBidirectional(true);
      // Re-fetch to ensure server-side state is reflected (esp. bidirectional)
      dispatch(fetchAdminTeleportLinks(npcId));
    }
  }, [dispatch, npcId, selectedTarget, costGold, bidirectional]);

  const startEdit = (link: TeleportLink) => {
    setEditingLinkId(link.id);
    setEditingCost(link.cost_gold);
  };

  const cancelEdit = () => {
    setEditingLinkId(null);
    setEditingCost(0);
  };

  const saveEdit = async (link: TeleportLink) => {
    if (editingCost < 0 || Number.isNaN(editingCost)) {
      toast.error('Стоимость должна быть неотрицательным числом');
      return;
    }
    const result = await dispatch(
      updateTeleportLink({ id: link.id, payload: { cost_gold: Math.floor(editingCost) } }),
    );
    if (updateTeleportLink.fulfilled.match(result)) {
      cancelEdit();
      dispatch(fetchAdminTeleportLinks(npcId));
    }
  };

  const handleDelete = async (link: TeleportLink) => {
    if (!window.confirm('Удалить связь телепорта? Обратная связь также будет удалена.')) return;
    const result = await dispatch(deleteTeleportLink({ id: link.id, deleteReverse: true }));
    if (deleteTeleportLink.fulfilled.match(result)) {
      dispatch(fetchAdminTeleportLinks(npcId));
    }
  };

  const showResults = useMemo(
    () => search.trim().length > 0 && (selectedTarget?.name ?? '') !== search,
    [search, selectedTarget],
  );

  return (
    <div className="gray-bg p-4 sm:p-6 flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h3 className="gold-text text-xl font-semibold uppercase tracking-[0.06em]">
          Связи телепорта
        </h3>
        <p className="text-white/50 text-xs" title={TOOLTIP_TEXT}>
          {TOOLTIP_TEXT}
        </p>
      </div>

      {/* Add new link */}
      <div className="flex flex-col gap-3 border border-white/10 rounded-md p-3 sm:p-4">
        <span className="text-white/60 text-xs font-medium uppercase tracking-[0.06em]">
          Новая связь
        </span>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
          <label className="flex flex-col gap-1 relative">
            <span className="text-white/50 text-xs">Целевой Мастер Телепорта</span>
            <input
              className="input-underline"
              placeholder="Поиск по имени..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setSelectedTarget(null);
              }}
            />
            {showResults && (
              <div className="absolute left-0 right-0 top-full mt-1 z-10 bg-site-dark border border-white/10 rounded-md max-h-56 overflow-auto shadow-card">
                {searching ? (
                  <div className="px-3 py-2 text-white/50 text-sm">Загрузка...</div>
                ) : searchResults.length === 0 ? (
                  <div className="px-3 py-2 text-white/50 text-sm">Ничего не найдено</div>
                ) : (
                  searchResults.map((opt) => (
                    <button
                      type="button"
                      key={opt.id}
                      onClick={() => handleSelectTarget(opt)}
                      className="w-full text-left px-3 py-2 text-sm text-white hover:bg-white/[0.08]"
                    >
                      <span className="font-medium">{opt.name}</span>
                      {opt.location_name && (
                        <span className="text-white/50 ml-2">— {opt.location_name}</span>
                      )}
                    </button>
                  ))
                )}
              </div>
            )}
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs">Стоимость (золото)</span>
            <input
              type="number"
              min={0}
              className="input-underline"
              value={costGold}
              onChange={(e) => setCostGold(Number(e.target.value))}
            />
          </label>
        </div>

        <label className="flex items-center gap-2 text-white/80 text-sm">
          <input
            type="checkbox"
            checked={bidirectional}
            onChange={(e) => setBidirectional(e.target.checked)}
            className="accent-gold"
          />
          <span>Двусторонняя связь (создать также обратное направление)</span>
        </label>

        <div>
          <button
            type="button"
            onClick={handleAdd}
            disabled={saving || !selectedTarget}
            className="btn-blue !text-sm !px-6 !py-2 disabled:opacity-50"
          >
            {saving ? 'Сохранение...' : 'Добавить связь'}
          </button>
        </div>
      </div>

      {/* Links list */}
      <div className="flex flex-col gap-2">
        <span className="text-white/60 text-xs font-medium uppercase tracking-[0.06em]">
          Существующие связи
        </span>
        {loading ? (
          <div className="flex items-center justify-center py-6">
            <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
          </div>
        ) : links.length === 0 ? (
          <div className="text-white/50 text-sm py-3">Связей пока нет</div>
        ) : (
          <ul className="flex flex-col gap-2">
            {links.map((link) => {
              const target = targetCache[link.to_npc_id];
              const isEditing = editingLinkId === link.id;
              return (
                <li
                  key={link.id}
                  className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 p-3 border border-white/10 rounded-md bg-white/[0.03]"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-white text-sm truncate">
                      → {target?.name ?? `НПС #${link.to_npc_id}`}
                    </div>
                    {target?.location_name && (
                      <div className="text-white/50 text-xs truncate">
                        {target.location_name}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    {isEditing ? (
                      <input
                        type="number"
                        min={0}
                        className="input-underline w-24"
                        value={editingCost}
                        onChange={(e) => setEditingCost(Number(e.target.value))}
                      />
                    ) : (
                      <span
                        className="px-2 py-0.5 rounded-full bg-gold/20 text-gold text-xs font-medium"
                        title={TOOLTIP_TEXT}
                      >
                        {link.cost_gold} зол.
                      </span>
                    )}

                    {isEditing ? (
                      <>
                        <button
                          type="button"
                          onClick={() => saveEdit(link)}
                          disabled={saving}
                          className="btn-blue !text-xs !px-3 !py-1 disabled:opacity-50"
                        >
                          ОК
                        </button>
                        <button
                          type="button"
                          onClick={cancelEdit}
                          className="btn-line !w-auto !text-xs !px-3 !py-1"
                        >
                          Отмена
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => startEdit(link)}
                          className="btn-line !w-auto !text-xs !px-3 !py-1"
                        >
                          Изменить
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(link)}
                          disabled={saving}
                          className="btn-line !w-auto !text-xs !px-3 !py-1 disabled:opacity-50"
                        >
                          Удалить
                        </button>
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
};

export default TeleportLinksPanel;
