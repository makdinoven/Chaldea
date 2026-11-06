// FEAT-206 — «Экономика» of one faction (admin): treasury and wealth numbers, the last tick's inflow /
// outflow, template + overrides, conditional members, «Заполнить по шаблону» (factions:economy + economy:emit),
// quartermasters, the assortment, debts, purchases, tick history and the treasury's ledger operations.
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import toast from 'react-hot-toast';
import { AlertTriangle } from 'lucide-react';
import {
  FACTION_ECON_PARAM_SPECS,
  FACTION_FILL_COMMENT_MAX,
  FACTION_FILL_COMMENT_MIN,
  FACTION_MEMBERS_MAX,
  FACTION_PROFILE_KINDS,
  FACTION_PROFILE_KIND_LABEL,
  FACTION_QUARTERMASTERS_MAX,
  adminFactionEconomy,
  adminFactionQuartermasters,
  adminFillFactionEconomy,
  adminListEconTemplates,
  adminPutFactionEconomy,
  adminSetFactionQuartermasters,
  type FactionEconParams,
  type FactionEconTemplate,
  type FactionEconomyAdmin,
  type FactionQuartermasterAdmin,
  type FactionRankAdmin,
} from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import { NPC_ROLE_LABELS } from '../../../constants/npc';
import { useCurrency } from '../../../hooks/useCurrency';
import { selectPermissions } from '../../../redux/slices/userSlice';
import { useAppSelector } from '../../../redux/store';
import { hasPermission } from '../../../utils/permissions';
import ConfirmDialog from '../../pages/LocationPage/ConfirmDialog';
import { EntityListPicker } from '../DungeonsPage/editor/pickers';
import { formatDateTime } from '../EconomyPage/economyLabels';
import { FIELD, INT_RE, LABEL, OPTION, toInt } from './adminShared';
import {
  FactionDebtsList,
  FactionEconHistoryList,
  FactionOperationsList,
  FactionPurchasesList,
} from './FactionEconLists';
import QmAssortmentEditor from './QmAssortmentEditor';

interface FactionEconomyPanelProps {
  factionId: number;
  isSecret: boolean;
  ranks: FactionRankAdmin[];
}

const SECTION = 'gray-bg p-4 sm:p-6 flex flex-col gap-4 min-w-0';
const H3 = 'gold-text text-lg font-medium uppercase tracking-[0.06em]';
const DEC_RE = /^\d*([.,]\d{0,6})?$/;

const Stat = ({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: string; tone?: string }) => (
  <div className="flex flex-col gap-0.5 bg-white/[0.03] rounded-card p-3 min-w-0">
    <span className="text-white/50 text-[11px] uppercase tracking-[0.06em]">{label}</span>
    <span className={`text-sm sm:text-base font-medium break-words ${tone ?? 'text-white'}`}>{value}</span>
    {hint && <span className="text-white/40 text-xs break-words">{hint}</span>}
  </div>
);

interface SettingsForm {
  template_code: string;
  overrides: Record<string, string>;
  econ_enabled: boolean;
  members_count: string;
  members_min: string;
  members_max: string;
}

const settingsOf = (e: FactionEconomyAdmin): SettingsForm => ({
  template_code: e.template_code ?? '',
  overrides: Object.fromEntries(Object.entries(e.overrides ?? {}).map(([k, v]) => [k, String(v)])),
  econ_enabled: e.econ_enabled,
  members_count: String(e.members_count),
  members_min: String(e.members_min),
  members_max: String(e.members_max),
});

/** Override inputs → the request map (empty = inherit from the template); a toast + null on a bad value. */
const overridesBody = (raw: Record<string, string>): FactionEconParams | null | false => {
  const out: FactionEconParams = {};
  for (const spec of FACTION_ECON_PARAM_SPECS) {
    const v = (raw[spec.key] ?? '').trim();
    if (!v) continue;
    if (spec.kind === 'kind') {
      out[spec.key] = v;
      continue;
    }
    const n = Number(v.replace(',', '.'));
    const bad = !Number.isFinite(n) || (spec.kind === 'int' && !Number.isInteger(n)) || n < (spec.min ?? 0) || n > (spec.max ?? Infinity);
    if (bad) {
      toast.error(`${spec.label}: ${spec.kind === 'int' ? 'целое число ' : ''}от ${spec.min} до ${spec.max}`);
      return false;
    }
    out[spec.key] = spec.kind === 'int' ? n : v.replace(',', '.');
  }
  return Object.keys(out).length ? out : null;
};

const FactionEconomyPanel = ({ factionId, isSecret, ranks }: FactionEconomyPanelProps) => {
  const permissions = useAppSelector(selectPermissions);
  const canEconomy = hasPermission(permissions, 'factions:economy');
  const canFill = canEconomy && hasPermission(permissions, 'economy:emit');
  const { format } = useCurrency();

  const [econ, setEcon] = useState<FactionEconomyAdmin | null>(null);
  const [templates, setTemplates] = useState<FactionEconTemplate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<SettingsForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [fillComment, setFillComment] = useState('');
  const [fillMembers, setFillMembers] = useState(false);
  const [fillConfirm, setFillConfirm] = useState(false);
  const [filling, setFilling] = useState(false);
  const [qms, setQms] = useState<FactionQuartermasterAdmin[]>([]);
  const [qmIds, setQmIds] = useState<number[]>([]);
  const [qmSaving, setQmSaving] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [e, t, q] = await Promise.all([
        adminFactionEconomy(factionId),
        adminListEconTemplates(),
        adminFactionQuartermasters(factionId),
      ]);
      setEcon(e);
      setForm(settingsOf(e));
      setTemplates(t);
      setQms(q);
      setQmIds(q.map((x) => x.npc_id));
    } catch (err) {
      setError(apiErrorMessage(err, 'Не удалось загрузить экономику фракции'));
    }
  }, [factionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const refreshAll = () => {
    void load();
    setReloadKey((k) => k + 1);
  };

  const template = useMemo(() => templates.find((t) => t.code === form?.template_code) ?? null, [templates, form?.template_code]);

  if (error && !econ) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-site-red text-sm">{error}</p>
        <button type="button" className="btn-line !w-auto !text-xs !py-1 !px-3" onClick={() => void load()}>
          Повторить
        </button>
      </div>
    );
  }
  if (!econ || !form) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

  const set = <K extends keyof SettingsForm>(k: K, v: SettingsForm[K]) => setForm((f) => (f ? { ...f, [k]: v } : f));
  const setOverride = (key: string, value: string) =>
    setForm((f) => (f ? { ...f, overrides: { ...f.overrides, [key]: value } } : f));

  const save = async () => {
    const overrides = overridesBody(form.overrides);
    if (overrides === false) return;
    const count = toInt(form.members_count);
    const lo = toInt(form.members_min);
    const hi = toInt(form.members_max);
    if (count == null || lo == null || hi == null || [count, lo, hi].some((n) => n < 0 || n > FACTION_MEMBERS_MAX) || lo > hi) {
      toast.error(`Участники и границы: от 0 до ${FACTION_MEMBERS_MAX}, минимум не больше максимума`);
      return;
    }
    setSaving(true);
    try {
      const updated = await adminPutFactionEconomy(factionId, {
        template_code: form.template_code || null,
        overrides,
        econ_enabled: form.econ_enabled,
        members_count: count,
        members_min: lo,
        members_max: hi,
      });
      setEcon(updated);
      setForm(settingsOf(updated));
      toast.success('Экономика фракции сохранена');
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Не удалось сохранить экономику фракции'));
    } finally {
      setSaving(false);
    }
  };

  const fill = async () => {
    setFillConfirm(false);
    setFilling(true);
    try {
      const res = await adminFillFactionEconomy(factionId, { comment: fillComment.trim(), set_members: fillMembers });
      toast.success(
        res.emitted > 0
          ? `Казна пополнена на ${format(res.emitted)}; участников: ${res.members_count}`
          : `Казна уже не меньше стартовой — эмиссии не было; участников: ${res.members_count}`,
      );
      setFillComment('');
      refreshAll();
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Не удалось заполнить по шаблону'));
    } finally {
      setFilling(false);
    }
  };

  const saveQms = async () => {
    setQmSaving(true);
    try {
      const list = await adminSetFactionQuartermasters(factionId, qmIds);
      setQms(list);
      setQmIds(list.map((x) => x.npc_id));
      toast.success('Интенданты сохранены');
      void load();
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Не удалось сохранить интендантов'));
    } finally {
      setQmSaving(false);
    }
  };

  const fillValid =
    fillComment.trim().length >= FACTION_FILL_COMMENT_MIN && fillComment.trim().length <= FACTION_FILL_COMMENT_MAX;
  const itemSales = econ.last.item_sales ?? 0;
  const inflow = econ.last.dues + econ.last.profile + itemSales;
  const itemStock = econ.item_stock ?? [];
  const outflow = econ.last.wages_paid + econ.last.restock + econ.last.debts_paid;
  const qmDirty = JSON.stringify(qmIds) !== JSON.stringify(qms.map((q) => q.npc_id));
  const ro = !canEconomy;

  return (
    <div className="flex flex-col gap-5">
      {/* Overview */}
      <section className={SECTION}>
        <h3 className={H3}>Состояние</h3>
        {!econ.ticking && (
          <p className="rounded-card border border-gold/30 bg-gold/[0.06] px-3 py-2 text-sm text-white/80 flex items-start gap-2">
            <AlertTriangle size={16} className="text-gold shrink-0 mt-0.5" />
            <span>
              Фракция не участвует в пересчёте: {econ.not_ticking_reason ?? 'причина неизвестна'}. Пожертвования, покупки у
              интенданта и выплаты долгов работают.
            </span>
          </p>
        )}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          <Stat label="Казна" value={format(econ.treasury.balance)} tone="text-gold" />
          <Stat
            label="Богатство"
            value={econ.wealth == null ? '—' : `${econ.wealth} · ${econ.wealth_label ?? ''}`}
            hint={econ.norm == null ? 'нет шаблона' : `норма ${format(econ.norm)}`}
          />
          <Stat label="Участники" value={econ.members_count.toLocaleString('ru-RU')} hint={`границы ${econ.members_min}…${econ.members_max}`} />
          <Stat
            label="Долги игрокам"
            value={econ.debts.open_total > 0 ? format(econ.debts.open_total) : 'нет'}
            hint={econ.debts.open_count > 0 ? `записей: ${econ.debts.open_count}` : undefined}
            tone={econ.debts.open_total > 0 ? 'text-site-red' : 'text-white'}
          />
          <Stat
            label="Штаб"
            value={econ.hq ? econ.hq.location_name ?? `#${econ.hq.location_id}` : 'не задан'}
            hint={econ.hq ? `${econ.hq.region_name ?? 'вне края'}${econ.hq.simulated ? '' : ' · край не в экономике'}` : undefined}
          />
          <Stat label="Шаблон" value={econ.template_name ?? 'не выбран'} />
          <Stat
            label="Приток за пересчёт"
            value={<span className="text-stat-energy">+{format(inflow)}</span>}
            hint={`взносы ${format(econ.last.dues)}, профиль ${format(econ.last.profile)}${itemSales > 0 ? `, продажа предметов ${format(itemSales)}` : ''}`}
          />
          <Stat
            label="Отток за пересчёт"
            value={<span className="text-site-red">−{format(outflow)}</span>}
            hint={`жалованье ${format(econ.last.wages_paid)} из ${format(econ.last.wages_due)}, закупки ${format(econ.last.restock)}, долги ${format(econ.last.debts_paid)}`}
          />
        </div>
        <p className="text-white/40 text-xs">
          {econ.last.tick_at
            ? `Последний пересчёт: ${formatDateTime(econ.last.tick_at)} · участники ${econ.last.members_delta >= 0 ? '+' : ''}${econ.last.members_delta}`
            : 'Пересчётов ещё не было.'}{' '}
          Игроки видят богатство только словами.
        </p>
      </section>

      {/* Template, overrides, members */}
      <section className={SECTION}>
        <h3 className={H3}>Настройки экономики</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <label className="flex flex-col gap-1 min-w-0 sm:col-span-2">
            <span className={LABEL}>Шаблон</span>
            <select value={form.template_code} disabled={ro} onChange={(e) => set('template_code', e.target.value)} className={FIELD}>
              <option value="" className={OPTION}>
                — Без шаблона (экономика не идёт) —
              </option>
              {templates.map((t) => (
                <option key={t.code} value={t.code} className={OPTION}>
                  {t.name}
                </option>
              ))}
            </select>
            {template?.description && <span className="text-white/40 text-xs">{template.description}</span>}
          </label>
          <label className="flex flex-col gap-1 min-w-0">
            <span className={LABEL}>Участников сейчас</span>
            <input inputMode="numeric" value={form.members_count} disabled={ro} onChange={(e) => INT_RE.test(e.target.value) && set('members_count', e.target.value)} className={FIELD} />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1 min-w-0">
              <span className={LABEL}>Мин.</span>
              <input inputMode="numeric" value={form.members_min} disabled={ro} onChange={(e) => INT_RE.test(e.target.value) && set('members_min', e.target.value)} className={FIELD} />
            </label>
            <label className="flex flex-col gap-1 min-w-0">
              <span className={LABEL}>Макс.</span>
              <input inputMode="numeric" value={form.members_max} disabled={ro} onChange={(e) => INT_RE.test(e.target.value) && set('members_max', e.target.value)} className={FIELD} />
            </label>
          </div>
        </div>

        <label className="flex items-start gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={form.econ_enabled}
            disabled={ro}
            onChange={(e) => set('econ_enabled', e.target.checked)}
            className="w-4 h-4 mt-0.5 accent-gold shrink-0"
          />
          <span className="flex flex-col">
            <span className="text-white/85 text-sm">Фракция живёт в пересчёте</span>
            <span className="text-white/40 text-xs">Выключено — казна и участники заморожены (общий выключатель — во вкладке «Настройки»)</span>
          </span>
        </label>

        <div className="flex flex-col gap-2">
          <span className={LABEL}>Свои числа поверх шаблона (пусто — как в шаблоне)</span>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {FACTION_ECON_PARAM_SPECS.map((spec) => {
              const inherited = econ.params?.[spec.key] ?? template?.params?.[spec.key];
              const value = form.overrides[spec.key] ?? '';
              return (
                <label key={spec.key} className="flex flex-col gap-1 min-w-0">
                  <span className="text-white/70 text-xs">{spec.label}</span>
                  {spec.kind === 'kind' ? (
                    <select value={value} disabled={ro} onChange={(e) => setOverride(spec.key, e.target.value)} className={FIELD}>
                      <option value="" className={OPTION}>
                        как в шаблоне{template ? ` (${FACTION_PROFILE_KIND_LABEL[template.params.profile_kind as keyof typeof FACTION_PROFILE_KIND_LABEL] ?? template.params.profile_kind})` : ''}
                      </option>
                      {FACTION_PROFILE_KINDS.map((k) => (
                        <option key={k} value={k} className={OPTION}>
                          {FACTION_PROFILE_KIND_LABEL[k]}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      inputMode="decimal"
                      value={value}
                      disabled={ro}
                      placeholder={template && template.params[spec.key] != null ? String(template.params[spec.key]) : ''}
                      onChange={(e) => (spec.kind === 'int' ? INT_RE : DEC_RE).test(e.target.value) && setOverride(spec.key, e.target.value)}
                      className={FIELD}
                    />
                  )}
                  <span className="text-white/40 text-xs break-words">
                    {spec.hint}
                    {inherited != null && spec.kind !== 'kind' ? ` · сейчас ${inherited}` : ''}
                  </span>
                </label>
              );
            })}
          </div>
        </div>

        {canEconomy ? (
          <button type="button" onClick={() => void save()} disabled={saving} className="btn-blue !w-full sm:!w-auto !text-base !px-8 !py-2 self-start disabled:opacity-50">
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
        ) : (
          <p className="text-white/40 text-xs">Изменять экономику фракций можно с правом factions:economy.</p>
        )}
      </section>

      {/* Fill from template */}
      {canFill && (
        <section className={SECTION}>
          <h3 className={H3}>Заполнить по шаблону</h3>
          <p className="text-white/50 text-xs">
            Ставит число участников из шаблона (если отмечено или сейчас 0) и выпускает марки в казну до «участники × стартовая
            казна на участника». Это эмиссия — общая сумма денег в мире вырастет. Повторное нажатие без изменений ничего не
            выпустит.
          </p>
          <label className="flex flex-col gap-1">
            <span className={LABEL}>Комментарий (обязательно)</span>
            <input
              value={fillComment}
              maxLength={FACTION_FILL_COMMENT_MAX}
              onChange={(e) => setFillComment(e.target.value)}
              className={FIELD}
              placeholder="Стартовая казна фракции"
            />
          </label>
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input type="checkbox" checked={fillMembers} onChange={(e) => setFillMembers(e.target.checked)} className="w-4 h-4 accent-gold shrink-0" />
            <span className="text-white/85 text-sm">Поставить число участников из шаблона</span>
          </label>
          <button
            type="button"
            disabled={!fillValid || filling || !econ.template_code}
            onClick={() => setFillConfirm(true)}
            className="btn-blue !w-full sm:!w-auto !text-sm !px-6 self-start disabled:opacity-50"
          >
            {filling ? 'Заполнение...' : 'Заполнить'}
          </button>
          {!econ.template_code && <p className="text-white/40 text-xs">Сначала выберите и сохраните шаблон.</p>}
          {fillConfirm && (
            <ConfirmDialog
              title="Заполнить по шаблону"
              message={`Выпустить марки в казну фракции до стартового уровня шаблона «${econ.template_name ?? ''}»? Сейчас в казне ${format(econ.treasury.balance)}.`}
              confirmLabel="Заполнить"
              onConfirm={() => void fill()}
              onCancel={() => setFillConfirm(false)}
            />
          )}
        </section>
      )}

      {/* Quartermasters */}
      <section className={SECTION}>
        <h3 className={H3}>Интенданты</h3>
        <p className="text-white/40 text-xs">
          НПС, которые продают ассортимент фракции (до {FACTION_QUARTERMASTERS_MAX}). Кнопка «Интендант» появляется в профиле
          НПС. Роль НПС — только подпись: поставьте ему роль «Интендант» в редакторе НПС.
          {isSecret &&
            ' Фракция тайная: с ролью «Интендант» посторонние увидят кнопку и ответ «Этот человек с вами не разговаривает»; с другой ролью — не увидят кнопки вовсе.'}
        </p>
        {qms.length > 0 && (
          <div className="flex flex-col gap-1.5">
            {qms.map((q) => (
              <p key={q.npc_id} className="text-white/80 text-sm break-words">
                {q.name ?? `#${q.npc_id}`}
                <span className="text-white/45 text-xs">
                  {' '}
                  · {q.location_name ?? 'вне локаций'} · роль: {q.npc_role ? NPC_ROLE_LABELS[q.npc_role] ?? q.npc_role : 'нет'}
                  {q.npc_status === 'dead' ? ' · мёртв' : ''}
                </span>
                {q.npc_role !== 'quartermaster' && <span className="text-gold/80 text-xs"> · роль не «Интендант»</span>}
              </p>
            ))}
          </div>
        )}
        {canEconomy ? (
          <>
            <EntityListPicker kind="npc" ids={qmIds} onChange={(ids) => setQmIds(ids.slice(0, FACTION_QUARTERMASTERS_MAX))} />
            {qmDirty && (
              <button type="button" onClick={() => void saveQms()} disabled={qmSaving} className="btn-blue !w-full sm:!w-auto !text-sm !px-6 self-start disabled:opacity-50">
                {qmSaving ? 'Сохранение...' : 'Сохранить интендантов'}
              </button>
            )}
          </>
        ) : (
          qms.length === 0 && <p className="text-white/50 text-sm">Интендантов нет.</p>
        )}
      </section>

      {/* FEAT-207: donated items waiting for the tick sale */}
      <section className={SECTION}>
        <h3 className={H3}>Склад пожертвованных предметов</h3>
        <p className="text-white/40 text-xs">
          Предметы, которые сдали участники. В пересчёт они продаются на рынок края штаба (деньги — в казну из кошелька
          жителей), в пределах доли из настроек. Предметы, которые нельзя продать, остаются здесь.
          {itemSales > 0 ? ` Последний пересчёт: продано на ${format(itemSales)}.` : ''}
        </p>
        {itemStock.length === 0 ? (
          <p className="text-white/50 text-sm">Склад пуст.</p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {itemStock.map((row) => (
              <div key={row.item_id} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 bg-white/[0.03] rounded-card px-3 py-2 min-w-0">
                <span className="text-white/85 text-sm break-words min-w-0 flex-1">{row.name ?? `Предмет #${row.item_id}`}</span>
                <span className="text-white/60 text-xs font-mono tabular-nums">× {row.quantity.toLocaleString('ru-RU')}</span>
                <span className={`text-xs ${row.unit_value == null ? 'text-site-red' : 'text-white/50'}`}>
                  {row.unit_value == null
                    ? 'не продаётся в крае штаба'
                    : `${format(row.unit_value)} за шт. · всего ${format(row.unit_value * row.quantity)}`}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      <QmAssortmentEditor factionId={factionId} ranks={ranks} canEdit={canEconomy} />
      <FactionDebtsList factionId={factionId} reloadKey={reloadKey} />
      <FactionPurchasesList factionId={factionId} canAct={canEconomy} reloadKey={reloadKey} onChanged={() => void load()} />
      <FactionEconHistoryList factionId={factionId} reloadKey={reloadKey} />
      <FactionOperationsList factionId={factionId} reloadKey={reloadKey} />
    </div>
  );
};

export default FactionEconomyPanel;
