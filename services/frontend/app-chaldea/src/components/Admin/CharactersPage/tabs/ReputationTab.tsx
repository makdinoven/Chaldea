import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import {
  fetchCharacterReputationAdmin,
  fetchCharacterReputationHistoryAdmin,
  fetchReputationActions,
  newRequestId,
  postCharacterReputationAdjust,
  type ReputationAction,
  type ReputationAdminHistoryItem,
  type ReputationAdminRegion,
  type ReputationAdjustBody,
} from '../../../../api/reputationAdmin';
import { fetchWorldGraph } from '../../../../api/worldGraph';
import { apiErrorMessage } from '../../../../api/errors';
import { useAppSelector } from '../../../../redux/store';
import { selectPermissions } from '../../../../redux/slices/userSlice';
import { hasPermission } from '../../../../utils/permissions';
import { tierIndex } from '../../ReputationPage/useReputationRefs';

interface ReputationTabProps {
  characterId: number;
}

interface RegionOption {
  id: number;
  name: string;
  countryName: string;
}

type AdjustMode = 'delta' | 'action';

const LABEL = 'text-white/50 text-xs font-medium uppercase tracking-[0.06em]';
const HISTORY_PAGE_SIZE = 20;
const DELTA_LIMIT = 2000;
const REASON_MIN = 3;
const REASON_MAX = 500;
const INT_RE = /^-?\d*$/;
const BAD_TIER_MAX_INDEX = 2; // outlaw, outcast, watched
const GOOD_TIER_MIN_INDEX = 4; // familiar and up

const tierClass = (code: string): string => {
  const i = tierIndex(code);
  if (i >= 0 && i <= BAD_TIER_MAX_INDEX) return 'text-site-red';
  if (i >= GOOD_TIER_MIN_INDEX) return 'text-gold';
  return 'text-white/80';
};

const formatDate = (iso: string | null): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const signed = (n: number): string => (n > 0 ? `+${n}` : String(n));

const deltaClass = (n: number): string => (n > 0 ? 'text-green-400' : n < 0 ? 'text-site-red' : 'text-white/60');

/** Admin character card «Репутация» (FEAT-197): numbers per region, manual edit with a reason, full journal. */
const ReputationTab = ({ characterId }: ReputationTabProps) => {
  const canManage = hasPermission(useAppSelector(selectPermissions), 'reputation:manage');

  const [regions, setRegions] = useState<ReputationAdminRegion[] | null>(null);
  const [regionsError, setRegionsError] = useState<string | null>(null);

  const [history, setHistory] = useState<ReputationAdminHistoryItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyRegion, setHistoryRegion] = useState<number | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const [allRegions, setAllRegions] = useState<RegionOption[]>([]);
  const [actions, setActions] = useState<ReputationAction[]>([]);
  const [mode, setMode] = useState<AdjustMode>('delta');
  const [regionId, setRegionId] = useState<number | null>(null);
  const [delta, setDelta] = useState('');
  const [actionCode, setActionCode] = useState('');
  const [reason, setReason] = useState('');
  const [echo, setEcho] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadRegions = useCallback(() => {
    fetchCharacterReputationAdmin(characterId)
      .then((list) => {
        setRegions(list);
        setRegionsError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить репутацию персонажа');
        setRegionsError(msg);
        toast.error(msg);
      });
  }, [characterId]);

  const loadHistory = useCallback(() => {
    setHistoryLoading(true);
    fetchCharacterReputationHistoryAdmin(characterId, {
      region_id: historyRegion,
      page: historyPage,
      page_size: HISTORY_PAGE_SIZE,
    })
      .then((p) => {
        setHistory(p.items);
        setHistoryTotal(p.total);
        setHistoryError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить журнал репутации');
        setHistoryError(msg);
        toast.error(msg);
      })
      .finally(() => setHistoryLoading(false));
  }, [characterId, historyRegion, historyPage]);

  useEffect(loadRegions, [loadRegions]);
  useEffect(loadHistory, [loadHistory]);

  // The adjust form needs every region (the character may have no row there yet) and the action list.
  useEffect(() => {
    if (!canManage) return undefined;
    let cancelled = false;
    fetchWorldGraph()
      .then((g) => {
        if (cancelled) return;
        const countries = new Map(g.countries.map((c) => [c.id, c.name]));
        setAllRegions(
          g.regions
            .map((r) => ({ id: r.id, name: r.name, countryName: countries.get(r.country_id) ?? 'Без страны' }))
            .sort((a, b) => a.countryName.localeCompare(b.countryName, 'ru') || a.name.localeCompare(b.name, 'ru')),
        );
      })
      .catch((e) => {
        if (!cancelled) toast.error(apiErrorMessage(e, 'Не удалось загрузить список регионов'));
      });
    fetchReputationActions()
      .then((list) => {
        if (!cancelled) setActions([...list].sort((a, b) => a.sort_order - b.sort_order));
      })
      .catch((e) => {
        if (!cancelled) toast.error(apiErrorMessage(e, 'Не удалось загрузить действия репутации'));
      });
    return () => {
      cancelled = true;
    };
  }, [canManage]);

  const regionGroups = useMemo(() => {
    const groups = new Map<string, RegionOption[]>();
    allRegions.forEach((r) => {
      const list = groups.get(r.countryName) ?? [];
      list.push(r);
      groups.set(r.countryName, list);
    });
    return Array.from(groups.entries());
  }, [allRegions]);

  // Actions usable for a manual edit: with non-zero points (npc_kill / admin_manual carry no fixed weight).
  const usableActions = useMemo(() => actions.filter((a) => a.points !== 0), [actions]);

  const historyRegionOptions = useMemo(() => {
    const map = new Map<number, string>();
    (regions ?? []).forEach((r) => map.set(r.region_id, r.region_name ?? `Регион #${r.region_id}`));
    return Array.from(map.entries()).sort((a, b) => a[1].localeCompare(b[1], 'ru'));
  }, [regions]);

  const validate = (): string | null => {
    if (!regionId) return 'Выберите регион';
    if (mode === 'delta') {
      const n = Number(delta);
      if (delta.trim() === '' || delta === '-' || !Number.isInteger(n)) return 'Укажите изменение целым числом';
      if (n === 0) return 'Изменение не может быть нулевым';
      if (Math.abs(n) > DELTA_LIMIT) return `Изменение — от −${DELTA_LIMIT} до ${DELTA_LIMIT}`;
    } else if (!actionCode) {
      return 'Выберите действие';
    }
    const r = reason.trim();
    if (r.length < REASON_MIN) return `Причина обязательна — не короче ${REASON_MIN} символов`;
    if (r.length > REASON_MAX) return `Причина — не длиннее ${REASON_MAX} символов`;
    return null;
  };

  const submit = async () => {
    const err = validate();
    if (err || !regionId) {
      setFormError(err ?? 'Выберите регион');
      return;
    }
    setFormError(null);
    const body: ReputationAdjustBody = {
      region_id: regionId,
      reason: reason.trim(),
      echo,
      request_id: newRequestId(),
      ...(mode === 'delta' ? { delta: Number(delta) } : { action_code: actionCode }),
    };
    setSubmitting(true);
    try {
      const result = await postCharacterReputationAdjust(characterId, body);
      if (result.duplicate) {
        toast('Эта правка уже была применена');
      } else {
        const origin = result.changes.find((c) => !c.is_echo && c.region_id === regionId) ?? result.changes[0];
        toast.success(
          origin
            ? `Репутация изменена: ${origin.value_before} → ${origin.value_after}` +
                (result.changes.length > 1 ? ` (отголосок: регионов ${result.changes.length - 1})` : '')
            : 'Репутация не изменилась (граница диапазона)',
        );
      }
      setDelta('');
      setReason('');
      loadRegions();
      if (historyPage === 1) loadHistory();
      else setHistoryPage(1);
    } catch (e) {
      const msg = apiErrorMessage(e, 'Не удалось изменить репутацию');
      setFormError(msg);
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(historyTotal / HISTORY_PAGE_SIZE));

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.2 }}
      className="flex flex-col gap-6"
    >
      {/* Per-region values */}
      <section className="gray-bg p-4 sm:p-6 flex flex-col gap-4 min-w-0">
        <h2 className="gold-text text-xl font-medium uppercase tracking-[0.06em]">По регионам</h2>
        {regionsError && !regions && <p className="text-site-red text-sm">{regionsError}</p>}
        {!regions && !regionsError && (
          <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        )}
        {regions && regions.length === 0 && (
          <p className="text-white/50 text-sm">Репутация ещё нигде не менялась — во всех регионах стартовая ступень.</p>
        )}
        {regions && regions.length > 0 && (
          <div className="flex flex-col divide-y divide-white/[0.06]">
            {regions.map((r) => (
              <div key={r.region_id} className="grid grid-cols-2 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1.5fr)_minmax(0,1.5fr)] gap-x-3 gap-y-1 py-2 items-center">
                <div className="col-span-2 sm:col-span-1 min-w-0">
                  <div className="text-white text-sm truncate">{r.region_name ?? `Регион #${r.region_id}`}</div>
                  <div className="text-white/40 text-xs truncate">{r.country_name ?? 'Без страны'}</div>
                </div>
                <div className={`text-base font-medium ${deltaClass(r.value)}`}>{r.value}</div>
                <div className={`text-sm ${tierClass(r.tier_code)}`}>
                  {r.tier_name}
                  {r.decaying && <span className="block text-white/40 text-xs">забывается</span>}
                </div>
                <div className="text-white/40 text-xs col-span-2 sm:col-span-1">{formatDate(r.updated_at)}</div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Manual edit */}
      {canManage && (
        <section className="gray-bg p-4 sm:p-6 flex flex-col gap-4 min-w-0">
          <h2 className="gold-text text-xl font-medium uppercase tracking-[0.06em]">Изменить репутацию</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <label className="flex flex-col gap-1 min-w-0">
              <span className={LABEL}>Регион</span>
              <select className="input-underline w-full" value={regionId ?? ''} disabled={submitting}
                onChange={(e) => setRegionId(e.target.value ? Number(e.target.value) : null)}>
                <option value="" className="bg-site-dark text-white">Выберите регион</option>
                {regionGroups.map(([country, list]) => (
                  <optgroup key={country} label={country} className="bg-site-dark text-white/60">
                    {list.map((r) => (
                      <option key={r.id} value={r.id} className="bg-site-dark text-white">{r.name}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>

            <div className="flex flex-col gap-1 min-w-0">
              <span className={LABEL}>Как изменить</span>
              <div className="grid grid-cols-2 gap-2">
                {(['delta', 'action'] as AdjustMode[]).map((m) => (
                  <button key={m} type="button" disabled={submitting} onClick={() => setMode(m)}
                    className={`chip-outline rounded-card px-3 py-2 text-sm ${mode === m ? 'chip-outline-active' : ''}`}>
                    {m === 'delta' ? 'Числом' : 'Действием'}
                  </button>
                ))}
              </div>
            </div>

            {mode === 'delta' ? (
              <label className="flex flex-col gap-1 min-w-0">
                <span className={LABEL}>Изменение (±)</span>
                <input className="input-underline w-full" inputMode="numeric" placeholder="например, -50 или 100"
                  value={delta} disabled={submitting}
                  onChange={(e) => INT_RE.test(e.target.value) && setDelta(e.target.value)} />
              </label>
            ) : (
              <label className="flex flex-col gap-1 min-w-0">
                <span className={LABEL}>Действие</span>
                <select className="input-underline w-full" value={actionCode} disabled={submitting}
                  onChange={(e) => setActionCode(e.target.value)}>
                  <option value="" className="bg-site-dark text-white">Выберите действие</option>
                  {usableActions.map((a) => (
                    <option key={a.code} value={a.code} className="bg-site-dark text-white">
                      {a.name} ({signed(a.points)})
                    </option>
                  ))}
                </select>
              </label>
            )}

            <label className="flex items-start gap-3 cursor-pointer select-none md:self-end md:pb-1">
              <input type="checkbox" className="w-4 h-4 mt-0.5 shrink-0 accent-gold" checked={echo} disabled={submitting}
                onChange={(e) => setEcho(e.target.checked)} />
              <span className="flex flex-col gap-0.5">
                <span className="text-white text-sm">С отголоском</span>
                <span className="text-white/40 text-xs">Часть изменения уйдёт в остальные регионы той же страны</span>
              </span>
            </label>
          </div>

          <label className="flex flex-col gap-1">
            <span className={LABEL}>Причина (обязательно)</span>
            <textarea className="textarea-bordered text-sm" rows={3} maxLength={REASON_MAX} value={reason}
              disabled={submitting} placeholder="За что меняется репутация — видно только в админке"
              onChange={(e) => setReason(e.target.value)} />
            <span className="text-white/40 text-xs self-end">{reason.trim().length}/{REASON_MAX}</span>
          </label>

          {formError && <p className="text-site-red text-sm">{formError}</p>}

          <div>
            <button type="button" className="btn-blue w-full sm:w-auto !px-8 disabled:opacity-50"
              disabled={submitting || reason.trim().length < REASON_MIN} onClick={() => void submit()}>
              {submitting ? 'Применение...' : 'Применить'}
            </button>
          </div>
        </section>
      )}

      {/* Journal */}
      <section className="gray-bg p-4 sm:p-6 flex flex-col gap-4 min-w-0">
        <div className="flex flex-col sm:flex-row sm:items-end gap-3 sm:justify-between">
          <h2 className="gold-text text-xl font-medium uppercase tracking-[0.06em]">Журнал</h2>
          <label className="flex flex-col gap-1 sm:w-64">
            <span className={LABEL}>Регион</span>
            <select className="input-underline w-full" value={historyRegion ?? ''}
              onChange={(e) => {
                setHistoryRegion(e.target.value ? Number(e.target.value) : null);
                setHistoryPage(1);
              }}>
              <option value="" className="bg-site-dark text-white">Все регионы</option>
              {historyRegionOptions.map(([id, name]) => (
                <option key={id} value={id} className="bg-site-dark text-white">{name}</option>
              ))}
            </select>
          </label>
        </div>

        {historyError && <p className="text-site-red text-sm">{historyError}</p>}
        {historyLoading && history.length === 0 && !historyError && (
          <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        )}
        {!historyLoading && !historyError && history.length === 0 && (
          <p className="text-white/50 text-sm">Записей нет</p>
        )}

        {history.length > 0 && (
          <div className={`flex flex-col divide-y divide-white/[0.06] ${historyLoading ? 'opacity-60' : ''}`}>
            {history.map((h) => (
              <div key={h.id} className="py-3 flex flex-col gap-1.5 min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="text-white/40 text-xs">{formatDate(h.created_at)}</span>
                  <span className="text-white text-sm">{h.region_name ?? `Регион #${h.region_id}`}</span>
                  {h.is_echo && (
                    <span className="text-white/50 text-xs">
                      отголосок{h.origin_region_name ? ` из «${h.origin_region_name}»` : ''}
                    </span>
                  )}
                  <span className="text-white/70 text-sm">{h.action_name}</span>
                </div>
                <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
                  <span className={`font-medium ${deltaClass(h.applied_delta)}`}>
                    {signed(h.applied_delta)}
                    {h.applied_delta !== h.requested_delta && (
                      <span className="text-white/40 text-xs font-normal"> (запрошено {signed(h.requested_delta)})</span>
                    )}
                  </span>
                  <span className="text-white/60">итог: {h.value_after}</span>
                  <span>
                    {h.tier_before !== h.tier_after ? (
                      <>
                        <span className={tierClass(h.tier_before)}>{h.tier_before_name}</span>
                        <span className="text-white/40"> → </span>
                        <span className={tierClass(h.tier_after)}>{h.tier_after_name}</span>
                      </>
                    ) : (
                      <span className={tierClass(h.tier_after)}>{h.tier_after_name}</span>
                    )}
                  </span>
                </div>
                {(h.reason || h.actor_username) && (
                  <div className="text-xs text-white/50 break-words">
                    {h.actor_username && <span className="text-white/70">{h.actor_username}: </span>}
                    {h.reason}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-3">
            <button type="button" className="btn-line !w-auto !px-4 !py-1 !text-sm disabled:opacity-40"
              disabled={historyPage <= 1 || historyLoading} onClick={() => setHistoryPage((p) => p - 1)}>
              Назад
            </button>
            <span className="text-white/60 text-sm">{historyPage} / {totalPages}</span>
            <button type="button" className="btn-line !w-auto !px-4 !py-1 !text-sm disabled:opacity-40"
              disabled={historyPage >= totalPages || historyLoading} onClick={() => setHistoryPage((p) => p + 1)}>
              Вперёд
            </button>
          </div>
        )}
      </section>
    </motion.div>
  );
};

export default ReputationTab;
