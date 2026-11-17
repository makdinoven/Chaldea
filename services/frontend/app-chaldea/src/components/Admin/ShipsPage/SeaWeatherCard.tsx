import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { RefreshCw } from 'lucide-react';
import {
  createSeaStorm,
  endSeaStorm,
  fetchSeaWeather,
  putSeaStormSea,
  seaAdminError,
  seaRangeText,
  SEA_LIMITS,
} from '../../../api/seaAdmin';
import type { SeaStormAdmin, SeaStormSea, SeaWeather, SeaZone } from '../../../types/seaAdmin';
import { battlePath } from '../../../utils/battlePath';
import { formatServerDateTime } from '../../../utils/serverDate';
import ConfirmDialog from '../../pages/LocationPage/ConfirmDialog';
import { FIELD, LABEL } from '../../pages/EpisodesPage/EpisodeFormModal';

const SEASON_LABEL: Record<string, string> = { spring: 'Весна', summer: 'Лето', autumn: 'Осень', winter: 'Зима' };

const RAID_STATUS: Record<string, { label: string; className: string }> = {
  starting: { label: 'Начинается', className: 'text-gold-light' },
  fighting: { label: 'Идёт бой', className: 'text-site-red' },
  won: { label: 'Отбились', className: 'text-stat-energy' },
  lost: { label: 'Проиграли', className: 'text-site-red' },
  aborted: { label: 'Сорвался', className: 'text-white/50' },
  expired: { label: 'Истёк', className: 'text-white/50' },
};

const ACTIVE_RAID = new Set(['starting', 'fighting']);

const TIME_OPTS: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' };

const DEFAULT_STORM_MINUTES = 60;

const CARD = 'bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] p-4 sm:p-5 flex flex-col gap-4 min-w-0';
const H2 = 'gold-text text-lg font-medium uppercase tracking-[0.06em]';
const SPINNER = 'w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin';

type SeaDraft = { is_enabled: boolean; chance: string; radius: string };

const draftOf = (s: SeaStormSea): SeaDraft => ({
  is_enabled: s.is_enabled,
  chance: String(s.chance_per_hour_pct),
  radius: String(s.radius),
});

const inRange = (raw: string, [min, max]: readonly [number, number], integer: boolean): boolean => {
  const value = Number(raw.trim());
  return raw.trim() !== '' && !Number.isNaN(value) && value >= min && value <= max && (!integer || Number.isInteger(value));
};

interface SeaRowProps {
  sea: SeaStormSea;
  canUpdate: boolean;
  onSaved: (sea: SeaStormSea) => void;
}

/** One sea: storms on/off, chance per real hour, radius in zones — saved per row. */
const SeaRow = ({ sea, canUpdate, onSaved }: SeaRowProps) => {
  const [draft, setDraft] = useState<SeaDraft>(() => draftOf(sea));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setDraft(draftOf(sea)), [sea]);

  const dirty =
    draft.is_enabled !== sea.is_enabled ||
    draft.chance.trim() !== String(sea.chance_per_hour_pct) ||
    draft.radius.trim() !== String(sea.radius);

  const save = async () => {
    if (!inRange(draft.chance, SEA_LIMITS.chance_per_hour_pct, false)) {
      setError(`Неверное значение: ${seaRangeText('chance_per_hour_pct')}`);
      return;
    }
    if (!inRange(draft.radius, SEA_LIMITS.radius, true)) {
      setError(`Неверное значение: ${seaRangeText('radius')}`);
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const saved = await putSeaStormSea(sea.region_id, {
        is_enabled: draft.is_enabled,
        chance_per_hour_pct: Number(draft.chance),
        radius: Number(draft.radius),
      });
      onSaved(saved);
      toast.success(`Море «${saved.name ?? `#${saved.region_id}`}» сохранено`);
    } catch (e) {
      const message = seaAdminError(e, 'Не удалось сохранить настройки моря');
      setError(message);
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <li className="flex flex-col gap-2 rounded-card border border-white/[0.07] bg-white/[0.03] p-3 min-w-0">
      <div className="grid grid-cols-1 sm:grid-cols-[minmax(0,1.4fr)_auto_minmax(0,1fr)_minmax(0,1fr)_auto] gap-3 sm:items-end">
        <div className="flex flex-col min-w-0">
          <span className="text-white/85 text-sm break-words">{sea.name ?? `Море #${sea.region_id}`}</span>
          <span className="text-white/40 text-xs">Морских зон: {sea.zones_count}</span>
        </div>
        <label className="flex items-center gap-2 text-sm text-white/80 cursor-pointer select-none sm:pb-2">
          <input
            type="checkbox"
            checked={draft.is_enabled}
            disabled={!canUpdate}
            onChange={(e) => setDraft((d) => ({ ...d, is_enabled: e.target.checked }))}
            className="w-4 h-4 accent-gold"
          />
          Шторма
        </label>
        <label className="flex flex-col gap-1 min-w-0">
          <span className={LABEL}>Шанс в час, %</span>
          <input
            type="number"
            inputMode="decimal"
            min={SEA_LIMITS.chance_per_hour_pct[0]}
            max={SEA_LIMITS.chance_per_hour_pct[1]}
            step={0.01}
            value={draft.chance}
            disabled={!canUpdate}
            onChange={(e) => setDraft((d) => ({ ...d, chance: e.target.value }))}
            className={FIELD}
          />
        </label>
        <label className="flex flex-col gap-1 min-w-0">
          <span className={LABEL}>Радиус, зон</span>
          <input
            type="number"
            inputMode="numeric"
            min={SEA_LIMITS.radius[0]}
            max={SEA_LIMITS.radius[1]}
            step={1}
            value={draft.radius}
            disabled={!canUpdate}
            onChange={(e) => setDraft((d) => ({ ...d, radius: e.target.value }))}
            className={FIELD}
          />
        </label>
        {canUpdate && (
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving || !dirty}
            className="btn-blue !w-full sm:!w-auto !px-4"
          >
            {saving ? 'Сохранение…' : 'Сохранить'}
          </button>
        )}
      </div>
      {error && <p className="text-site-red text-xs">{error}</p>}
    </li>
  );
};

interface SeaWeatherCardProps {
  canUpdate: boolean;
  /** L8 sea zones — the centre of a manual storm. */
  zones: SeaZone[];
  /** ship id → deck location id (the battle link of a raid). */
  deckByShip: Map<number, number>;
}

/**
 * FEAT-214 admin «Погода»: season and its storm multiplier, per-sea storm settings, active storms (end now),
 * a manual storm and the recent sea-monster raids.
 */
const SeaWeatherCard = ({ canUpdate, zones, deckByShip }: SeaWeatherCardProps) => {
  const [weather, setWeather] = useState<SeaWeather | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [ending, setEnding] = useState<SeaStormAdmin | null>(null);
  const [busyStormId, setBusyStormId] = useState<number | null>(null);
  const [zoneId, setZoneId] = useState('');
  const [minutes, setMinutes] = useState(String(DEFAULT_STORM_MINUTES));
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setWeather(await fetchSeaWeather());
      setLoadError(null);
    } catch (e) {
      const message = seaAdminError(e, 'Не удалось загрузить погоду на море');
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const zoneGroups = useMemo(() => {
    const groups = new Map<string, SeaZone[]>();
    [...zones]
      .sort((a, b) => a.name.localeCompare(b.name, 'ru'))
      .forEach((z) => {
        const key = z.region_name ?? 'Без моря';
        groups.set(key, [...(groups.get(key) ?? []), z]);
      });
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b, 'ru'));
  }, [zones]);

  const onSeaSaved = (saved: SeaStormSea) =>
    setWeather((prev) =>
      prev ? { ...prev, seas: prev.seas.map((s) => (s.region_id === saved.region_id ? saved : s)) } : prev,
    );

  const startStorm = async () => {
    const id = Number(zoneId);
    if (!zoneId || !Number.isInteger(id) || id < 1) {
      setCreateError('Выберите морскую зону — центр шторма');
      return;
    }
    if (!inRange(minutes, SEA_LIMITS.minutes, true)) {
      setCreateError(`Неверное значение: ${seaRangeText('minutes')}`);
      return;
    }
    setCreateError(null);
    setCreating(true);
    try {
      const storm = await createSeaStorm({ zone_id: id, minutes: Number(minutes) });
      toast.success(`Шторм вызван в «${storm.center_zone.name ?? `#${storm.center_zone.id}`}»`);
      await load();
    } catch (e) {
      const message = seaAdminError(e, 'Не удалось вызвать шторм');
      setCreateError(message);
      toast.error(message);
    } finally {
      setCreating(false);
    }
  };

  const stopStorm = async (storm: SeaStormAdmin) => {
    setEnding(null);
    setBusyStormId(storm.id);
    try {
      await endSeaStorm(storm.id);
      toast.success('Шторм завершён');
      setWeather((prev) => (prev ? { ...prev, storms: prev.storms.filter((s) => s.id !== storm.id) } : prev));
    } catch (e) {
      toast.error(seaAdminError(e, 'Не удалось завершить шторм'));
      void load();
    } finally {
      setBusyStormId(null);
    }
  };

  if (!weather) {
    return loadError ? (
      <div className="flex flex-col sm:flex-row sm:items-center gap-2">
        <p className="text-site-red text-sm flex-1">{loadError}</p>
        <button type="button" className="btn-line !w-full sm:!w-auto" onClick={() => void load()} disabled={loading}>
          Повторить
        </button>
      </div>
    ) : (
      <div className={SPINNER} />
    );
  }

  const season = weather.season ? SEASON_LABEL[weather.season] ?? weather.season : null;

  return (
    <div className="flex flex-col gap-5 min-w-0">
      {/* Season */}
      <section className={CARD}>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex flex-col gap-1 min-w-0">
            <h2 className={H2}>Погода на море</h2>
            <p className="text-white/70 text-sm">
              {season ? (
                <>
                  Сезон: <span className="text-gold">{season}</span> · шанс штормов ×
                  <span className="text-gold">{weather.season_mult.toLocaleString('ru-RU')}</span>
                </>
              ) : (
                <>
                  Игрового календаря нет · шанс штормов ×
                  <span className="text-gold">{weather.season_mult.toLocaleString('ru-RU')}</span>
                </>
              )}
            </p>
            <p className="text-white/40 text-xs">
              Множители сезонов и длительность штормов — на вкладке «Настройки моря». В одном море одновременно
              бывает не больше одного случайного шторма.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="btn-line !w-full sm:!w-auto flex items-center justify-center gap-2 shrink-0"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Обновить
          </button>
        </div>
        {loadError && <p className="text-site-red text-sm">{loadError}</p>}
      </section>

      {/* Seas */}
      <section className={CARD}>
        <h2 className={H2}>Моря</h2>
        {weather.seas.length === 0 ? (
          <p className="text-white/40 text-sm italic">
            Морей нет — отметьте локации как морские зоны в редакторе локаций.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {weather.seas.map((s) => (
              <SeaRow key={s.region_id} sea={s} canUpdate={canUpdate} onSaved={onSeaSaved} />
            ))}
          </ul>
        )}
      </section>

      {/* Storms */}
      <section className={CARD}>
        <h2 className={H2}>Шторма сейчас</h2>
        {weather.storms.length === 0 ? (
          <p className="text-white/40 text-sm italic">Штормов нет — море спокойно.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {weather.storms.map((st) => (
              <li
                key={st.id}
                className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 rounded-card border border-white/[0.07] bg-white/[0.03] p-3 min-w-0"
              >
                <div className="flex flex-col gap-0.5 min-w-0 flex-1 text-sm">
                  <span className="text-white/85 break-words">
                    <span aria-hidden>⛈️ </span>
                    {st.center_zone.name ?? `#${st.center_zone.id}`}
                    {st.sea_name ? <span className="text-white/50">, {st.sea_name}</span> : null}
                  </span>
                  <span className="text-white/50 text-xs break-words">
                    Зоны: {st.zones.map((z) => z.name ?? `#${z.id}`).join(', ') || '—'}
                  </span>
                  <span className="text-white/40 text-xs">
                    до {formatServerDateTime(st.ends_at, TIME_OPTS)} · смещений {st.moves} ·{' '}
                    {st.source === 'admin' ? 'вызван вручную' : 'случайный'}
                  </span>
                </div>
                {canUpdate && (
                  <button
                    type="button"
                    onClick={() => setEnding(st)}
                    disabled={busyStormId === st.id}
                    className="btn-line !w-full sm:!w-auto shrink-0"
                  >
                    {busyStormId === st.id ? 'Завершение…' : 'Завершить'}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}

        {canUpdate && (
          <div className="flex flex-col gap-3 border-t border-white/[0.07] pt-4">
            <h3 className="text-white/70 text-sm uppercase tracking-[0.06em]">Вызвать шторм</h3>
            {zones.length === 0 ? (
              <p className="text-white/40 text-sm italic">Морских зон нет.</p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto] gap-3 sm:items-end">
                <label className="flex flex-col gap-1 min-w-0">
                  <span className={LABEL}>Центр шторма</span>
                  <select value={zoneId} onChange={(e) => setZoneId(e.target.value)} className={FIELD}>
                    <option value="">— морская зона —</option>
                    {zoneGroups.map(([sea, list]) => (
                      <optgroup key={sea} label={sea}>
                        {list.map((z) => (
                          <option key={z.id} value={z.id}>
                            {z.name}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 min-w-0">
                  <span className={LABEL}>Длительность, мин</span>
                  <input
                    type="number"
                    inputMode="numeric"
                    min={SEA_LIMITS.minutes[0]}
                    max={SEA_LIMITS.minutes[1]}
                    step={1}
                    value={minutes}
                    onChange={(e) => setMinutes(e.target.value)}
                    className={FIELD}
                  />
                </label>
                <button
                  type="button"
                  onClick={() => void startStorm()}
                  disabled={creating}
                  className="btn-blue !w-full sm:!w-auto !px-4"
                >
                  {creating ? 'Вызываем…' : 'Вызвать'}
                </button>
              </div>
            )}
            <p className="text-white/40 text-xs">
              Шторм накроет выбранную зону и соседние в пределах радиуса её моря ({SEA_LIMITS.minutes[0]}–
              {SEA_LIMITS.minutes[1].toLocaleString('ru-RU')} мин).
            </p>
            {createError && <p className="text-site-red text-sm">{createError}</p>}
          </div>
        )}
      </section>

      {/* Raids */}
      <section className={CARD}>
        <h2 className={H2}>Нападения монстров</h2>
        {weather.raids.length === 0 ? (
          <p className="text-white/40 text-sm italic">Нападений пока не было.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {weather.raids.map((r) => {
              const status = RAID_STATUS[r.status] ?? { label: r.status, className: 'text-white/60' };
              const deck = deckByShip.get(r.ship_id);
              const link = r.battle_id != null && deck != null ? `${battlePath(deck, r.battle_id)}/spectate` : null;
              return (
                <li
                  key={r.id}
                  className={`flex flex-col gap-1 rounded-card border p-3 min-w-0 text-sm ${
                    ACTIVE_RAID.has(r.status) ? 'border-site-red/40 bg-site-red/[0.05]' : 'border-white/[0.07] bg-white/[0.03]'
                  }`}
                >
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 min-w-0">
                    <span className="text-white/85 break-words">
                      {r.ship_name ? `«${r.ship_name}»` : `Корабль #${r.ship_id} (удалён)`}
                    </span>
                    <span className={`text-xs ${status.className}`}>{status.label}</span>
                    <span className="text-white/40 text-xs">{formatServerDateTime(r.created_at, TIME_OPTS)}</span>
                  </div>
                  <span className="text-white/60 text-xs break-words">
                    {r.monster_name ?? 'Монстр'} · {r.zone.name ?? `зона #${r.zone.id}`}
                  </span>
                  <span className="text-white/50 text-xs break-words">
                    Игроки: {r.players.length ? r.players.map((p) => p.name ?? `#${p.id}`).join(', ') : '—'}
                  </span>
                  {r.battle_id != null &&
                    (link ? (
                      <Link to={link} className="site-link text-xs self-start">
                        Бой #{r.battle_id}
                      </Link>
                    ) : (
                      <span className="text-white/40 text-xs">Бой #{r.battle_id}</span>
                    ))}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {ending && (
        <ConfirmDialog
          title="Завершить шторм"
          message={`Шторм в «${ending.center_zone.name ?? `#${ending.center_zone.id}`}» закончится сейчас же.`}
          confirmLabel="Завершить"
          danger
          onCancel={() => setEnding(null)}
          onConfirm={() => void stopStorm(ending)}
        />
      )}
    </div>
  );
};

export default SeaWeatherCard;
