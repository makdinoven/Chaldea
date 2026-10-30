import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import toast from 'react-hot-toast';
import { ChevronRight, Plus, RefreshCw, Trash2 } from 'lucide-react';
import {
  deleteEconomyEventTemplate,
  fetchEconomyActiveEvents,
  fetchEconomyEventTemplates,
  fetchEconomyEventsHistory,
  fetchEconomyGoodsGroups,
  fetchEconomyRegions,
  fetchEconomyTemplates,
  postEconomyEventCancel,
  postEconomyEventStart,
  putEconomyEventTemplate,
} from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import type {
  EconEventKind,
  EconEventOrigin,
  EconEventScope,
  EconEventStartResult,
  EconEventStatus,
  EconEventTemplate,
  EconEventTemplateUpdate,
  EconGoodsGroup,
  EconRegionEvent,
  EconRegionItem,
  EconRegionTemplate,
} from '../../../types/economy';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import ConfirmationModal from '../../ui/ConfirmationModal';
import AdminPagination from '../AdminPagination/AdminPagination';
import EventIcon from '../../common/EventIcon';
import { newRequestId } from '../../pages/LocationPage/BankModal/bankFormat';
import EventTemplateEditor from './EventTemplateEditor';
import { draftToEffect, effectToDraft } from './EventEffectsBuilder';
import { BigMoney } from './CompactValue';
import { compactNumber, exactNumber } from '../../../utils/compactNumber';
import { formatDateTime, formatQty } from './economyLabels';
import {
  KIND_LABELS,
  ORIGIN_LABELS,
  SCOPE_LABELS,
  STATUS_LABELS,
  TRIGGER_LABELS,
  describeEffect,
  durationText,
  kindBadgeClass,
  kindTextClass,
  labelOf,
  remainingText,
  seasonLabel,
} from './eventLabels';
import { FieldHint } from './ParamHint';

type View = 'active' | 'start' | 'templates' | 'history';

const VIEW_LABEL: Record<View, string> = {
  active: 'Активные',
  start: 'Запустить',
  templates: 'Шаблоны',
  history: 'История',
};

const COMMENT_MIN = 3;
const COMMENT_MAX = 500;
const DURATION_MAX = 365;
const HISTORY_PAGE_SIZE = 50;

const Spinner = () => <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

const regionLabel = (regionId: number, names: Record<number, string>, snapshot?: string | null): string =>
  names[regionId] ?? snapshot ?? `Регион #${regionId}`;

/** Shared data of every sub-view: region names, goods group names, templates. */
interface Ctx {
  regions: EconRegionItem[];
  regionNames: Record<number, string>;
  groups: EconGoodsGroup[];
  groupNames: Record<string, string>;
  regionTemplates: EconRegionTemplate[];
  templates: EconEventTemplate[] | null;
  templatesError: string | null;
  reloadTemplates: () => void;
  canSettings: boolean;
}

/* ------------------------------------------------------------------ pieces */

const OriginBadge = ({ origin }: { origin: string }) => (
  <span className="inline-flex rounded-full border border-white/15 px-2 py-0.5 text-white/60 text-[10px] uppercase tracking-[0.06em] whitespace-nowrap">
    {labelOf(ORIGIN_LABELS, origin)}
  </span>
);

const KindBadge = ({ kind }: { kind: string }) => (
  <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.06em] whitespace-nowrap ${kindBadgeClass(kind)}`}>
    {labelOf(KIND_LABELS, kind)}
  </span>
);

/** One-shot results of an event: population change, lost stock, treasury expense. */
const Outcome = ({ ev, groupNames }: { ev: EconRegionEvent; groupNames: Record<string, string> }) => {
  const lines: ReactNode[] = [];
  if (ev.population_before != null && ev.population_after != null) {
    const diff = ev.population_after - ev.population_before;
    lines.push(
      <span key="pop" title={`${exactNumber(ev.population_before)} → ${exactNumber(ev.population_after)} жит.`}>
        население {diff >= 0 ? '+' : '−'}
        {compactNumber(Math.abs(diff))}
      </span>,
    );
  }
  const lost = Object.entries(ev.outcome?.stock_lost ?? {}).filter(([, units]) => units > 0);
  if (lost.length > 0) {
    lines.push(
      <span key="stock">
        потеряно на складах: {lost.map(([code, units]) => `${(groupNames[code] ?? code).toLowerCase()} ${formatQty(units)}`).join(', ')}
      </span>,
    );
  }
  const expense = ev.outcome?.treasury_expense ?? 0;
  if (expense > 0) {
    lines.push(
      <span key="treasury">
        из казны на восстановление <BigMoney value={expense} />
      </span>,
    );
  }
  const hasOneShots = ev.effects.some((e) => ['stock_loss', 'treasury_expense', 'population'].includes(e.type));
  if (lines.length === 0) {
    if (!ev.applied_at && hasOneShots && ev.status === 'active') {
      return <p className="text-white/40 text-xs">Разовые эффекты сработают в ближайшем пересчёте.</p>;
    }
    return null;
  }
  return <p className="flex flex-col gap-0.5 text-white/60 text-xs break-words">{lines}</p>;
};

/* ------------------------------------------------------------------ cancel dialog */

interface CancelDialogProps {
  ev: EconRegionEvent;
  regionName: string;
  onClose: () => void;
  onDone: () => void;
}

const CancelDialog = ({ ev, regionName, onClose, onDone }: CancelDialogProps) => {
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const trimmed = comment.trim();
  const commentOk = trimmed.length >= COMMENT_MIN && trimmed.length <= COMMENT_MAX;

  const submit = async () => {
    setBusy(true);
    try {
      await postEconomyEventCancel(ev.id, trimmed);
      toast.success(`Событие «${ev.name}» в регионе «${regionName}» отменено`);
      onDone();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось отменить событие'));
      setBusy(false);
    }
  };

  return (
    <ModalShell
      open
      onClose={onClose}
      dismissible={!busy}
      title="Отменить событие"
      size="md"
      footer={
        <>
          <button type="button" className="btn-line w-full sm:w-auto !text-xs !py-2 !px-5" onClick={onClose} disabled={busy}>
            Не отменять
          </button>
          <button
            type="button"
            className="btn-blue w-full sm:w-auto !py-2 !px-5 !text-xs"
            disabled={!commentOk || busy}
            onClick={submit}
          >
            {busy ? 'Отмена...' : 'Отменить событие'}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4 text-sm">
        <p className="text-white/80 break-words">
          «{ev.name}» в регионе «{regionName}» закончится сейчас: со следующего пересчёта перестанут действовать его
          производство, цены, стабильность и другие эффекты.
        </p>
        <p className="field-hint field-hint-strong">
          Разовые последствия не откатываются: погибшие жители, потерянные запасы и деньги, ушедшие из казны на
          восстановление, остаются. Чтобы их вернуть, поправьте регион вручную.
        </p>
        <div className="flex flex-col gap-1">
          <label htmlFor="econ-ev-cancel-comment" className="text-white/60 text-xs uppercase tracking-[0.06em]">
            Комментарий (обязательно)
          </label>
          <textarea
            id="econ-ev-cancel-comment"
            className="textarea-bordered w-full"
            rows={3}
            maxLength={COMMENT_MAX}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Почему событие отменяется"
          />
          {comment !== '' && !commentOk && (
            <p className="text-site-red text-xs">
              От {COMMENT_MIN} до {COMMENT_MAX} символов
            </p>
          )}
        </div>
      </div>
    </ModalShell>
  );
};

/* ------------------------------------------------------------------ «Активные» */

const ActiveView = ({ ctx }: { ctx: Ctx }) => {
  const [regionId, setRegionId] = useState('');
  const [items, setItems] = useState<EconRegionEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [cancelling, setCancelling] = useState<EconRegionEvent | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(() => {
    setLoading(true);
    fetchEconomyActiveEvents(regionId ? Number(regionId) : undefined)
      .then((list) => {
        setItems(list);
        setError(null);
        setNow(Date.now());
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить активные события');
        setError(msg);
        toast.error(msg);
      })
      .finally(() => setLoading(false));
  }, [regionId]);

  useEffect(load, [load]);

  const participating = ctx.regions.filter((r) => r.simulated);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-end gap-3">
        <div className="flex flex-col gap-1 min-w-0 sm:w-72">
          <label htmlFor="econ-ev-active-region" className="text-white/60 text-xs uppercase tracking-[0.06em]">
            Регион
          </label>
          <select
            id="econ-ev-active-region"
            className="input-underline w-full"
            value={regionId}
            onChange={(e) => setRegionId(e.target.value)}
          >
            <option value="" className="bg-site-dark text-white">Все регионы</option>
            {participating.map((r) => (
              <option key={r.region_id} value={r.region_id} className="bg-site-dark text-white">
                {r.name ?? `Регион #${r.region_id}`}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="sm:ml-auto self-start sm:self-end inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-site-blue transition-colors duration-200 ease-site disabled:opacity-40"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Обновить
        </button>
      </div>

      {error && <p className="text-site-red text-sm">{error}</p>}
      {!items && !error && <Spinner />}
      {items && items.length === 0 && (
        <p className="text-white/40 text-sm italic">{regionId ? 'В этом регионе событий нет.' : 'Сейчас ни в одном регионе нет событий.'}</p>
      )}

      {items && items.length > 0 && (
        <ul className={`grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 transition-opacity ${loading ? 'opacity-60' : ''}`}>
          {items.map((ev) => {
            const region = regionLabel(ev.region_id, ctx.regionNames, ev.region_name);
            return (
              <li key={ev.id} className="bg-site-bg rounded-card border border-white/[0.07] p-4 flex flex-col gap-2 min-w-0">
                <div className="flex items-start gap-2">
                  <EventIcon name={ev.icon} size={18} className={`shrink-0 mt-0.5 ${kindTextClass(ev.kind)}`} />
                  <div className="flex-1 min-w-0 flex flex-col">
                    <span className={`font-medium break-words ${kindTextClass(ev.kind)}`}>{ev.name}</span>
                    <span className="text-white/70 text-sm break-words">{region}</span>
                  </div>
                  <OriginBadge origin={ev.origin} />
                </div>
                <p className="text-white text-sm">{remainingText(ev.ends_at, now)}</p>
                <p className="text-white/40 text-xs">
                  {formatDateTime(ev.started_at)} → {formatDateTime(ev.ends_at)}
                </p>
                <Outcome ev={ev} groupNames={ctx.groupNames} />
                {ctx.canSettings && (
                  <button
                    type="button"
                    className="btn-line w-full sm:w-auto sm:self-start !text-xs !py-2 !px-5 mt-auto"
                    onClick={() => setCancelling(ev)}
                  >
                    Отменить
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {cancelling && (
        <CancelDialog
          ev={cancelling}
          regionName={regionLabel(cancelling.region_id, ctx.regionNames, cancelling.region_name)}
          onClose={() => setCancelling(null)}
          onDone={() => {
            setCancelling(null);
            load();
            ctx.reloadTemplates();
          }}
        />
      )}
    </div>
  );
};

/* ------------------------------------------------------------------ «Запустить» */

const StartView = ({ ctx }: { ctx: Ctx }) => {
  const [templateId, setTemplateId] = useState('');
  const [regionId, setRegionId] = useState('');
  const [scope, setScope] = useState<'' | EconEventScope>('');
  const [duration, setDuration] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<EconEventStartResult | null>(null);

  const templates = ctx.templates ?? [];
  const template = templates.find((t) => String(t.id) === templateId) ?? null;
  const participating = ctx.regions.filter((r) => r.simulated);
  const region = participating.find((r) => String(r.region_id) === regionId) ?? null;
  const durationNum = Number(duration);
  const durationOk = duration.trim() === '' || (Number.isFinite(durationNum) && durationNum > 0 && durationNum <= DURATION_MAX);
  const effectiveScope: EconEventScope = scope || template?.scope || 'region';
  const canSubmit = template !== null && region !== null && durationOk && !busy;

  const submit = async () => {
    if (!template || !region) return;
    setConfirming(false);
    setBusy(true);
    try {
      const res = await postEconomyEventStart({
        template_id: template.id,
        region_id: region.region_id,
        scope: scope || null,
        duration_days: duration.trim() === '' ? null : durationNum,
        request_id: newRequestId(),
      });
      setResult(res);
      const skippedText = res.skipped.length > 0 ? `, пропущено: ${res.skipped.length}` : '';
      toast.success(`«${template.name}» запущено в регионах: ${res.started.length}${skippedText}`);
      ctx.reloadTemplates();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось запустить событие'));
    } finally {
      setBusy(false);
    }
  };

  if (ctx.templatesError && !ctx.templates) return <p className="text-site-red text-sm">{ctx.templatesError}</p>;
  if (!ctx.templates) return <Spinner />;

  return (
    <div className="flex flex-col gap-5">
      <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
        <p className="text-white/60 text-sm max-w-2xl">
          Запустить можно любое событие, даже выключенное или «только вручную». Разовые эффекты (население, запасы,
          казна) сработают в ближайшем пересчёте — «Пересчитать сейчас» применит их сразу.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="flex flex-col gap-1 min-w-0">
            <label htmlFor="econ-ev-start-template" className="text-white/60 text-xs uppercase tracking-[0.06em]">
              Событие
            </label>
            <select
              id="econ-ev-start-template"
              className="input-underline w-full"
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
            >
              <option value="" className="bg-site-dark text-white">Выберите событие</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id} className="bg-site-dark text-white">
                  {t.name}
                  {t.is_enabled ? '' : ' (выключено)'}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1 min-w-0">
            <label htmlFor="econ-ev-start-region" className="text-white/60 text-xs uppercase tracking-[0.06em]">
              Регион
            </label>
            <select
              id="econ-ev-start-region"
              className="input-underline w-full"
              value={regionId}
              onChange={(e) => setRegionId(e.target.value)}
            >
              <option value="" className="bg-site-dark text-white">Выберите регион</option>
              {participating.map((r) => (
                <option key={r.region_id} value={r.region_id} className="bg-site-dark text-white">
                  {r.name ?? `Регион #${r.region_id}`}
                  {r.country_name ? ` — ${r.country_name}` : ''}
                </option>
              ))}
            </select>
            {participating.length === 0 && (
              <p className="text-white/40 text-xs">Нет регионов, которые участвуют в пересчёте.</p>
            )}
          </div>
          <div className="flex flex-col gap-1 min-w-0">
            <span className="flex items-center gap-1">
              <label htmlFor="econ-ev-start-scope" className="text-white/60 text-xs uppercase tracking-[0.06em]">
                Область
              </label>
              <FieldHint field="event_start_scope" label="Область запуска" />
            </span>
            <select
              id="econ-ev-start-scope"
              className="input-underline w-full"
              value={scope}
              onChange={(e) => setScope(e.target.value as '' | EconEventScope)}
            >
              <option value="" className="bg-site-dark text-white">
                Как в шаблоне{template ? ` (${SCOPE_LABELS[template.scope].toLowerCase()})` : ''}
              </option>
              {(Object.keys(SCOPE_LABELS) as EconEventScope[]).map((s) => (
                <option key={s} value={s} className="bg-site-dark text-white">
                  {SCOPE_LABELS[s]}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1 min-w-0">
            <span className="flex items-center gap-1">
              <label htmlFor="econ-ev-start-duration" className="text-white/60 text-xs uppercase tracking-[0.06em]">
                Длительность, дн.
              </label>
              <FieldHint field="event_start_duration" label="Длительность запуска" />
            </span>
            <input
              id="econ-ev-start-duration"
              type="number"
              inputMode="decimal"
              min={0}
              max={DURATION_MAX}
              step={0.5}
              className={`input-underline w-full ${durationOk ? '' : '!border-site-red'}`}
              value={duration}
              placeholder={template ? `по шаблону: ${durationText(template.duration_min_days, template.duration_max_days)}` : 'по шаблону'}
              onChange={(e) => setDuration(e.target.value)}
            />
            {!durationOk && <p className="text-site-red text-xs">Больше 0 и не больше {DURATION_MAX} дней</p>}
          </div>
        </div>

        {template && (
          <div className="flex flex-col gap-2 rounded-card border border-white/[0.07] bg-white/[0.03] p-3 min-w-0">
            <span className={`flex items-center gap-2 font-medium ${kindTextClass(template.kind)}`}>
              <EventIcon name={template.icon} size={16} className="shrink-0" />
              <span className="break-words min-w-0">{template.name}</span>
            </span>
            <span className="text-white/70 text-xs break-words">{template.player_text}</span>
            <ul className="flex flex-col gap-0.5 text-white/80 text-xs">
              {template.effects.map((e, i) => (
                <li key={i} className="break-words">• {describeEffect(e, ctx.groupNames)}</li>
              ))}
            </ul>
            {template.active_count > 0 && (
              <span className="text-white/40 text-xs">Сейчас идёт в регионах: {template.active_count}</span>
            )}
          </div>
        )}

        <button
          type="button"
          className="btn-blue w-full sm:w-auto sm:self-start !px-6"
          disabled={!canSubmit}
          onClick={() => setConfirming(true)}
        >
          {busy ? 'Запуск...' : 'Запустить'}
        </button>
      </section>

      {result && (
        <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-3 min-w-0">
          <h3 className="gold-text text-base font-medium uppercase tracking-[0.06em]">Результат запуска</h3>
          {result.started.length > 0 ? (
            <div className="flex flex-col gap-1">
              <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Началось ({result.started.length})</span>
              <ul className="flex flex-col gap-0.5 text-sm">
                {result.started.map((ev) => (
                  <li key={ev.id} className="text-white break-words">
                    {regionLabel(ev.region_id, ctx.regionNames, ev.region_name)}{' '}
                    <span className="text-white/40 text-xs">— {remainingText(ev.ends_at)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-white/60 text-sm">Ни в одном регионе событие не началось.</p>
          )}
          {result.skipped.length > 0 && (
            <div className="flex flex-col gap-1">
              <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Пропущено ({result.skipped.length})</span>
              <ul className="flex flex-col gap-0.5 text-sm">
                {result.skipped.map((s) => (
                  <li key={s.region_id} className="text-white/70 break-words">
                    {regionLabel(s.region_id, ctx.regionNames, s.region_name)}: <span className="text-white/50">{s.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <ConfirmationModal
        isOpen={confirming && template !== null && region !== null}
        title="Запустить событие?"
        message={
          template && region
            ? `«${template.name}» начнётся: ${
                effectiveScope === 'region'
                  ? `в регионе «${region.name ?? `#${region.region_id}`}»`
                  : `${SCOPE_LABELS[effectiveScope].toLowerCase()} (от региона «${region.name ?? `#${region.region_id}`}»)`
              }, ${duration.trim() ? `${duration} дн.` : durationText(template.duration_min_days, template.duration_max_days)}; разовые эффекты сработают в ближайшем пересчёте.`
            : ''
        }
        onCancel={() => setConfirming(false)}
        onConfirm={submit}
      />
    </div>
  );
};

/* ------------------------------------------------------------------ «Шаблоны» */

const toUpdate = (t: EconEventTemplate, patch: Partial<EconEventTemplateUpdate> = {}): EconEventTemplateUpdate => ({
  name: t.name,
  icon: t.icon,
  kind: t.kind,
  player_text: t.player_text,
  admin_note: t.admin_note,
  trigger_kind: t.trigger_kind,
  weight: t.weight,
  duration_min_days: t.duration_min_days,
  duration_max_days: t.duration_max_days,
  scope: t.scope,
  spread_chance: t.spread_chance,
  region_templates: t.region_templates ?? [],
  seasons: t.seasons ?? [],
  // Only the fields of each effect's type: the server rejects extra (even null) fields.
  effects: t.effects.map((e) => draftToEffect(effectToDraft(e))),
  chains: t.chains ?? [],
  is_enabled: t.is_enabled,
  ...patch,
});

const TemplatesView = ({ ctx }: { ctx: Ctx }) => {
  const [editing, setEditing] = useState<EconEventTemplate | 'new' | null>(null);
  const [deleting, setDeleting] = useState<EconEventTemplate | null>(null);
  const [toggling, setToggling] = useState<number | null>(null);
  const [kindFilter, setKindFilter] = useState<'' | EconEventKind>('');

  const templateNames = useMemo(
    () => Object.fromEntries((ctx.templates ?? []).map((t) => [t.code, t.name])),
    [ctx.templates],
  );
  const regionTemplateNames = useMemo(
    () => Object.fromEntries(ctx.regionTemplates.map((t) => [t.code, t.name])),
    [ctx.regionTemplates],
  );

  const toggleEnabled = async (t: EconEventTemplate) => {
    setToggling(t.id);
    try {
      await putEconomyEventTemplate(t.id, toUpdate(t, { is_enabled: !t.is_enabled }));
      toast.success(t.is_enabled ? `«${t.name}» выключено` : `«${t.name}» включено`);
      ctx.reloadTemplates();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось изменить событие'));
    } finally {
      setToggling(null);
    }
  };

  const remove = async () => {
    const t = deleting;
    setDeleting(null);
    if (!t) return;
    try {
      await deleteEconomyEventTemplate(t.id);
      toast.success(`Событие «${t.name}» удалено`);
      ctx.reloadTemplates();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось удалить событие'));
    }
  };

  if (ctx.templatesError && !ctx.templates) return <p className="text-site-red text-sm">{ctx.templatesError}</p>;
  if (!ctx.templates) return <Spinner />;

  const list = ctx.templates.filter((t) => !kindFilter || t.kind === kindFilter);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex flex-wrap gap-2">
          {([['', 'Все'], ['bad', 'Кризисы'], ['good', 'Благоприятные']] as ['' | EconEventKind, string][]).map(([k, label]) => (
            <button
              key={k || 'all'}
              type="button"
              aria-pressed={kindFilter === k}
              onClick={() => setKindFilter(k)}
              className={`chip-outline rounded-full px-4 py-1.5 text-xs font-medium ${kindFilter === k ? 'chip-outline-active' : ''}`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="sm:ml-auto flex items-center gap-4">
          <button
            type="button"
            onClick={ctx.reloadTemplates}
            className="inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-site-blue transition-colors duration-200 ease-site"
          >
            <RefreshCw size={14} />
            Обновить
          </button>
          {ctx.canSettings && (
            <button
              type="button"
              className="btn-blue !text-xs !py-2 !px-5 inline-flex items-center gap-1.5"
              onClick={() => setEditing('new')}
            >
              <Plus size={14} />
              Новое событие
            </button>
          )}
        </div>
      </div>
      {!ctx.canSettings && (
        <p className="field-hint">Только просмотр: менять события может администратор с правом «economy:settings».</p>
      )}

      {list.length === 0 && <p className="text-white/40 text-sm italic">Событий нет.</p>}
      <ul className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {list.map((t) => (
          <li key={t.id} className={`bg-site-bg rounded-card border border-white/[0.07] p-4 flex flex-col gap-2 min-w-0 ${t.is_enabled ? '' : 'opacity-70'}`}>
            <button type="button" onClick={() => setEditing(t)} className="text-left flex items-start gap-2 group">
              <EventIcon name={t.icon} size={18} className={`shrink-0 mt-0.5 ${kindTextClass(t.kind)}`} />
              <span className="flex-1 min-w-0 flex flex-col">
                <span className={`font-medium break-words group-hover:underline ${kindTextClass(t.kind)}`}>{t.name}</span>
                <span className="text-white/40 text-xs">{t.code}</span>
              </span>
              <ChevronRight size={16} className="text-gold shrink-0 mt-1" />
            </button>
            <span className="flex flex-wrap gap-1.5">
              <KindBadge kind={t.kind} />
              {!t.is_enabled && (
                <span className="inline-flex rounded-full border border-white/15 px-2 py-0.5 text-white/50 text-[10px] uppercase tracking-[0.06em]">
                  выключено
                </span>
              )}
              {t.active_count > 0 && (
                <span className="inline-flex rounded-full border border-gold/40 bg-gold/10 px-2 py-0.5 text-gold text-[10px] uppercase tracking-[0.06em]">
                  идёт: {t.active_count}
                </span>
              )}
            </span>
            <span className="flex flex-col gap-0.5 text-xs text-white/55 break-words">
              <span>
                {labelOf(TRIGGER_LABELS, t.trigger_kind)} · вес {t.weight} · {durationText(t.duration_min_days, t.duration_max_days)} ·{' '}
                {labelOf(SCOPE_LABELS, t.scope).toLowerCase()}
                {t.spread_chance > 0 ? ` · перекинуться ${Math.round(t.spread_chance * 100)} %` : ''}
              </span>
              <span>
                Сезоны: {t.seasons && t.seasons.length > 0 ? t.seasons.map(seasonLabel).join(', ') : 'любые'}
              </span>
              <span>
                Регионы:{' '}
                {t.region_templates && t.region_templates.length > 0
                  ? t.region_templates.map((c) => regionTemplateNames[c] ?? c).join(', ')
                  : 'любые'}
              </span>
              {t.chains && t.chains.length > 0 && (
                <span>
                  Вызывает: {t.chains.map((c) => `${templateNames[c.code] ?? c.code} ${Math.round(c.chance * 100)} %`).join(', ')}
                </span>
              )}
            </span>
            <ul className="flex flex-col gap-0.5 text-white/80 text-xs">
              {t.effects.map((e, i) => (
                <li key={i} className="break-words">• {describeEffect(e, ctx.groupNames)}</li>
              ))}
            </ul>
            {ctx.canSettings && (
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mt-auto pt-1">
                <label className="flex items-center gap-2 text-xs text-white/70 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={t.is_enabled}
                    disabled={toggling === t.id}
                    onChange={() => toggleEnabled(t)}
                    className="w-4 h-4 shrink-0 accent-gold"
                  />
                  Включено
                </label>
                <button
                  type="button"
                  onClick={() => setDeleting(t)}
                  className="ml-auto inline-flex items-center gap-1 text-xs text-white/50 hover:text-site-red transition-colors duration-200 ease-site"
                >
                  <Trash2 size={13} />
                  Удалить
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>

      {editing && (
        <EventTemplateEditor
          key={editing === 'new' ? 'new' : editing.id}
          template={editing === 'new' ? null : editing}
          templates={ctx.templates}
          groups={ctx.groups}
          regionTemplates={ctx.regionTemplates}
          canEdit={ctx.canSettings}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            ctx.reloadTemplates();
          }}
        />
      )}

      <ConfirmationModal
        isOpen={deleting !== null}
        title="Удалить событие?"
        message={
          deleting
            ? `Шаблон «${deleting.name}» будет удалён. ${
                deleting.active_count > 0
                  ? `Идущие события (${deleting.active_count}) доживут до конца по своему снимку.`
                  : 'Идущих событий нет.'
              } История сохранится.`
            : ''
        }
        onCancel={() => setDeleting(null)}
        onConfirm={remove}
      />
    </div>
  );
};

/* ------------------------------------------------------------------ «История» */

const HistoryView = ({ ctx }: { ctx: Ctx }) => {
  const [regionId, setRegionId] = useState('');
  const [templateCode, setTemplateCode] = useState('');
  const [kind, setKind] = useState<'' | EconEventKind>('');
  const [status, setStatus] = useState<'' | EconEventStatus>('');
  const [origin, setOrigin] = useState<'' | EconEventOrigin>('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<EconRegionEvent[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPage(1);
  }, [regionId, templateCode, kind, status, origin, dateFrom, dateTo]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchEconomyEventsHistory({
      region_id: regionId ? Number(regionId) : undefined,
      template_code: templateCode || undefined,
      kind: kind || undefined,
      status: status || undefined,
      origin: origin || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      page,
      page_size: HISTORY_PAGE_SIZE,
    })
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setTotal(res.total);
      })
      .catch((e) => {
        if (cancelled) return;
        setItems([]);
        setTotal(0);
        const msg = apiErrorMessage(e, 'Не удалось загрузить историю событий');
        setError(msg);
        toast.error(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [regionId, templateCode, kind, status, origin, dateFrom, dateTo, page]);

  const hasFilters = Boolean(regionId || templateCode || kind || status || origin || dateFrom || dateTo);
  const totalPages = Math.max(1, Math.ceil(total / HISTORY_PAGE_SIZE));
  const regions = [...ctx.regions].sort((a, b) => (a.name ?? '').localeCompare(b.name ?? '', 'ru'));

  const select = (
    id: string,
    label: string,
    value: string,
    onChange: (v: string) => void,
    options: [string, string][],
  ) => (
    <div className="flex flex-col gap-1 min-w-0">
      <label htmlFor={id} className="text-white/60 text-xs uppercase tracking-[0.06em]">
        {label}
      </label>
      <select id={id} className="input-underline w-full" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="" className="bg-site-dark text-white">Все</option>
        {options.map(([v, l]) => (
          <option key={v} value={v} className="bg-site-dark text-white">
            {l}
          </option>
        ))}
      </select>
    </div>
  );

  const endText = (ev: EconRegionEvent) =>
    ev.status === 'active' ? remainingText(ev.ends_at) : formatDateTime(ev.ended_at ?? ev.ends_at);

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {select('econ-ev-h-region', 'Регион', regionId, setRegionId,
          regions.map((r) => [String(r.region_id), r.name ?? `Регион #${r.region_id}`]))}
        {select('econ-ev-h-template', 'Событие', templateCode, setTemplateCode,
          (ctx.templates ?? []).map((t) => [t.code, t.name]))}
        {select('econ-ev-h-kind', 'Характер', kind, (v) => setKind(v as '' | EconEventKind),
          Object.entries(KIND_LABELS) as [string, string][])}
        {select('econ-ev-h-status', 'Статус', status, (v) => setStatus(v as '' | EconEventStatus),
          Object.entries(STATUS_LABELS) as [string, string][])}
        {select('econ-ev-h-origin', 'Откуда', origin, (v) => setOrigin(v as '' | EconEventOrigin),
          Object.entries(ORIGIN_LABELS) as [string, string][])}
        <div className="flex flex-col gap-1 min-w-0">
          <label htmlFor="econ-ev-h-from" className="text-white/60 text-xs uppercase tracking-[0.06em]">С даты</label>
          <input id="econ-ev-h-from" type="date" className="input-underline w-full [color-scheme:dark]" value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1 min-w-0">
          <label htmlFor="econ-ev-h-to" className="text-white/60 text-xs uppercase tracking-[0.06em]">По дату</label>
          <input id="econ-ev-h-to" type="date" className="input-underline w-full [color-scheme:dark]" value={dateTo}
            onChange={(e) => setDateTo(e.target.value)} />
        </div>
        {hasFilters && (
          <div className="flex items-end">
            <button
              type="button"
              className="btn-line w-full sm:w-auto !text-xs !py-2 !px-5"
              onClick={() => {
                setRegionId('');
                setTemplateCode('');
                setKind('');
                setStatus('');
                setOrigin('');
                setDateFrom('');
                setDateTo('');
              }}
            >
              Сбросить фильтры
            </button>
          </div>
        )}
      </div>

      {error && <p className="text-site-red text-sm">{error}</p>}
      {loading && !items && <Spinner />}
      {items && items.length === 0 && !error && <p className="text-white/40 text-sm italic">Событий не найдено.</p>}

      {items && items.length > 0 && (
        <div className={`md:bg-site-bg md:rounded-card md:border md:border-white/[0.07] md:px-4 md:py-2 transition-opacity ${loading ? 'opacity-60' : ''}`}>
          <table className="hidden md:table w-full text-sm">
            <thead>
              <tr className="text-white/50 text-xs uppercase tracking-[0.06em] text-left border-b border-white/10">
                <th className="py-2 pr-3 font-normal">Начало</th>
                <th className="py-2 pr-3 font-normal">Событие</th>
                <th className="py-2 pr-3 font-normal">Регион</th>
                <th className="py-2 pr-3 font-normal">Откуда</th>
                <th className="py-2 pr-3 font-normal">Статус</th>
                <th className="py-2 font-normal">Итог</th>
              </tr>
            </thead>
            <tbody>
              {items.map((ev) => (
                <tr key={ev.id} className="border-b border-white/[0.07] align-top">
                  <td className="py-2 pr-3 text-white/70 whitespace-nowrap">
                    {formatDateTime(ev.started_at)}
                    {ev.game_segment && <span className="block text-white/40 text-xs">{seasonLabel(ev.game_segment)}</span>}
                  </td>
                  <td className="py-2 pr-3">
                    <span className={`flex items-center gap-1.5 ${kindTextClass(ev.kind)}`}>
                      <EventIcon name={ev.icon} size={15} className="shrink-0" />
                      <span className="break-words">{ev.name}</span>
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-white break-words">{regionLabel(ev.region_id, ctx.regionNames, ev.region_name)}</td>
                  <td className="py-2 pr-3"><OriginBadge origin={ev.origin} /></td>
                  <td className="py-2 pr-3 text-white/80">
                    {labelOf(STATUS_LABELS, ev.status)}
                    <span className="block text-white/40 text-xs whitespace-nowrap">{endText(ev)}</span>
                    {ev.cancel_comment && <span className="block text-white/50 text-xs break-words max-w-[220px]">{ev.cancel_comment}</span>}
                  </td>
                  <td className="py-2 max-w-[260px]"><Outcome ev={ev} groupNames={ctx.groupNames} /></td>
                </tr>
              ))}
            </tbody>
          </table>

          <ul className="md:hidden flex flex-col gap-3">
            {items.map((ev) => (
              <li key={ev.id} className="bg-site-bg rounded-card border border-white/[0.07] p-3 flex flex-col gap-1.5 min-w-0">
                <div className="flex items-start gap-2">
                  <EventIcon name={ev.icon} size={16} className={`shrink-0 mt-0.5 ${kindTextClass(ev.kind)}`} />
                  <span className="flex-1 min-w-0 flex flex-col">
                    <span className={`text-sm font-medium break-words ${kindTextClass(ev.kind)}`}>{ev.name}</span>
                    <span className="text-white/70 text-xs break-words">{regionLabel(ev.region_id, ctx.regionNames, ev.region_name)}</span>
                  </span>
                  <OriginBadge origin={ev.origin} />
                </div>
                <span className="text-white/50 text-xs">
                  {formatDateTime(ev.started_at)}
                  {ev.game_segment ? ` · ${seasonLabel(ev.game_segment)}` : ''} · {labelOf(STATUS_LABELS, ev.status).toLowerCase()} · {endText(ev)}
                </span>
                {ev.cancel_comment && <span className="text-white/50 text-xs break-words">{ev.cancel_comment}</span>}
                <Outcome ev={ev} groupNames={ctx.groupNames} />
              </li>
            ))}
          </ul>
        </div>
      )}

      <AdminPagination page={page} totalPages={totalPages} onPageChange={setPage} total={total} pageSize={HISTORY_PAGE_SIZE} />
    </div>
  );
};

/* ------------------------------------------------------------------ tab */

interface EconomyEventsProps {
  canSettings: boolean;
}

/** «События» (FEAT-187): active events, manual start, templates, history. */
const EconomyEvents = ({ canSettings }: EconomyEventsProps) => {
  const [view, setView] = useState<View>('active');
  const [regions, setRegions] = useState<EconRegionItem[]>([]);
  const [groups, setGroups] = useState<EconGoodsGroup[]>([]);
  const [regionTemplates, setRegionTemplates] = useState<EconRegionTemplate[]>([]);
  const [templates, setTemplates] = useState<EconEventTemplate[] | null>(null);
  const [templatesError, setTemplatesError] = useState<string | null>(null);

  const reloadTemplates = useCallback(() => {
    fetchEconomyEventTemplates()
      .then((list) => {
        setTemplates(list);
        setTemplatesError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить шаблоны событий');
        setTemplatesError(msg);
        toast.error(msg);
      });
  }, []);

  useEffect(() => {
    reloadTemplates();
    fetchEconomyRegions()
      .then((list) => setRegions([...list].sort((a, b) => (a.name ?? '').localeCompare(b.name ?? '', 'ru'))))
      .catch((e) => toast.error(apiErrorMessage(e, 'Не удалось загрузить регионы')));
    fetchEconomyGoodsGroups()
      .then((list) => setGroups([...list].sort((a, b) => a.sort_order - b.sort_order)))
      .catch((e) => toast.error(apiErrorMessage(e, 'Не удалось загрузить группы товаров')));
    fetchEconomyTemplates()
      .then((list) => setRegionTemplates([...list].sort((a, b) => a.sort_order - b.sort_order)))
      .catch((e) => toast.error(apiErrorMessage(e, 'Не удалось загрузить шаблоны регионов')));
  }, [reloadTemplates]);

  const ctx: Ctx = useMemo(
    () => ({
      regions,
      regionNames: Object.fromEntries(regions.map((r) => [r.region_id, r.name ?? `Регион #${r.region_id}`])),
      groups,
      groupNames: Object.fromEntries(groups.map((g) => [g.code, g.name])),
      regionTemplates,
      templates,
      templatesError,
      reloadTemplates,
      canSettings,
    }),
    [regions, groups, regionTemplates, templates, templatesError, reloadTemplates, canSettings],
  );

  const views: View[] = canSettings ? ['active', 'start', 'templates', 'history'] : ['active', 'templates', 'history'];
  const current = views.includes(view) ? view : 'active';

  return (
    <div className="flex flex-col gap-5">
      <div className="flex gap-2 overflow-x-auto gold-scrollbar pb-1">
        {views.map((v) => (
          <button
            key={v}
            type="button"
            aria-pressed={current === v}
            onClick={() => setView(v)}
            className={`chip-outline rounded-full px-4 py-1.5 text-xs font-medium whitespace-nowrap ${current === v ? 'chip-outline-active' : ''}`}
          >
            {VIEW_LABEL[v]}
          </button>
        ))}
      </div>
      {current === 'active' && <ActiveView ctx={ctx} />}
      {current === 'start' && <StartView ctx={ctx} />}
      {current === 'templates' && <TemplatesView ctx={ctx} />}
      {current === 'history' && <HistoryView ctx={ctx} />}
    </div>
  );
};

export default EconomyEvents;
