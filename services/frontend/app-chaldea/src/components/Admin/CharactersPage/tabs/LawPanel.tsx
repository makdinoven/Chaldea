import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  fetchCharacterLawAdmin,
  postLawClearWanted,
  postLawRelease,
  LAW_REASON_MAX,
  LAW_REASON_MIN,
  type LawAdminCharacter,
  type LawCrime,
  type LawLogEntry,
} from '../../../../api/lawAdmin';
import { postRenownAdjust, RENOWN_ADJUST_MAX, type RenownScale } from '../../../../api/shadowAdmin';
import CrimeActionModal, { type CrimeAction, type CrimeActionTarget } from '../../ReputationPage/CrimeActionModal';
import {
  CRIME_STATUS_CLASSES,
  CRIME_TYPE_LABELS,
  RENOWN_SCALE_LABELS,
  RENOWN_SOURCE_LABELS,
  crimeStatusLabel,
  isOpenCrime,
  pct,
} from '../../ReputationPage/shadowLabels';
import { renownTierName, useRenownTierNames } from '../../ReputationPage/useShadowRefs';
import { newRequestId } from '../../../../api/reputationAdmin';
import { apiErrorMessage } from '../../../../api/errors';
import { formatServerDateTime } from '../../../../utils/serverDate';
import RemainingText from '../../../CommonComponents/RemainingText';

interface LawPanelProps {
  characterId: number;
  canManage: boolean;
}

type StaffAction = 'release' | 'clear';

const LABEL = 'text-white/50 text-xs font-medium uppercase tracking-[0.06em]';
/** Region select value meaning «every region». */
const ALL_REGIONS = 'all';

const SIGNED_INT_RE = /^-?\d*$/;

const ENCOUNTER_STATUS_LABELS: Record<string, string> = {
  pending: 'ждёт ответа',
  fighting: 'идёт бой',
  fined: 'штраф уплачен',
  jailed: 'сдался',
  fled: 'сбежал',
  won: 'стража побеждена',
  auto_fined: 'автоштраф',
  cancelled: 'отменено',
  guard_gone: 'стражник ушёл',
};

const CHOICE_LABELS: Record<string, string> = {
  fine: 'штраф',
  surrender: 'сдаться',
  flee: 'бежать',
  fight: 'драться',
};

const SOURCE_LABELS: Record<string, string> = {
  move: 'переход',
  quick_move: 'быстрый переход',
  teleport: 'телепорт',
};

const LOG_LABELS: Record<string, string> = {
  crime: 'Преступление',
  encounter: 'Встреча со стражей',
  fine: 'Штраф',
  surrender: 'Сдался страже',
  jail: 'Заключение',
  flee_ok: 'Удачное бегство',
  flee_fail: 'Бегство не удалось',
  fight: 'Бой со стражей',
  fight_won: 'Стража побеждена',
  fight_lost: 'Бой со стражей проигран',
  fight_aborted: 'Бой со стражей прерван',
  escape_ok: 'Удачный побег',
  escape_fail: 'Побег не удался',
  bail: 'Залог',
  served: 'Срок отбыт',
  auto_surrender: 'Автосдача (нет ответа)',
  auto_fine: 'Автоштраф (нет ответа)',
  staff_release: 'Освобождён властями',
  staff_clear: 'Розыск снят властями',
  staff_cancel: 'Встреча отменена властями',
  guard_ko: 'Стражник оглушён',
  guard_gone: 'Стражник ушёл',
  choice: 'Выбор',
  reveal: 'Преступление раскрыто',
  reveal_fail: 'Раскрытие не удалось',
  crime_closed: 'Дело закрыто (срок истёк)',
  staff_reveal: 'Раскрыто властями',
  staff_close: 'Дело закрыто властями',
};

const label = (map: Record<string, string>, code: string | null | undefined): string =>
  code ? map[code] ?? code : '—';

const wantedChange = (x: LawLogEntry): string | null => {
  if (x.wanted_before == null && x.wanted_after == null) return null;
  return `розыск ${x.wanted_before ?? '—'} → ${x.wanted_after ?? '—'}`;
};

const Info = ({ name, children }: { name: string; children: React.ReactNode }) => (
  <div className="flex flex-col gap-0.5 min-w-0">
    <span className={LABEL}>{name}</span>
    <span className="text-white text-sm break-words">{children}</span>
  </div>
);

/** Admin character card → «Репутация» → «Закон» (FEAT-198): wanted numbers, encounter / jail, crimes, log, staff actions. */
const LawPanel = ({ characterId, canManage }: LawPanelProps) => {
  const [data, setData] = useState<LawAdminCharacter | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [action, setAction] = useState<StaffAction>('clear');
  const [region, setRegion] = useState<string>(ALL_REGIONS);
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [crimeTarget, setCrimeTarget] = useState<CrimeActionTarget | null>(null);
  const [crimeAction, setCrimeAction] = useState<CrimeAction>('reveal');

  const tierNames = useRenownTierNames();
  const [renownScale, setRenownScale] = useState<RenownScale>('fame');
  const [renownDelta, setRenownDelta] = useState('');
  const [renownReason, setRenownReason] = useState('');
  const [renownSubmitting, setRenownSubmitting] = useState(false);
  const [renownError, setRenownError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    fetchCharacterLawAdmin(characterId)
      .then((d) => {
        setData(d);
        setLoadError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить данные о законе');
        setLoadError(msg);
        toast.error(msg);
      })
      .finally(() => setLoading(false));
  }, [characterId]);

  useEffect(load, [load]);

  const canRelease = Boolean(data?.jail || data?.encounter);

  // A region that no longer has wanted after a reload falls back to «all».
  useEffect(() => {
    if (region !== ALL_REGIONS && !data?.wanted.some((w) => String(w.region_id) === region)) setRegion(ALL_REGIONS);
  }, [data, region]);

  const submit = async () => {
    const r = reason.trim();
    if (action === 'release' && !canRelease) {
      setFormError('Персонаж не в тюрьме и не задержан стражей');
      return;
    }
    if (r.length < LAW_REASON_MIN) {
      setFormError(`Причина обязательна — не короче ${LAW_REASON_MIN} символов`);
      return;
    }
    if (r.length > LAW_REASON_MAX) {
      setFormError(`Причина — не длиннее ${LAW_REASON_MAX} символов`);
      return;
    }
    setFormError(null);
    setSubmitting(true);
    try {
      const requestId = newRequestId();
      const result =
        action === 'release'
          ? await postLawRelease(characterId, { reason: r, request_id: requestId })
          : await postLawClearWanted(characterId, {
              region_id: region === ALL_REGIONS ? null : Number(region),
              reason: r,
              request_id: requestId,
            });
      if (result.duplicate) toast(result.message);
      else toast.success(result.message);
      setReason('');
      load();
    } catch (e) {
      const msg = apiErrorMessage(
        e,
        action === 'release' ? 'Не удалось освободить персонажа' : 'Не удалось снять розыск',
      );
      setFormError(msg);
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const openCrimeAction = (c: LawCrime, a: CrimeAction) => {
    setCrimeAction(a);
    setCrimeTarget({
      id: c.id,
      title: `${label(CRIME_TYPE_LABELS, c.crime_type)} · ${c.region_name ?? `край #${c.region_id}`} · ${formatServerDateTime(c.created_at)}`,
    });
  };

  const submitRenown = async () => {
    const delta = Number(renownDelta);
    const r = renownReason.trim();
    if (renownDelta.trim() === '' || renownDelta === '-' || !Number.isInteger(delta) || delta === 0) {
      setRenownError('Изменение — целое число, не равное нулю');
      return;
    }
    if (Math.abs(delta) > RENOWN_ADJUST_MAX) {
      setRenownError(`Изменение — от −${RENOWN_ADJUST_MAX} до ${RENOWN_ADJUST_MAX}`);
      return;
    }
    if (r.length < LAW_REASON_MIN) {
      setRenownError(`Причина обязательна — не короче ${LAW_REASON_MIN} символов`);
      return;
    }
    if (r.length > LAW_REASON_MAX) {
      setRenownError(`Причина — не длиннее ${LAW_REASON_MAX} символов`);
      return;
    }
    setRenownError(null);
    setRenownSubmitting(true);
    try {
      const result = await postRenownAdjust(characterId, {
        scale: renownScale,
        delta,
        reason: r,
        request_id: newRequestId(),
      });
      const text = `${label(RENOWN_SCALE_LABELS, result.scale)}: ${result.value_before} → ${result.value_after}`;
      if (result.duplicate) toast(`Уже применено. ${text}`);
      else toast.success(text);
      setRenownDelta('');
      setRenownReason('');
      load();
    } catch (e) {
      const msg = apiErrorMessage(e, 'Не удалось изменить славу');
      setRenownError(msg);
      toast.error(msg);
    } finally {
      setRenownSubmitting(false);
    }
  };

  const enc = data?.encounter ?? null;
  const jail = data?.jail ?? null;

  return (
    <section className="gray-bg p-4 sm:p-6 flex flex-col gap-5 min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="gold-text text-xl font-medium uppercase tracking-[0.06em]">Закон</h2>
        <button type="button" className="btn-line !w-auto !px-4 !py-1 !text-sm disabled:opacity-40" disabled={loading}
          onClick={load}>
          Обновить
        </button>
      </div>

      {loadError && !data && <p className="text-site-red text-sm">{loadError}</p>}
      {loading && !data && !loadError && (
        <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      )}

      {data && (
        <>
          {/* Wanted per region */}
          <div className="flex flex-col gap-2 min-w-0">
            <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">Розыск по краям</h3>
            {data.wanted.length === 0 ? (
              <p className="text-white/50 text-sm">Персонажа нигде не разыскивают</p>
            ) : (
              <div className="flex flex-col divide-y divide-white/[0.06]">
                {data.wanted.map((w) => (
                  <div key={w.region_id} className="grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1.5fr)] gap-x-3 gap-y-1 py-2 items-center">
                    <span className="text-white text-sm truncate">{w.region_name ?? `Край #${w.region_id}`}</span>
                    <span className="text-site-red text-base font-medium text-right sm:text-left">{w.value}</span>
                    <span className="text-white/70 text-sm col-span-2 sm:col-span-1">{w.level_name ?? 'ниже первой ступени'}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Open encounter */}
          {enc && (
            <div className="flex flex-col gap-3 rounded-card border border-white/[0.07] bg-white/[0.02] p-3 sm:p-4 min-w-0">
              <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">
                Задержан стражей — {label(ENCOUNTER_STATUS_LABELS, enc.status)}
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                <Info name="Край">{enc.region_name ?? `#${enc.region_id}`}</Info>
                <Info name="Стражник">{enc.guard_name ?? (enc.guard_npc_id ? `НПС #${enc.guard_npc_id}` : '—')}</Info>
                <Info name="Ступень">
                  {enc.level_name ?? enc.level_code} · розыск {enc.wanted_value}
                  {enc.is_outlaw && <span className="text-site-red"> · вне закона</span>}
                </Info>
                <Info name="Штраф / срок">{enc.fine} · {enc.jail_hours} ч{!enc.has_jail && ' (в крае нет тюрьмы)'}</Info>
                <Info name="Варианты">{enc.options.map((o) => label(CHOICE_LABELS, o)).join(', ') || '—'}</Info>
                <Info name="Шанс бегства">
                  {enc.flee_chance_pct != null ? `${enc.flee_chance_pct}%` : '—'}
                  {enc.flee_used && ' (уже пытался)'}
                </Info>
                <Info name="Как попал">{label(SOURCE_LABELS, enc.source)}</Info>
                <Info name="Бой">{enc.battle_id ? `#${enc.battle_id}` : '—'}</Info>
                <Info name="Автоответ через">
                  <RemainingText until={enc.expires_at} prefix="" doneText="истекло" className="text-gold" />
                </Info>
                <Info name="Начало">{formatServerDateTime(enc.created_at)}</Info>
              </div>
            </div>
          )}

          {/* Jail */}
          {jail && (
            <div className="flex flex-col gap-3 rounded-card border border-white/[0.07] bg-white/[0.02] p-3 sm:p-4 min-w-0">
              <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">В тюрьме</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                <Info name="Край">{jail.region_name ?? `#${jail.region_id}`}</Info>
                <Info name="Локация">{jail.location_name ?? `#${jail.location_id}`}</Info>
                <Info name="Осталось">
                  <RemainingText until={jail.until} prefix="" doneText="истекло" className="text-gold" />
                </Info>
                <Info name="Залог">{jail.bail_price}</Info>
                <Info name="Шанс побега">{jail.escape_chance_pct}% · попыток {jail.escape_attempts}</Info>
                <Info name="Следующий побег">
                  {jail.can_escape_at
                    ? <RemainingText until={jail.can_escape_at} prefix="через" doneText="можно сейчас" />
                    : 'можно сейчас'}
                </Info>
                <Info name="Срок с">{formatServerDateTime(jail.started_at)}</Info>
                <Info name="Встреча">{jail.encounter_id ? `#${jail.encounter_id}` : '—'}</Info>
              </div>
            </div>
          )}

          {/* Staff actions */}
          {canManage && (
            <div className="flex flex-col gap-4 min-w-0">
              <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">Решение властей</h3>
              <div className="grid grid-cols-2 gap-2 sm:max-w-md">
                {(['clear', 'release'] as StaffAction[]).map((a) => (
                  <button key={a} type="button" disabled={submitting} onClick={() => setAction(a)}
                    className={`chip-outline rounded-card px-3 py-2 text-sm ${action === a ? 'chip-outline-active' : ''}`}>
                    {a === 'clear' ? 'Снять розыск' : 'Освободить'}
                  </button>
                ))}
              </div>

              {action === 'clear' ? (
                <label className="flex flex-col gap-1 sm:max-w-md">
                  <span className={LABEL}>Край</span>
                  <select className="input-underline w-full" value={region} disabled={submitting}
                    onChange={(e) => setRegion(e.target.value)}>
                    <option value={ALL_REGIONS} className="bg-site-dark text-white">Все края</option>
                    {data.wanted.map((w) => (
                      <option key={w.region_id} value={String(w.region_id)} className="bg-site-dark text-white">
                        {w.region_name ?? `Край #${w.region_id}`} ({w.value})
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <p className="text-white/50 text-sm">
                  {canRelease
                    ? 'Персонаж выйдет из тюрьмы и/или будет отпущен стражей. Розыск не меняется.'
                    : 'Персонаж не в тюрьме и не задержан стражей — освобождать некого.'}
                </p>
              )}

              <label className="flex flex-col gap-1">
                <span className={LABEL}>Причина (обязательно)</span>
                <textarea className="textarea-bordered text-sm" rows={3} maxLength={LAW_REASON_MAX} value={reason}
                  disabled={submitting} placeholder="Почему принято решение — видно только в админке"
                  onChange={(e) => setReason(e.target.value)} />
                <span className="text-white/40 text-xs self-end">{reason.trim().length}/{LAW_REASON_MAX}</span>
              </label>

              {formError && <p className="text-site-red text-sm">{formError}</p>}

              <div>
                <button type="button" className="btn-blue w-full sm:w-auto !px-8 disabled:opacity-50"
                  disabled={submitting || reason.trim().length < LAW_REASON_MIN || (action === 'release' && !canRelease)}
                  onClick={() => void submit()}>
                  {submitting ? 'Применение...' : action === 'clear' ? 'Снять розыск' : 'Освободить'}
                </button>
              </div>
            </div>
          )}

          {/* Crimes */}
          <div className="flex flex-col gap-2 min-w-0">
            <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">Преступления</h3>
            {data.crimes.length === 0 ? (
              <p className="text-white/50 text-sm">Преступлений нет</p>
            ) : (
              <div className="flex flex-col divide-y divide-white/[0.06]">
                {data.crimes.map((c) => {
                  const open = isOpenCrime(c.status);
                  return (
                    <div key={c.id} className="py-2 flex flex-col gap-1 min-w-0">
                      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 min-w-0">
                        <span className="text-white/40 text-xs">{formatServerDateTime(c.created_at)}</span>
                        <span className="text-white text-sm">{label(CRIME_TYPE_LABELS, c.crime_type)}</span>
                        <span className="text-white/70 text-sm">{c.region_name ?? `Край #${c.region_id}`}</span>
                        <span className="text-site-red text-sm">
                          +{c.wanted_applied}
                          {c.wanted_applied !== c.wanted_points && (
                            <span className="text-white/40 text-xs"> (из {c.wanted_points})</span>
                          )}
                        </span>
                        <span className={`text-xs uppercase tracking-[0.06em] ${CRIME_STATUS_CLASSES[c.status] ?? 'text-white/50'}`}>
                          {crimeStatusLabel(c.status, c.revealed_at)}
                        </span>
                        {c.masked && <span className="text-white/60 text-xs">маска</span>}
                        {c.battle_id && <span className="text-white/40 text-xs">бой #{c.battle_id}</span>}
                      </div>
                      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-xs text-white/60">
                        {c.witness_chance_pct != null && (
                          <span>
                            свидетели: шанс {pct(c.witness_chance_pct)}
                            {c.witness_roll_pct != null && `, бросок ${pct(c.witness_roll_pct)}`}
                          </span>
                        )}
                        {c.reputation_delta != null && <span>репутация {c.reputation_delta}</span>}
                        {c.wanted_floor != null && <span>розыск не меньше {c.wanted_floor}</span>}
                        {(open || c.reveal_attempts > 0) && <span>попыток раскрытия {c.reveal_attempts}</span>}
                        {open && c.next_roll_at && (
                          <span>
                            бросок <RemainingText until={c.next_roll_at} prefix="через" doneText="при следующем проходе" />
                          </span>
                        )}
                        {open && c.reveal_until && (
                          <span>
                            закроется <RemainingText until={c.reveal_until} prefix="через" doneText="срок истёк" />
                          </span>
                        )}
                        {c.revealed_at && <span>раскрыто {formatServerDateTime(c.revealed_at)}</span>}
                      </div>
                      {canManage && open && (
                        <div className="flex flex-wrap gap-2 pt-1">
                          <button type="button" className="btn-line !w-auto !px-4 !py-1 !text-sm"
                            onClick={() => openCrimeAction(c, 'reveal')}>
                            Раскрыть
                          </button>
                          <button type="button" className="btn-line !w-auto !px-4 !py-1 !text-sm"
                            onClick={() => openCrimeAction(c, 'close')}>
                            Закрыть дело
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Renown (FEAT-199) */}
          <div className="flex flex-col gap-3 min-w-0">
            <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">Слава и дурная слава</h3>
            {data.renown ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Info name="Слава (публичная)">
                  <span className="text-gold font-medium">{data.renown.fame}</span> · {data.renown.fame_tier_name}
                </Info>
                <Info name="Дурная слава (тайная)">
                  <span className="text-site-red font-medium">{data.renown.infamy}</span> · {data.renown.infamy_tier_name}
                </Info>
              </div>
            ) : (
              <p className="text-white/50 text-sm">Нет данных о славе</p>
            )}

            {canManage && (
              <div className="flex flex-col gap-3 rounded-card border border-white/[0.07] bg-white/[0.02] p-3 sm:p-4 min-w-0">
                <span className={LABEL}>Изменить славу / дурную славу</span>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:max-w-lg">
                  <div className="grid grid-cols-2 gap-2">
                    {(['fame', 'infamy'] as RenownScale[]).map((sc) => (
                      <button key={sc} type="button" disabled={renownSubmitting} onClick={() => setRenownScale(sc)}
                        className={`chip-outline rounded-card px-3 py-2 text-sm ${renownScale === sc ? 'chip-outline-active' : ''}`}>
                        {RENOWN_SCALE_LABELS[sc]}
                      </button>
                    ))}
                  </div>
                  <label className="flex flex-col gap-1 min-w-0">
                    <span className={LABEL}>Изменение (±)</span>
                    <input className="input-underline w-full" inputMode="numeric" value={renownDelta}
                      placeholder="например, 50 или -20" disabled={renownSubmitting}
                      onChange={(e) => {
                        if (SIGNED_INT_RE.test(e.target.value)) setRenownDelta(e.target.value);
                      }} />
                  </label>
                </div>
                <label className="flex flex-col gap-1">
                  <span className={LABEL}>Причина (обязательно)</span>
                  <textarea className="textarea-bordered text-sm" rows={2} maxLength={LAW_REASON_MAX} value={renownReason}
                    disabled={renownSubmitting} placeholder="Почему меняется слава — видно только в админке"
                    onChange={(e) => setRenownReason(e.target.value)} />
                  <span className="text-white/40 text-xs self-end">{renownReason.trim().length}/{LAW_REASON_MAX}</span>
                </label>
                {renownError && <p className="text-site-red text-sm">{renownError}</p>}
                <div>
                  <button type="button" className="btn-blue w-full sm:w-auto !px-8 disabled:opacity-50"
                    disabled={renownSubmitting || renownReason.trim().length < LAW_REASON_MIN || renownDelta.trim() === ''}
                    onClick={() => void submitRenown()}>
                    {renownSubmitting ? 'Применение...' : 'Изменить'}
                  </button>
                </div>
              </div>
            )}

            <div className="flex flex-col gap-2 min-w-0">
              <span className={LABEL}>Журнал славы (последние 50)</span>
              {data.renown_log.length === 0 ? (
                <p className="text-white/50 text-sm">Записей нет</p>
              ) : (
                <div className="flex flex-col divide-y divide-white/[0.06]">
                  {data.renown_log.map((x) => (
                    <div key={x.id} className="py-2 flex flex-col gap-1 min-w-0">
                      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                        <span className="text-white/40 text-xs">{formatServerDateTime(x.created_at)}</span>
                        <span className="text-white text-sm">{label(RENOWN_SCALE_LABELS, x.scale)}</span>
                        <span className={`text-sm font-medium ${x.delta >= 0 ? 'text-gold' : 'text-site-red'}`}>
                          {x.delta > 0 ? `+${x.delta}` : x.delta}
                        </span>
                        <span className="text-white/70 text-sm">→ {x.value_after}</span>
                        <span className="text-white/50 text-xs">{label(RENOWN_SOURCE_LABELS, x.source)}</span>
                        {x.ref_id != null && <span className="text-white/40 text-xs">#{x.ref_id}</span>}
                      </div>
                      {x.tier_before !== x.tier_after && (
                        <div className="text-xs text-white/60 break-words">
                          ступень: {renownTierName(tierNames, x.scale, x.tier_before)} →{' '}
                          {renownTierName(tierNames, x.scale, x.tier_after)}
                        </div>
                      )}
                      {x.reason && <div className="text-xs text-white/50 break-words">{x.reason}</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Log */}
          <div className="flex flex-col gap-2 min-w-0">
            <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">Журнал закона</h3>
            {data.log.length === 0 ? (
              <p className="text-white/50 text-sm">Записей нет</p>
            ) : (
              <div className="flex flex-col divide-y divide-white/[0.06]">
                {data.log.map((x) => {
                  const change = wantedChange(x);
                  return (
                    <div key={x.id} className="py-2 flex flex-col gap-1 min-w-0">
                      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                        <span className="text-white/40 text-xs">{formatServerDateTime(x.created_at)}</span>
                        <span className="text-white text-sm">{label(LOG_LABELS, x.action)}</span>
                        {x.region_name && <span className="text-white/70 text-sm">{x.region_name}</span>}
                      </div>
                      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-xs text-white/60">
                        {change && <span>{change}</span>}
                        {x.amount != null && <span>сумма {x.amount}</span>}
                        {x.chance_pct != null && (
                          <span>
                            шанс {x.chance_pct}%{x.roll_pct != null && `, бросок ${x.roll_pct}`}
                          </span>
                        )}
                      </div>
                      {(x.reason || x.actor_username) && (
                        <div className="text-xs text-white/50 break-words">
                          {x.actor_username && <span className="text-white/70">{x.actor_username}: </span>}
                          {x.reason}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}

      <CrimeActionModal target={crimeTarget} action={crimeAction} onClose={() => setCrimeTarget(null)} onDone={load} />
    </section>
  );
};

export default LawPanel;
