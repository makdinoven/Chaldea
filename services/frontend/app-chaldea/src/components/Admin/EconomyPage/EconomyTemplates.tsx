import { useCallback, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { ArrowLeft, ChevronRight, RefreshCw } from 'lucide-react';
import { fetchEconomyGoodsGroups, fetchEconomyTemplates, putEconomyTemplate } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { useAppSelector } from '../../../redux/store';
import { selectPermissions } from '../../../redux/slices/userSlice';
import { hasPermission } from '../../../utils/permissions';
import type {
  EconGoodsGroup,
  EconNounGender,
  EconRegionTemplate,
  EconTemplateUpdate,
} from '../../../types/economy';
import { formatPercent } from './economyLabels';
import { Population, populationTitle } from './CompactValue';
import { compactNumber } from '../../../utils/compactNumber';
import { FieldHint } from './ParamHint';
import type { FieldHintKey } from './paramHints';

/* Bounds of `PUT /admin/economy/templates/{code}` (feature file 3.7; same limits as the region editor). */
const NAME_MAX = 100;
const DESCRIPTION_MAX = 500;
const NOUN_MAX = 50;
const MAX_POPULATION = 1_000_000_000;
const MAX_TAX_PERCENT = 50;
const MAX_PRODUCTION = 100_000;
const MAX_CONSUMPTION_MULT = 10;
/** How many specialty goods the list card shows. */
const TOP_GOODS = 3;

/** Food phrases of the player card by the settlement noun's gender (econ_sim). */
const FOOD_WORDS: Record<EconNounGender, [string, string, string]> = {
  m: ['сыт', 'недоедает', 'голодает'],
  f: ['сыта', 'недоедает', 'голодает'],
  n: ['сыто', 'недоедает', 'голодает'],
};

const GENDER_LABELS: Record<EconNounGender, string> = {
  m: 'Мужской («Регион сыт»)',
  f: 'Женский («Крепость сыта»)',
  n: 'Средний («Село сыто»)',
};

interface GoodsDraft {
  production: string;
  consumption: string;
}

interface Draft {
  name: string;
  description: string;
  noun: string;
  gender: EconNounGender;
  population: string;
  taxPercent: string;
  goods: Record<string, GoodsDraft>;
}

const toDraft = (t: EconRegionTemplate, groups: EconGoodsGroup[]): Draft => {
  const byCode = Object.fromEntries(t.goods.map((g) => [g.group_code, g]));
  return {
    name: t.name,
    description: t.description ?? '',
    noun: t.settlement_noun,
    gender: t.noun_gender,
    population: String(t.default_population),
    taxPercent: String(Math.round(t.tax_rate * 10000) / 100),
    // Every group gets a row: a template missing a group would otherwise be impossible to fill in.
    goods: Object.fromEntries(
      groups.map((g) => [
        g.code,
        {
          production: String(byCode[g.code]?.production_per_1000 ?? 0),
          consumption: String(byCode[g.code]?.consumption_mult ?? 1),
        },
      ]),
    ),
  };
};

const inRange = (text: string, min: number, max: number, integer = false): boolean => {
  if (text.trim() === '') return false;
  const n = Number(text);
  return Number.isFinite(n) && n >= min && n <= max && (!integer || Number.isInteger(n));
};

const textValid = (text: string, min: number, max: number) => {
  const t = text.trim();
  return t.length >= min && t.length <= max && !/[<>]/.test(t);
};

interface FieldLabelProps {
  htmlFor: string;
  children: string;
  /** «?» hint of the field (FEAT-185). */
  hint?: FieldHintKey;
  /** Hint title when the label is abbreviated. */
  hintTitle?: string;
}

const FieldLabel = ({ htmlFor, children, hint, hintTitle }: FieldLabelProps) => (
  <span className="flex items-center gap-1 min-w-0">
    <label htmlFor={htmlFor} className="text-white/60 text-xs uppercase tracking-[0.06em] truncate">
      {children}
    </label>
    {hint && <FieldHint field={hint} label={hintTitle ?? children} />}
  </span>
);

interface TemplateEditorProps {
  template: EconRegionTemplate;
  groups: EconGoodsGroup[];
  canEdit: boolean;
  onBack: () => void;
  onSaved: (t: EconRegionTemplate) => void;
}

const TemplateEditor = ({ template, groups, canEdit, onBack, onSaved }: TemplateEditorProps) => {
  const [draft, setDraft] = useState<Draft>(() => toDraft(template, groups));
  const [saving, setSaving] = useState(false);

  const nameValid = textValid(draft.name, 1, NAME_MAX);
  const descriptionValid = textValid(draft.description, 0, DESCRIPTION_MAX);
  const nounValid = textValid(draft.noun, 1, NOUN_MAX);
  const populationValid = inRange(draft.population, 0, MAX_POPULATION, true);
  const taxValid = inRange(draft.taxPercent, 0, MAX_TAX_PERCENT);
  const goodsErrors = groups.filter((g) => {
    const d = draft.goods[g.code];
    return !d || !inRange(d.production, 0, MAX_PRODUCTION) || !inRange(d.consumption, 0, MAX_CONSUMPTION_MULT);
  });
  const formValid = nameValid && descriptionValid && nounValid && populationValid && taxValid && goodsErrors.length === 0;

  const setGoods = (code: string, patch: Partial<GoodsDraft>) =>
    setDraft({ ...draft, goods: { ...draft.goods, [code]: { ...draft.goods[code], ...patch } } });

  const nounPreview = draft.noun.trim() || 'Регион';
  const words = FOOD_WORDS[draft.gender];

  const save = async () => {
    const description = draft.description.trim();
    const body: EconTemplateUpdate = {
      name: draft.name.trim(),
      description: description || null,
      settlement_noun: draft.noun.trim(),
      noun_gender: draft.gender,
      default_population: Number(draft.population),
      tax_rate: Math.round(Number(draft.taxPercent) * 100) / 10000,
      goods: groups.map((g) => ({
        group_code: g.code,
        production_per_1000: Number(draft.goods[g.code].production),
        consumption_mult: Number(draft.goods[g.code].consumption),
      })),
    };
    setSaving(true);
    try {
      const saved = await putEconomyTemplate(template.code, body);
      toast.success('Шаблон сохранён');
      onSaved(saved);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить шаблон'));
    } finally {
      setSaving(false);
    }
  };

  const numberInput = (
    id: string,
    value: string,
    onChange: (v: string) => void,
    valid: boolean,
    opts: { min: number; max: number; step: number },
  ) => (
    <input
      id={id}
      type="number"
      inputMode="decimal"
      min={opts.min}
      max={opts.max}
      step={opts.step}
      className={`input-underline w-full ${valid ? '' : '!border-site-red'}`}
      value={value}
      disabled={!canEdit}
      onChange={(e) => onChange(e.target.value)}
    />
  );

  return (
    <div className="flex flex-col gap-5">
      <button type="button" onClick={onBack} className="self-start text-white/60 hover:text-white text-sm flex items-center gap-1">
        <ArrowLeft size={15} />
        Все шаблоны
      </button>
      <div className="flex flex-col gap-0.5">
        <h2 className="gold-text text-xl sm:text-2xl font-semibold uppercase tracking-[0.06em] break-words">{template.name}</h2>
        <p className="text-white/40 text-xs">код {template.code}</p>
      </div>

      <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-5 min-w-0">
        <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Основное</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div className="flex flex-col gap-1 min-w-0">
            <FieldLabel htmlFor="econ-tpl-name">Название</FieldLabel>
            <input
              id="econ-tpl-name"
              type="text"
              maxLength={NAME_MAX}
              className={`input-underline w-full ${nameValid ? '' : '!border-site-red'}`}
              value={draft.name}
              disabled={!canEdit}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
            {!nameValid && <p className="text-site-red text-xs">От 1 до {NAME_MAX} символов, без «&lt;» и «&gt;»</p>}
          </div>
          <div className="grid grid-cols-2 gap-5">
            <div className="flex flex-col gap-1 min-w-0">
              <FieldLabel htmlFor="econ-tpl-population" hint="template_population">Население</FieldLabel>
              {numberInput('econ-tpl-population', draft.population, (v) => setDraft({ ...draft, population: v }), populationValid,
                { min: 0, max: MAX_POPULATION, step: 100 })}
              {populationValid ? (
                draft.population.trim() !== '' && (
                  <p className="text-white/40 text-xs break-words" title={populationTitle(Number(draft.population))}>
                    {compactNumber(Number(draft.population))} жит.
                  </p>
                )
              ) : (
                <p className="text-site-red text-xs">Целое от 0 до 1 000 000 000</p>
              )}
            </div>
            <div className="flex flex-col gap-1 min-w-0">
              <FieldLabel htmlFor="econ-tpl-tax" hint="template_tax" hintTitle="Налог с жителей">Налог, %</FieldLabel>
              {numberInput('econ-tpl-tax', draft.taxPercent, (v) => setDraft({ ...draft, taxPercent: v }), taxValid,
                { min: 0, max: MAX_TAX_PERCENT, step: 0.5 })}
              {!taxValid && <p className="text-site-red text-xs">От 0 до {MAX_TAX_PERCENT}%</p>}
            </div>
          </div>
          <div className="flex flex-col gap-1 min-w-0 sm:col-span-2">
            <FieldLabel htmlFor="econ-tpl-description">Описание</FieldLabel>
            <textarea
              id="econ-tpl-description"
              rows={3}
              maxLength={DESCRIPTION_MAX}
              className={`textarea-bordered w-full ${descriptionValid ? '' : '!border-site-red'}`}
              value={draft.description}
              disabled={!canEdit}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            />
            <p className={`text-xs ${descriptionValid ? 'text-white/40' : 'text-site-red'}`}>
              {descriptionValid ? `${draft.description.trim().length} / ${DESCRIPTION_MAX}` : `До ${DESCRIPTION_MAX} символов, без «<» и «>»`}
            </p>
          </div>
        </div>
      </section>

      <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
        <div className="flex flex-col gap-1">
          <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Поселение на карточке</h3>
          <p className="text-white/50 text-sm">Слово и его род нужны для фраз, которые видят игроки в карточке региона.</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div className="flex flex-col gap-1 min-w-0">
            <FieldLabel htmlFor="econ-tpl-noun">Слово</FieldLabel>
            <input
              id="econ-tpl-noun"
              type="text"
              maxLength={NOUN_MAX}
              placeholder="Регион, Край, Округа..."
              className={`input-underline w-full ${nounValid ? '' : '!border-site-red'}`}
              value={draft.noun}
              disabled={!canEdit}
              onChange={(e) => setDraft({ ...draft, noun: e.target.value })}
            />
            {!nounValid && <p className="text-site-red text-xs">От 1 до {NOUN_MAX} символов, без «&lt;» и «&gt;»</p>}
          </div>
          <div className="flex flex-col gap-1 min-w-0">
            <FieldLabel htmlFor="econ-tpl-gender">Род</FieldLabel>
            <select
              id="econ-tpl-gender"
              className="input-underline w-full"
              value={draft.gender}
              disabled={!canEdit}
              onChange={(e) => setDraft({ ...draft, gender: e.target.value as EconNounGender })}
            >
              {(Object.keys(GENDER_LABELS) as EconNounGender[]).map((g) => (
                <option key={g} value={g} className="bg-site-dark text-white">
                  {GENDER_LABELS[g]}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="text-white/40 uppercase tracking-[0.06em] self-center">Как увидят игроки:</span>
          <span className="rounded-full border border-stat-energy/40 bg-stat-energy/10 px-2.5 py-0.5 text-stat-energy break-words">
            {nounPreview} {words[0]}
          </span>
          <span className="rounded-full border border-gold/50 bg-gold/10 px-2.5 py-0.5 text-gold break-words">
            {nounPreview} {words[1]}
          </span>
          <span className="rounded-full border border-site-red/50 bg-site-red/10 px-2.5 py-0.5 text-site-red break-words">
            {nounPreview} {words[2]}
          </span>
        </div>
      </section>

      <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-3 min-w-0">
        <div className="flex flex-col gap-1">
          <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Товары</h3>
          <p className="text-white/50 text-sm">
            Производство — единиц в сутки на 1000 жителей при полной стабильности; потребление — множитель к норме
            группы. Изменения шаблона не трогают уже заполненные регионы, пока для них не нажата «Применить шаблон».
          </p>
        </div>
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3">
          {groups.map((g) => {
            const d = draft.goods[g.code];
            const prodOk = inRange(d.production, 0, MAX_PRODUCTION);
            const consOk = inRange(d.consumption, 0, MAX_CONSUMPTION_MULT);
            return (
              <li key={g.code} className="grid grid-cols-[minmax(0,1fr)_6.5rem_5rem] items-end gap-3 border-b border-white/[0.07] pb-2">
                <span className="text-white text-sm break-words pb-1.5">{g.name}</span>
                <div className="flex flex-col gap-1 min-w-0">
                  <FieldLabel htmlFor={`econ-tpl-${g.code}-prod`} hint="template_production" hintTitle="Производство на 1000 жителей">
                    Произв.
                  </FieldLabel>
                  {numberInput(`econ-tpl-${g.code}-prod`, d.production, (v) => setGoods(g.code, { production: v }), prodOk,
                    { min: 0, max: MAX_PRODUCTION, step: 1 })}
                </div>
                <div className="flex flex-col gap-1 min-w-0">
                  <FieldLabel htmlFor={`econ-tpl-${g.code}-cons`} hint="template_consumption" hintTitle="Множитель потребления">
                    Потр. ×
                  </FieldLabel>
                  {numberInput(`econ-tpl-${g.code}-cons`, d.consumption, (v) => setGoods(g.code, { consumption: v }), consOk,
                    { min: 0, max: MAX_CONSUMPTION_MULT, step: 0.1 })}
                </div>
              </li>
            );
          })}
        </ul>
        {goodsErrors.length > 0 && (
          <p className="text-site-red text-xs">
            Проверьте значения: производство 0–{MAX_PRODUCTION.toLocaleString('ru-RU')}, потребление 0–{MAX_CONSUMPTION_MULT}.
          </p>
        )}
      </section>

      {canEdit ? (
        <button type="button" className="btn-blue w-full sm:w-auto sm:self-start !px-6" disabled={!formValid || saving} onClick={save}>
          {saving ? 'Сохранение...' : 'Сохранить'}
        </button>
      ) : (
        <p className="field-hint">Изменять шаблоны может только администратор с правом «economy:settings».</p>
      )}
    </div>
  );
};

/** «Шаблоны» (FEAT-182): region templates — settlement noun, default population, tax, 12 goods. */
const EconomyTemplates = () => {
  const canEdit = hasPermission(useAppSelector(selectPermissions), 'economy:settings');
  const [templates, setTemplates] = useState<EconRegionTemplate[] | null>(null);
  const [groups, setGroups] = useState<EconGoodsGroup[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([fetchEconomyTemplates(), fetchEconomyGoodsGroups()])
      .then(([tpl, grp]) => {
        setTemplates([...tpl].sort((a, b) => a.sort_order - b.sort_order));
        setGroups([...grp].sort((a, b) => a.sort_order - b.sort_order));
        setError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить шаблоны регионов');
        setError(msg);
        toast.error(msg);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const names = useMemo(() => Object.fromEntries((groups ?? []).map((g) => [g.code, g.name])), [groups]);
  const current = templates?.find((t) => t.code === selected);

  if (current && groups && templates) {
    return (
      <TemplateEditor
        key={current.code}
        template={current}
        groups={groups}
        canEdit={canEdit}
        onBack={() => setSelected(null)}
        onSaved={(saved) => {
          setTemplates(templates.map((t) => (t.code === saved.code ? { ...t, ...saved } : t)));
          setSelected(null);
        }}
      />
    );
  }

  const specialties = (t: EconRegionTemplate) =>
    [...t.goods]
      .filter((g) => g.production_per_1000 > 0)
      .sort((a, b) => b.production_per_1000 - a.production_per_1000)
      .slice(0, TOP_GOODS)
      .map((g) => names[g.group_code] ?? g.group_code);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col sm:flex-row sm:items-end gap-3">
        <p className="text-white/50 text-sm max-w-2xl">
          Шаблон — заготовка хозяйства региона: что он производит, сколько потребляет, какой налог и население по
          умолчанию. Регион получает значения шаблона при заполнении или кнопкой «Применить шаблон».
        </p>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="sm:ml-auto self-start inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-site-blue transition-colors duration-200 ease-site disabled:opacity-40"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Обновить
        </button>
      </div>
      {!canEdit && <p className="field-hint">Только просмотр: менять шаблоны может администратор с правом «economy:settings».</p>}

      {error && !templates && <p className="text-site-red text-sm">{error}</p>}
      {!templates && !error && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
      {templates && templates.length === 0 && <p className="text-white/40 text-sm italic">Шаблонов нет.</p>}

      {templates && templates.length > 0 && (
        <ul className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {templates.map((t) => {
            const top = specialties(t);
            return (
              <li key={t.code}>
                <button
                  type="button"
                  onClick={() => setSelected(t.code)}
                  className="w-full h-full text-left bg-site-bg rounded-card border border-white/[0.07] p-4 flex flex-col gap-2 hover:border-gold/40 transition-colors duration-200 ease-site"
                >
                  <span className="flex items-start gap-2">
                    <span className="flex-1 min-w-0 text-white font-medium break-words">{t.name}</span>
                    <ChevronRight size={16} className="text-gold shrink-0 mt-1" />
                  </span>
                  {t.description && <span className="text-white/50 text-xs break-words line-clamp-3">{t.description}</span>}
                  <span className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-white/50">
                    <span>
                      «<span className="text-white/80">{t.settlement_noun} {FOOD_WORDS[t.noun_gender]?.[0] ?? ''}</span>»
                    </span>
                    <span>
                      жителей <Population value={t.default_population} className="text-white/80" />
                    </span>
                    <span>
                      налог <span className="text-white/80">{formatPercent(t.tax_rate)}</span>
                    </span>
                  </span>
                  {top.length > 0 && (
                    <span className="flex flex-wrap gap-1.5">
                      {top.map((n) => (
                        <span key={n} className="rounded-full border border-gold/30 px-2 py-0.5 text-gold/90 text-[11px]">
                          {n}
                        </span>
                      ))}
                    </span>
                  )}
                  {t.goods.length > 0 && top.length === 0 && (
                    <span className="text-white/40 text-xs">Ничего не производит</span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

export default EconomyTemplates;
