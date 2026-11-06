// FEAT-207 — regions where a faction is outlawed: an open member there is an offender (guards react as to the
// wanted level), a secret one only if a guard's stealth roll reveals him. PUT replaces the whole list.
import { useCallback, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { X } from 'lucide-react';
import {
  FACTION_OUTLAW_REGIONS_MAX,
  adminFactionOutlawRegions,
  adminPutFactionOutlawRegions,
  type FactionOutlawRegionAdmin,
} from '../../../api/factions';
import { LAW_LEVEL_CODES, fetchLawSettings } from '../../../api/lawAdmin';
import { fetchWorldGraph } from '../../../api/worldGraph';
import { apiErrorMessage } from '../../../api/errors';
import { FIELD, LABEL, OPTION } from './adminShared';

interface OutlawRegionsEditorProps {
  factionId: number;
  isSecret: boolean;
  canEdit: boolean;
}

interface Row {
  key: number;
  region_id: number | null;
  level_code: string;
}

interface LevelOption {
  code: string;
  name: string;
  min_value: number | null;
}

const SECTION = 'gray-bg p-4 sm:p-6 flex flex-col gap-4 min-w-0';
const H3 = 'gold-text text-lg font-medium uppercase tracking-[0.06em]';

let rowKey = 0;
const rowsOf = (list: FactionOutlawRegionAdmin[]): Row[] =>
  list.map((r) => ({ key: ++rowKey, region_id: r.region_id, level_code: r.level_code }));

const OutlawRegionsEditor = ({ factionId, isSecret, canEdit }: OutlawRegionsEditorProps) => {
  const [saved, setSaved] = useState<FactionOutlawRegionAdmin[] | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [regions, setRegions] = useState<{ id: number; name: string }[]>([]);
  const [levels, setLevels] = useState<LevelOption[]>(LAW_LEVEL_CODES.map((code) => ({ code, name: code, min_value: null })));
  const [saving, setSaving] = useState(false);
  const ro = !canEdit;

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await adminFactionOutlawRegions(factionId);
      setSaved(res.regions ?? []);
      setRows(rowsOf(res.regions ?? []));
    } catch (e) {
      setError(apiErrorMessage(e, 'Не удалось загрузить края, где фракция вне закона'));
    }
  }, [factionId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    let cancelled = false;
    fetchWorldGraph()
      .then((g) => {
        if (cancelled) return;
        const countries = new Map(g.countries.map((c) => [c.id, c.name]));
        setRegions(
          g.regions
            .map((r) => ({ id: r.id, name: `${r.name} (${countries.get(r.country_id) ?? 'без страны'})` }))
            .sort((a, b) => a.name.localeCompare(b.name, 'ru')),
        );
      })
      .catch((e) => !cancelled && toast.error(apiErrorMessage(e, 'Не удалось загрузить список краёв')));
    fetchLawSettings()
      .then((d) => {
        if (cancelled || !d.levels?.length) return;
        setLevels(d.levels.map((l) => ({ code: l.code, name: l.name, min_value: l.min_value })));
      })
      .catch((e) => !cancelled && toast.error(apiErrorMessage(e, 'Не удалось загрузить уровни розыска — показаны коды')));
    return () => {
      cancelled = true;
    };
  }, []);

  const regionName = useMemo(() => {
    const m = new Map(regions.map((r) => [r.id, r.name]));
    (saved ?? []).forEach((r) => !m.has(r.region_id) && m.set(r.region_id, r.region_name ?? `#${r.region_id}`));
    return m;
  }, [regions, saved]);

  const update = (key: number, patch: Partial<Row>) => setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  const save = async () => {
    const body: { region_id: number; level_code: string }[] = [];
    const seen = new Set<number>();
    for (const r of rows) {
      if (r.region_id == null) return void toast.error('Выберите край в каждой строке');
      if (!r.level_code) return void toast.error('Выберите тяжесть в каждой строке');
      if (seen.has(r.region_id)) return void toast.error('Один край указан дважды');
      seen.add(r.region_id);
      body.push({ region_id: r.region_id, level_code: r.level_code });
    }
    if (body.length > FACTION_OUTLAW_REGIONS_MAX) return void toast.error(`Краёв — не больше ${FACTION_OUTLAW_REGIONS_MAX}`);
    setSaving(true);
    try {
      const res = await adminPutFactionOutlawRegions(factionId, body);
      setSaved(res.regions ?? []);
      setRows(rowsOf(res.regions ?? []));
      toast.success('Края, где фракция вне закона, сохранены');
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить края'));
    } finally {
      setSaving(false);
    }
  };

  if (error && !saved) {
    return (
      <section className={SECTION}>
        <h3 className={H3}>Вне закона</h3>
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-site-red text-sm">{error}</p>
          <button type="button" className="btn-line !w-auto !text-xs !py-1 !px-3" onClick={() => void load()}>
            Повторить
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className={SECTION}>
      <h3 className={H3}>Вне закона</h3>
      <p className="text-white/40 text-xs">
        В этих краях членство — правонарушение «Членство в запрещённой фракции»: розыск поднимается не ниже выбранной
        тяжести, стража реагирует как на розыск. Не чаще срока из настроек на край.
        {isSecret
          ? ' Фракция тайная: участника раскрывает только успешная проверка стражи (как обнаружение скрытности).'
          : ' Открытых участников стража узнаёт без броска.'}{' '}
        Игроки видят предупреждение в каталоге и в профиле.
      </p>
      {!saved ? (
        <div className="w-6 h-6 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
      ) : (
        <>
          <div className="flex flex-col gap-2">
            <span className={LABEL}>
              Края ({rows.length}/{FACTION_OUTLAW_REGIONS_MAX})
            </span>
            {rows.length === 0 && <p className="text-white/50 text-sm">Фракция нигде не запрещена.</p>}
            {rows.map((r) => (
              <div key={r.key} className="flex flex-col sm:flex-row sm:items-center gap-2 bg-white/[0.03] rounded-card p-2.5 min-w-0">
                <select
                  value={r.region_id ?? ''}
                  disabled={ro}
                  onChange={(e) => update(r.key, { region_id: e.target.value ? Number(e.target.value) : null })}
                  className={`${FIELD} sm:flex-1 min-w-0`}
                  aria-label="Край"
                >
                  <option value="" className={OPTION}>
                    — Край —
                  </option>
                  {regions.map((g) => (
                    <option key={g.id} value={g.id} className={OPTION}>
                      {g.name}
                    </option>
                  ))}
                  {r.region_id != null && !regions.some((g) => g.id === r.region_id) && (
                    <option value={r.region_id} className={OPTION}>
                      {regionName.get(r.region_id) ?? `#${r.region_id}`}
                    </option>
                  )}
                </select>
                <select
                  value={r.level_code}
                  disabled={ro}
                  onChange={(e) => update(r.key, { level_code: e.target.value })}
                  className={`${FIELD} sm:!w-56 shrink-0`}
                  aria-label="Тяжесть"
                >
                  <option value="" className={OPTION}>
                    — Тяжесть —
                  </option>
                  {levels.map((l) => (
                    <option key={l.code} value={l.code} className={OPTION}>
                      {l.name}
                      {l.min_value != null ? ` (розыск от ${l.min_value})` : ''}
                    </option>
                  ))}
                </select>
                {!ro && (
                  <button
                    type="button"
                    onClick={() => setRows((prev) => prev.filter((x) => x.key !== r.key))}
                    className="text-site-red hover:text-white transition-colors p-1 self-end sm:self-center"
                    aria-label="Убрать край"
                  >
                    <X size={16} />
                  </button>
                )}
              </div>
            ))}
            {!ro && rows.length < FACTION_OUTLAW_REGIONS_MAX && (
              <button
                type="button"
                onClick={() => setRows((prev) => [...prev, { key: ++rowKey, region_id: null, level_code: levels[0]?.code ?? '' }])}
                className="text-sm text-site-blue hover:text-white transition-colors self-start"
              >
                + Добавить край
              </button>
            )}
          </div>
          {canEdit && (
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving}
              className="btn-blue !w-full sm:!w-auto !text-sm !px-6 self-start disabled:opacity-50"
            >
              {saving ? 'Сохранение...' : 'Сохранить края'}
            </button>
          )}
        </>
      )}
    </section>
  );
};

export default OutlawRegionsEditor;
