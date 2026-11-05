import { useCallback, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { apiErrorMessage } from '../../api/errors';
import {
  fetchGuardPatrol,
  saveGuardPatrol,
  stepGuardPatrol,
  PATROL_DEFAULT_INTERVAL,
  PATROL_DEFAULT_JITTER,
  PATROL_INTERVAL_MAX,
  PATROL_INTERVAL_MIN,
  PATROL_JITTER_MAX,
  PATROL_JITTER_MIN,
  PATROL_ROUTE_MAX_POINTS,
  PATROL_ROUTE_MIN_POINTS,
  PATROL_ZONE_MAX_LOCATIONS,
  PATROL_ZONE_MIN_LOCATIONS,
  type PatrolBlockedReason,
  type PatrolIn,
  type PatrolMode,
  type PatrolOut,
  type PatrolRouteStyle,
  type PatrolStepOut,
  type PatrolZoneKind,
} from '../../api/guardPatrol';
import { EntityListPicker, EntityPicker, SearchBox } from '../Admin/DungeonsPage/editor/pickers';
import RemainingText from '../CommonComponents/RemainingText';
import { formatServerDateTime } from '../../utils/serverDate';

/*
  FEAT-204 — «Патруль» of a guard NPC: a fixed post, an ordered route
  (loop / ping-pong) or a zone (a district or a set of locations) walked at
  random. Own GET / PUT and a «Шаг сейчас» for checking without waiting.
*/

interface GuardPatrolPanelProps {
  npcId: number;
}

interface RoutePoint {
  id: number;
  name: string | null;
}

interface PatrolForm {
  mode: PatrolMode;
  routeStyle: PatrolRouteStyle;
  route: RoutePoint[];
  zoneKind: PatrolZoneKind;
  zoneDistrictId: number | null;
  zoneLocationIds: number[];
  interval: string;
  jitter: string;
}

const MODE_OPTIONS: { value: PatrolMode; label: string }[] = [
  { value: 'post', label: 'Пост' },
  { value: 'route', label: 'Маршрут' },
  { value: 'zone', label: 'Зона' },
];

const STYLE_OPTIONS: { value: PatrolRouteStyle; label: string }[] = [
  { value: 'loop', label: 'По кругу' },
  { value: 'pingpong', label: 'Туда-обратно' },
];

const ZONE_KIND_OPTIONS: { value: PatrolZoneKind; label: string }[] = [
  { value: 'district', label: 'Район' },
  { value: 'locations', label: 'Набор локаций' },
];

const BLOCKED_LABELS: Record<PatrolBlockedReason, string> = {
  not_guard: 'НПС больше не стражник',
  dead: 'стражник мёртв',
  ko: 'стражник выбит',
  battle: 'стражник в бою',
  encounter: 'стражник задерживает нарушителя',
};

const blockedText = (reason: string | null | undefined): string =>
  reason ? BLOCKED_LABELS[reason as PatrolBlockedReason] ?? reason : '';

const formFrom = (p: PatrolOut): PatrolForm => ({
  mode: p.mode,
  routeStyle: p.route_style,
  route: p.route.map((pt) => ({ id: pt.location_id, name: pt.name })),
  zoneKind: p.zone_kind,
  zoneDistrictId: p.zone_district_id,
  zoneLocationIds: p.zone_locations.map((pt) => pt.location_id),
  interval: String(p.interval_min ?? PATROL_DEFAULT_INTERVAL),
  jitter: String(p.jitter_pct ?? PATROL_DEFAULT_JITTER),
});

const bodyFrom = (f: PatrolForm): PatrolIn => ({
  mode: f.mode,
  route_style: f.routeStyle,
  route_location_ids: f.route.map((pt) => pt.id),
  zone_kind: f.zoneKind,
  zone_district_id: f.zoneDistrictId,
  zone_location_ids: f.zoneLocationIds,
  interval_min: Number(f.interval),
  jitter_pct: Number(f.jitter),
});

/** Client-side mirror of `patrol_core.validate` (the server re-checks everything). */
const validate = (f: PatrolForm): string | null => {
  const interval = Number(f.interval);
  const jitter = Number(f.jitter);
  if (!Number.isInteger(interval) || interval < PATROL_INTERVAL_MIN || interval > PATROL_INTERVAL_MAX) {
    return `Интервал патруля: от ${PATROL_INTERVAL_MIN} до ${PATROL_INTERVAL_MAX} минут`;
  }
  if (!Number.isInteger(jitter) || jitter < PATROL_JITTER_MIN || jitter > PATROL_JITTER_MAX) {
    return `Разброс интервала: от ${PATROL_JITTER_MIN} до ${PATROL_JITTER_MAX} %`;
  }
  if (f.route.length > PATROL_ROUTE_MAX_POINTS) return `В маршруте не больше ${PATROL_ROUTE_MAX_POINTS} точек`;
  if (f.zoneLocationIds.length > PATROL_ZONE_MAX_LOCATIONS) {
    return `В зоне патруля не больше ${PATROL_ZONE_MAX_LOCATIONS} локаций`;
  }
  if (f.mode === 'route') {
    if (f.route.length < PATROL_ROUTE_MIN_POINTS) return `В маршруте нужно хотя бы ${PATROL_ROUTE_MIN_POINTS} точки`;
    if (f.route.some((pt, i) => i > 0 && f.route[i - 1].id === pt.id)) {
      return 'Одна и та же локация не может идти в маршруте два раза подряд';
    }
  }
  if (f.mode === 'zone') {
    if (f.zoneKind === 'district' && !f.zoneDistrictId) return 'Выберите район зоны патруля';
    if (f.zoneKind === 'locations') {
      if (f.zoneLocationIds.length < PATROL_ZONE_MIN_LOCATIONS) {
        return `В зоне патруля нужно хотя бы ${PATROL_ZONE_MIN_LOCATIONS} локации`;
      }
      if (new Set(f.zoneLocationIds).size !== f.zoneLocationIds.length) {
        return 'Локации в зоне патруля не должны повторяться';
      }
    }
  }
  return null;
};

const sameForm = (a: PatrolForm, b: PatrolForm) => JSON.stringify(bodyFrom(a)) === JSON.stringify(bodyFrom(b));

const intervalHint = (interval: string, jitter: string): string | null => {
  const i = Number(interval);
  const j = Number(jitter);
  if (!Number.isFinite(i) || !Number.isFinite(j) || i <= 0 || j < 0) return null;
  const lo = Math.max(1, Math.round(i * (1 - j / 100)));
  const hi = Math.round(i * (1 + j / 100));
  return j === 0 ? `ровно ${i} мин` : `${i} мин ± ${j} % = ${lo}–${hi} мин`;
};

const stepText = (r: PatrolStepOut, name: (id: number | null) => string): string => {
  switch (r.outcome) {
    case 'moved': {
      const sweep = r.checked > 0
        ? `; проверено: ${r.checked}, задержано: ${r.encounters}, проскользнули: ${r.slipped}`
        : '; разыскиваемых там нет';
      return `Стражник перешёл: ${name(r.from_location_id)} → ${name(r.to_location_id)}${sweep}`;
    }
    case 'stayed':
      return 'Стражник остался на месте — идти некуда';
    case 'blocked':
      return `Стражник не может идти: ${blockedText(r.blocked_reason) || 'занят'}`;
    case 'not_patrolling':
      return 'Стражник не патрулирует (пост или патрули выключены)';
    default:
      return r.outcome;
  }
};

const Segmented = <T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) => (
  <div className="flex flex-wrap gap-2">
    {options.map((o) => (
      <button
        key={o.value}
        type="button"
        onClick={() => onChange(o.value)}
        className={`chip-outline rounded-full px-4 py-1.5 text-xs font-medium ${value === o.value ? 'chip-outline-active' : ''}`}
      >
        {o.label}
      </button>
    ))}
  </div>
);

const GuardPatrolPanel = ({ npcId }: GuardPatrolPanelProps) => {
  const [patrol, setPatrol] = useState<PatrolOut | null>(null);
  const [form, setForm] = useState<PatrolForm | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [stepping, setStepping] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [stepResult, setStepResult] = useState<string | null>(null);

  const apply = useCallback((p: PatrolOut) => {
    setPatrol(p);
    setForm(formFrom(p));
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    fetchGuardPatrol(npcId)
      .then(apply)
      .catch((err) => setLoadError(apiErrorMessage(err, 'Не удалось загрузить патруль стражника')))
      .finally(() => setLoading(false));
  }, [npcId, apply]);

  useEffect(() => {
    setStepResult(null);
    setFormError(null);
    load();
  }, [load]);

  const dirty = useMemo(() => !!(patrol && form && !sameForm(form, formFrom(patrol))), [patrol, form]);

  const update = (patch: Partial<PatrolForm>) => {
    setForm((f) => (f ? { ...f, ...patch } : f));
    setFormError(null);
  };

  const moveRoutePoint = (idx: number, delta: number) => {
    if (!form) return;
    const target = idx + delta;
    if (target < 0 || target >= form.route.length) return;
    const route = [...form.route];
    [route[idx], route[target]] = [route[target], route[idx]];
    update({ route });
  };

  const handleSave = async () => {
    if (!form) return;
    const problem = validate(form);
    if (problem) {
      setFormError(problem);
      return;
    }
    setSaving(true);
    try {
      const saved = await saveGuardPatrol(npcId, bodyFrom(form));
      apply(saved);
      setStepResult(null);
      toast.success('Патруль сохранён');
    } catch (err) {
      const message = apiErrorMessage(err, 'Не удалось сохранить патруль стражника');
      setFormError(message);
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const handleStep = async () => {
    setStepping(true);
    try {
      const r = await stepGuardPatrol(npcId);
      // Names of the from / to points: the route / zone lists of the fresh patrol, or the current location.
      const names = new Map<number, string>();
      // The from-point is where the guard stood before the step (a district zone lists no names of its own).
      if (patrol?.current_location_id && patrol.current_location_name) {
        names.set(patrol.current_location_id, patrol.current_location_name);
      }
      [...r.patrol.route, ...r.patrol.zone_locations].forEach((pt) => pt.name && names.set(pt.location_id, pt.name));
      if (r.patrol.current_location_id && r.patrol.current_location_name) {
        names.set(r.patrol.current_location_id, r.patrol.current_location_name);
      }
      const name = (id: number | null) => (id ? names.get(id) ?? `#${id}` : '—');
      setStepResult(stepText(r, name));
      // Keep unsaved edits; refresh only the status part.
      setPatrol(r.patrol);
      if (!dirty) setForm(formFrom(r.patrol));
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Не удалось выполнить шаг патруля'));
    } finally {
      setStepping(false);
    }
  };

  if (loading && !patrol) {
    return (
      <div className="gray-bg p-4 sm:p-6 flex items-center justify-center">
        <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

  if (loadError || !patrol || !form) {
    return (
      <div className="gray-bg p-4 sm:p-6 flex flex-col gap-3">
        <h3 className="gold-text text-xl font-semibold uppercase tracking-[0.06em]">Патруль</h3>
        <p className="text-site-red text-sm">{loadError ?? 'Не удалось загрузить патруль стражника'}</p>
        <button type="button" onClick={load} className="btn-line !w-auto !px-6 self-start">
          Повторить
        </button>
      </div>
    );
  }

  const moving = patrol.mode !== 'post';
  const hint = intervalHint(form.interval, form.jitter);

  return (
    <div className="gray-bg p-4 sm:p-6 flex flex-col gap-5 min-w-0">
      <div className="flex flex-col gap-1">
        <h3 className="gold-text text-xl font-semibold uppercase tracking-[0.06em]">Патруль</h3>
        <p className="text-white/50 text-xs">
          Пост — стражник стоит на месте. Маршрут — обходит локации по порядку. Зона — бродит по соседним
          локациям внутри района или выбранного набора.
        </p>
      </div>

      {/* Status */}
      <div className="flex flex-col gap-1.5 border border-white/10 rounded-md p-3 sm:p-4 text-sm min-w-0">
        {!patrol.patrols_enabled && (
          <p className="text-site-red text-xs">
            Патрули стражи выключены в настройках закона — стражник никуда не пойдёт.
          </p>
        )}
        <p className="text-white/80 break-words">
          <span className="text-white/50">Сейчас: </span>
          {patrol.current_location_name ?? (patrol.current_location_id ? `#${patrol.current_location_id}` : 'нигде')}
        </p>
        {moving && (
          <p className="text-white/80 break-words">
            <span className="text-white/50">Следующий шаг: </span>
            {patrol.next_move_at ? (
              <>
                <RemainingText until={patrol.next_move_at} prefix="через" doneText="вот-вот" />
                <span className="text-white/40"> ({formatServerDateTime(patrol.next_move_at)})</span>
              </>
            ) : (
              'не назначен'
            )}
          </p>
        )}
        {patrol.last_moved_at && (
          <p className="text-white/60 text-xs">Последний переход: {formatServerDateTime(patrol.last_moved_at)}</p>
        )}
        {patrol.blocked_reason && (
          <p className="text-site-red text-xs">Стоит: {blockedText(patrol.blocked_reason)}</p>
        )}
        {patrol.warnings.length > 0 && (
          <ul className="flex flex-col gap-1 mt-1">
            {patrol.warnings.map((w, i) => (
              <li key={i} className="text-gold text-xs break-words">
                ⚠ {w}
              </li>
            ))}
          </ul>
        )}
        {stepResult && <p className="text-white text-xs mt-1 break-words">{stepResult}</p>}
      </div>

      {/* Mode */}
      <div className="flex flex-col gap-2">
        <span className="text-white/50 text-xs">Режим</span>
        <Segmented options={MODE_OPTIONS} value={form.mode} onChange={(mode) => update({ mode })} />
      </div>

      {form.mode === 'route' && (
        <div className="flex flex-col gap-3 min-w-0">
          <div className="flex flex-col gap-2">
            <span className="text-white/50 text-xs">Порядок обхода</span>
            <Segmented
              options={STYLE_OPTIONS}
              value={form.routeStyle}
              onChange={(routeStyle) => update({ routeStyle })}
            />
          </div>
          <div className="flex flex-col gap-2 min-w-0">
            <span className="text-white/50 text-xs">
              Точки маршрута ({form.route.length}/{PATROL_ROUTE_MAX_POINTS})
            </span>
            {form.route.length === 0 && <p className="text-white/40 text-xs">Пока ни одной точки</p>}
            <ol className="flex flex-col gap-1.5 min-w-0">
              {form.route.map((pt, idx) => (
                <li
                  key={`${pt.id}-${idx}`}
                  className="flex items-center gap-2 min-w-0 rounded-md bg-white/5 px-2 py-1.5"
                >
                  <span className="text-white/40 text-xs w-5 shrink-0 text-right">{idx + 1}.</span>
                  <span className="flex-1 min-w-0 truncate text-sm text-white" title={pt.name ?? undefined}>
                    {pt.name ?? `#${pt.id}`}
                    <span className="text-white/40 text-xs ml-1">#{pt.id}</span>
                  </span>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      type="button"
                      onClick={() => moveRoutePoint(idx, -1)}
                      disabled={idx === 0}
                      className="w-8 h-8 sm:w-7 sm:h-7 rounded-md text-white/70 hover:text-gold hover:bg-white/10 disabled:opacity-30 disabled:hover:bg-transparent"
                      aria-label="Выше"
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      onClick={() => moveRoutePoint(idx, 1)}
                      disabled={idx === form.route.length - 1}
                      className="w-8 h-8 sm:w-7 sm:h-7 rounded-md text-white/70 hover:text-gold hover:bg-white/10 disabled:opacity-30 disabled:hover:bg-transparent"
                      aria-label="Ниже"
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      onClick={() => update({ route: form.route.filter((_, i) => i !== idx) })}
                      className="w-8 h-8 sm:w-7 sm:h-7 rounded-md text-white/70 hover:text-site-red hover:bg-white/10"
                      aria-label="Убрать"
                    >
                      ×
                    </button>
                  </div>
                </li>
              ))}
            </ol>
            {form.route.length < PATROL_ROUTE_MAX_POINTS && (
              <div className="max-w-md">
                <SearchBox
                  kind="location"
                  onPick={(o) => update({ route: [...form.route, { id: o.id, name: o.label }] })}
                />
              </div>
            )}
          </div>
        </div>
      )}

      {form.mode === 'zone' && (
        <div className="flex flex-col gap-3 min-w-0">
          <div className="flex flex-col gap-2">
            <span className="text-white/50 text-xs">Зона</span>
            <Segmented
              options={ZONE_KIND_OPTIONS}
              value={form.zoneKind}
              onChange={(zoneKind) => update({ zoneKind })}
            />
          </div>
          {form.zoneKind === 'district' ? (
            <div className="flex flex-col gap-1 max-w-md min-w-0">
              <span className="text-white/50 text-xs">Район (все его локации, включая вложенные)</span>
              <EntityPicker
                kind="district"
                value={form.zoneDistrictId}
                onChange={(zoneDistrictId) => update({ zoneDistrictId })}
              />
            </div>
          ) : (
            <div className="flex flex-col gap-1 min-w-0">
              <span className="text-white/50 text-xs">
                Локации зоны ({form.zoneLocationIds.length}/{PATROL_ZONE_MAX_LOCATIONS})
              </span>
              <EntityListPicker
                kind="location"
                ids={form.zoneLocationIds}
                onChange={(zoneLocationIds) => update({ zoneLocationIds })}
              />
            </div>
          )}
          <p className="text-white/40 text-xs">
            Стражник ходит только по переходам между соседними локациями внутри зоны.
          </p>
        </div>
      )}

      {form.mode !== 'post' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4 max-w-xl">
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs">Интервал, мин</span>
            <input
              type="number"
              inputMode="numeric"
              min={PATROL_INTERVAL_MIN}
              max={PATROL_INTERVAL_MAX}
              className="input-underline"
              value={form.interval}
              onChange={(e) => update({ interval: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs">Разброс, %</span>
            <input
              type="number"
              inputMode="numeric"
              min={PATROL_JITTER_MIN}
              max={PATROL_JITTER_MAX}
              className="input-underline"
              value={form.jitter}
              onChange={(e) => update({ jitter: e.target.value })}
            />
          </label>
          {hint && <p className="text-white/40 text-xs sm:col-span-2">Шаг раз в {hint}</p>}
        </div>
      )}

      {formError && <p className="text-site-red text-sm break-words">{formError}</p>}

      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving || !dirty}
          className="btn-blue !px-8 disabled:opacity-50"
        >
          {saving ? 'Сохранение...' : 'Сохранить патруль'}
        </button>
        <button
          type="button"
          onClick={handleStep}
          disabled={stepping || dirty || patrol.mode === 'post'}
          className="btn-line !w-auto !px-8 disabled:opacity-50"
          title={dirty ? 'Сначала сохраните патруль' : undefined}
        >
          {stepping ? 'Шаг...' : 'Шаг сейчас'}
        </button>
        {dirty && <span className="text-white/50 text-xs">Есть несохранённые изменения</span>}
      </div>
    </div>
  );
};

export default GuardPatrolPanel;
