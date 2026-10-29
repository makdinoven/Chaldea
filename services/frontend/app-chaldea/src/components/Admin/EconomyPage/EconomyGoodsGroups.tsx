import { useCallback, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { ArrowLeft, ChevronRight, Plus, RefreshCw, X } from 'lucide-react';
import { fetchEconomyGoodsGroups, putEconomyGoodsGroup } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { useCurrency } from '../../../hooks/useCurrency';
import { useAppSelector } from '../../../redux/store';
import { selectPermissions } from '../../../redux/slices/userSlice';
import { hasPermission } from '../../../utils/permissions';
import type { EconGoodsGroup, EconGoodsGroupUpdate } from '../../../types/economy';
import { formatDecimal } from './economyLabels';
import { FieldHint } from './ParamHint';
import type { FieldHintKey } from './paramHints';

/* Bounds of `PUT /admin/economy/goods-groups/{code}` (feature file 3.7). */
const NAME_MAX = 100;
const BASE_PRICE_MIN = 1;
const BASE_PRICE_MAX = 1_000_000;
const NORM_MAX = 100_000;
const NORM_DAYS_MIN = 0.5;
const NORM_DAYS_MAX = 365;
const ELASTICITY_MAX = 3;
const RATIO_MIN = 0.001;
const RATIO_MAX = 100;

interface InputDraft {
  code: string;
  ratio: string;
}

interface Draft {
  name: string;
  basePrice: string;
  norm: string;
  normDays: string;
  prosperityElasticity: string;
  priceElasticity: string;
  inputs: InputDraft[];
}

const toDraft = (g: EconGoodsGroup): Draft => ({
  name: g.name,
  basePrice: String(g.base_price),
  norm: String(g.norm_per_1000),
  normDays: String(g.norm_days),
  prosperityElasticity: String(g.prosperity_elasticity),
  priceElasticity: String(g.price_elasticity),
  inputs: g.inputs.map((i) => ({ code: i.input_code, ratio: String(i.ratio) })),
});

const inRange = (text: string, min: number, max: number, integer = false): boolean => {
  if (text.trim() === '') return false;
  const n = Number(text);
  return Number.isFinite(n) && n >= min && n <= max && (!integer || Number.isInteger(n));
};

/** True when `start` reaches `target` through the chain graph (group → its inputs). */
const reaches = (graph: Record<string, string[]>, start: string, target: string): boolean => {
  const seen = new Set<string>();
  const stack = [start];
  while (stack.length > 0) {
    const cur = stack.pop() as string;
    if (cur === target) return true;
    if (seen.has(cur)) continue;
    seen.add(cur);
    stack.push(...(graph[cur] ?? []));
  }
  return false;
};

/** «?» hints of the group editor fields (FEAT-185), by input id. */
const GROUP_FIELD_HINT: Record<string, FieldHintKey> = {
  'econ-gg-price': 'group_base_price',
  'econ-gg-norm': 'group_norm',
  'econ-gg-days': 'group_norm_days',
  'econ-gg-pe': 'group_prosperity_elasticity',
  'econ-gg-ce': 'group_price_elasticity',
};

const FieldLabel = ({ htmlFor, children, hint }: { htmlFor: string; children: string; hint?: FieldHintKey }) => (
  <span className="flex items-center gap-1 min-w-0">
    <label htmlFor={htmlFor} className="text-white/60 text-xs uppercase tracking-[0.06em]">
      {children}
    </label>
    {hint && <FieldHint field={hint} label={children} />}
  </span>
);

interface GroupEditorProps {
  group: EconGoodsGroup;
  groups: EconGoodsGroup[];
  canEdit: boolean;
  onBack: () => void;
  onSaved: (g: EconGoodsGroup) => void;
}

const GroupEditor = ({ group, groups, canEdit, onBack, onSaved }: GroupEditorProps) => {
  const [draft, setDraft] = useState<Draft>(() => toDraft(group));
  const [saving, setSaving] = useState(false);

  const names = useMemo(() => Object.fromEntries(groups.map((g) => [g.code, g.name])), [groups]);

  const trimmedName = draft.name.trim();
  const nameValid = trimmedName.length >= 1 && trimmedName.length <= NAME_MAX && !/[<>]/.test(trimmedName);
  const basePriceValid = inRange(draft.basePrice, BASE_PRICE_MIN, BASE_PRICE_MAX, true);
  const normValid = inRange(draft.norm, 0, NORM_MAX);
  const normDaysValid = inRange(draft.normDays, NORM_DAYS_MIN, NORM_DAYS_MAX);
  const prospValid = inRange(draft.prosperityElasticity, 0, ELASTICITY_MAX);
  const priceElValid = inRange(draft.priceElasticity, 0, ELASTICITY_MAX);

  const inputCodes = draft.inputs.map((i) => i.code);
  const duplicateInputs = inputCodes.length !== new Set(inputCodes).size;
  const ratiosValid = draft.inputs.every((i) => inRange(i.ratio, RATIO_MIN, RATIO_MAX));
  const emptyInput = draft.inputs.some((i) => !i.code);

  // A chain may not loop back to this group: e.g. tools ← ore_metal ← tools.
  const cycleInputs = useMemo(() => {
    const graph: Record<string, string[]> = Object.fromEntries(
      groups.map((g) => [g.code, g.inputs.map((i) => i.input_code)]),
    );
    const codes = draft.inputs.map((i) => i.code).filter(Boolean);
    graph[group.code] = codes;
    return codes.filter((c) => reaches(graph, c, group.code));
  }, [groups, group.code, draft.inputs]);

  const formValid =
    nameValid &&
    basePriceValid &&
    normValid &&
    normDaysValid &&
    prospValid &&
    priceElValid &&
    ratiosValid &&
    !duplicateInputs &&
    !emptyInput &&
    cycleInputs.length === 0;

  const availableFor = (current: string) =>
    groups.filter((g) => g.code !== group.code && (g.code === current || !inputCodes.includes(g.code)));

  const setInput = (idx: number, patch: Partial<InputDraft>) =>
    setDraft({ ...draft, inputs: draft.inputs.map((i, n) => (n === idx ? { ...i, ...patch } : i)) });

  const addInput = () => {
    const free = availableFor('')[0];
    setDraft({ ...draft, inputs: [...draft.inputs, { code: free?.code ?? '', ratio: '1' }] });
  };

  const save = async () => {
    const body: EconGoodsGroupUpdate = {
      name: trimmedName,
      base_price: Number(draft.basePrice),
      norm_per_1000: Number(draft.norm),
      norm_days: Number(draft.normDays),
      prosperity_elasticity: Number(draft.prosperityElasticity),
      price_elasticity: Number(draft.priceElasticity),
      inputs: draft.inputs.map((i) => ({ input_code: i.code, ratio: Number(i.ratio) })),
    };
    setSaving(true);
    try {
      const saved = await putEconomyGoodsGroup(group.code, body);
      toast.success('Группа товаров сохранена');
      onSaved(saved);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить группу товаров'));
    } finally {
      setSaving(false);
    }
  };

  const numberField = (
    id: string,
    label: string,
    value: string,
    onChange: (v: string) => void,
    valid: boolean,
    hint: string,
    error: string,
    opts: { min: number; max: number; step: number },
  ) => (
    <div className="flex flex-col gap-1 min-w-0">
      <FieldLabel htmlFor={id} hint={GROUP_FIELD_HINT[id]}>
        {label}
      </FieldLabel>
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
      {valid ? <p className="text-white/40 text-xs">{hint}</p> : <p className="text-site-red text-xs">{error}</p>}
    </div>
  );

  return (
    <div className="flex flex-col gap-5">
      <button type="button" onClick={onBack} className="self-start text-white/60 hover:text-white text-sm flex items-center gap-1">
        <ArrowLeft size={15} />
        Все группы
      </button>
      <div className="flex flex-col gap-0.5">
        <h2 className="gold-text text-xl sm:text-2xl font-semibold uppercase tracking-[0.06em] break-words">{group.name}</h2>
        <p className="text-white/40 text-xs">
          код {group.code}
          {group.is_food && ' · продовольствие (голод считается по этой группе)'}
        </p>
      </div>

      <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-5 min-w-0">
        <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Параметры</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          <div className="flex flex-col gap-1 min-w-0">
            <FieldLabel htmlFor="econ-gg-name">Название</FieldLabel>
            <input
              id="econ-gg-name"
              type="text"
              maxLength={NAME_MAX}
              className={`input-underline w-full ${nameValid ? '' : '!border-site-red'}`}
              value={draft.name}
              disabled={!canEdit}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
            {!nameValid && <p className="text-site-red text-xs">От 1 до {NAME_MAX} символов, без «&lt;» и «&gt;»</p>}
          </div>
          {numberField('econ-gg-price', 'Базовая цена', draft.basePrice, (v) => setDraft({ ...draft, basePrice: v }),
            basePriceValid, 'За единицу; цена предмета без своей цены', `Целое от ${BASE_PRICE_MIN} до ${BASE_PRICE_MAX.toLocaleString('ru-RU')}`,
            { min: BASE_PRICE_MIN, max: BASE_PRICE_MAX, step: 1 })}
          {numberField('econ-gg-norm', 'Потребление на 1000', draft.norm, (v) => setDraft({ ...draft, norm: v }),
            normValid, 'Единиц в сутки на 1000 жителей', `От 0 до ${NORM_MAX.toLocaleString('ru-RU')}`,
            { min: 0, max: NORM_MAX, step: 0.1 })}
          {numberField('econ-gg-days', 'Норма запаса, дней', draft.normDays, (v) => setDraft({ ...draft, normDays: v }),
            normDaysValid, 'Запас «в норме» = столько дней потребления', `От ${formatDecimal(NORM_DAYS_MIN, 1)} до ${NORM_DAYS_MAX}`,
            { min: NORM_DAYS_MIN, max: NORM_DAYS_MAX, step: 0.5 })}
          {numberField('econ-gg-pe', 'Эластичность по достатку', draft.prosperityElasticity,
            (v) => setDraft({ ...draft, prosperityElasticity: v }), prospValid,
            'Насколько спрос растёт у зажиточных', `От 0 до ${ELASTICITY_MAX}`, { min: 0, max: ELASTICITY_MAX, step: 0.05 })}
          {numberField('econ-gg-ce', 'Эластичность по цене', draft.priceElasticity,
            (v) => setDraft({ ...draft, priceElasticity: v }), priceElValid,
            'Насколько спрос падает при дорогих ценах', `От 0 до ${ELASTICITY_MAX}`, { min: 0, max: ELASTICITY_MAX, step: 0.05 })}
        </div>
      </section>

      <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
        <div className="flex flex-col gap-1">
          <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Цепочка производства</h3>
          <p className="text-white/50 text-sm">
            Сырьё, которое нужно на 1 единицу этой группы. Если сырья в регионе мало, производство падает.
          </p>
        </div>
        {draft.inputs.length === 0 && <p className="text-white/40 text-sm italic">Сырьё не требуется.</p>}
        <ul className="flex flex-col gap-3">
          {draft.inputs.map((inp, idx) => {
            const ratioOk = inRange(inp.ratio, RATIO_MIN, RATIO_MAX);
            const loops = cycleInputs.includes(inp.code);
            return (
              <li key={idx} className="flex flex-col sm:flex-row sm:items-end gap-3 min-w-0">
                <div className="flex flex-col gap-1 min-w-0 sm:flex-1">
                  <FieldLabel htmlFor={`econ-gg-in-${idx}`}>Сырьё</FieldLabel>
                  <select
                    id={`econ-gg-in-${idx}`}
                    className={`input-underline w-full ${inp.code && !loops ? '' : '!border-site-red'}`}
                    value={inp.code}
                    disabled={!canEdit}
                    onChange={(e) => setInput(idx, { code: e.target.value })}
                  >
                    <option value="" className="bg-site-dark text-white">— выберите —</option>
                    {availableFor(inp.code).map((g) => (
                      <option key={g.code} value={g.code} className="bg-site-dark text-white">
                        {g.name}
                      </option>
                    ))}
                  </select>
                  {loops && <p className="text-site-red text-xs">Цепочка замыкается на «{group.name}»</p>}
                </div>
                <div className="flex items-end gap-3">
                  <div className="flex flex-col gap-1 min-w-0 w-32">
                    <FieldLabel htmlFor={`econ-gg-ratio-${idx}`} hint="group_input_ratio">
                      Ед. на 1
                    </FieldLabel>
                    <input
                      id={`econ-gg-ratio-${idx}`}
                      type="number"
                      inputMode="decimal"
                      min={RATIO_MIN}
                      max={RATIO_MAX}
                      step={0.1}
                      className={`input-underline w-full ${ratioOk ? '' : '!border-site-red'}`}
                      value={inp.ratio}
                      disabled={!canEdit}
                      onChange={(e) => setInput(idx, { ratio: e.target.value })}
                    />
                  </div>
                  {canEdit && (
                    <button
                      type="button"
                      aria-label="Убрать сырьё"
                      title="Убрать сырьё"
                      onClick={() => setDraft({ ...draft, inputs: draft.inputs.filter((_, n) => n !== idx) })}
                      className="p-2 text-white/50 hover:text-site-red transition-colors duration-200 ease-site"
                    >
                      <X size={16} />
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
        {!ratiosValid && (
          <p className="text-site-red text-xs">
            Количество сырья — от {formatDecimal(RATIO_MIN, 3)} до {RATIO_MAX}
          </p>
        )}
        {duplicateInputs && <p className="text-site-red text-xs">Одно и то же сырьё указано дважды</p>}
        {canEdit && availableFor('').length > 0 && (
          <button
            type="button"
            onClick={addInput}
            className="self-start inline-flex items-center gap-1.5 text-sm text-site-blue hover:text-white transition-colors duration-200 ease-site"
          >
            <Plus size={15} />
            Добавить сырьё
          </button>
        )}
        {draft.inputs.length > 0 && (
          <p className="text-white/40 text-xs break-words">
            Сейчас: 1 «{trimmedName || group.name}» ={' '}
            {draft.inputs
              .filter((i) => i.code)
              .map((i) => `${formatDecimal(Number(i.ratio) || 0, 3)} «${names[i.code] ?? i.code}»`)
              .join(' + ')}
          </p>
        )}
      </section>

      {canEdit ? (
        <button type="button" className="btn-blue w-full sm:w-auto sm:self-start !px-6" disabled={!formValid || saving} onClick={save}>
          {saving ? 'Сохранение...' : 'Сохранить'}
        </button>
      ) : (
        <p className="field-hint">Изменять группы товаров может только администратор с правом «economy:settings».</p>
      )}
    </div>
  );
};

/** «Товары» (FEAT-182): the 12 goods groups — base price, household norms, elasticities, production chains. */
const EconomyGoodsGroups = () => {
  const canEdit = hasPermission(useAppSelector(selectPermissions), 'economy:settings');
  const { format } = useCurrency();
  const [groups, setGroups] = useState<EconGoodsGroup[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    fetchEconomyGoodsGroups()
      .then((list) => {
        setGroups([...list].sort((a, b) => a.sort_order - b.sort_order));
        setError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить группы товаров');
        setError(msg);
        toast.error(msg);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const names = useMemo(() => Object.fromEntries((groups ?? []).map((g) => [g.code, g.name])), [groups]);
  const current = groups?.find((g) => g.code === selected);

  if (current && groups) {
    return (
      <GroupEditor
        key={current.code}
        group={current}
        groups={groups}
        canEdit={canEdit}
        onBack={() => setSelected(null)}
        onSaved={(saved) => {
          setGroups(groups.map((g) => (g.code === saved.code ? { ...g, ...saved } : g)));
          setSelected(null);
        }}
      />
    );
  }

  const chain = (g: EconGoodsGroup) =>
    g.inputs.length === 0
      ? null
      : g.inputs.map((i) => `${names[i.input_code] ?? i.input_code} ×${formatDecimal(i.ratio, 3)}`).join(', ');

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col sm:flex-row sm:items-end gap-3">
        <p className="text-white/50 text-sm max-w-2xl">
          Двенадцать групп товаров, из которых складывается хозяйство регионов. Базовая цена — цена единицы до
          рыночного множителя; нормы задают, сколько жители потребляют и какой запас считается достаточным.
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
      {!canEdit && <p className="field-hint">Только просмотр: менять группы может администратор с правом «economy:settings».</p>}

      {error && !groups && <p className="text-site-red text-sm">{error}</p>}
      {!groups && !error && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}

      {groups && (
        <>
          {/* Table — lg and up */}
          <div className="hidden lg:block bg-site-bg rounded-card border border-white/[0.07] px-4 py-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-white/50 text-xs uppercase tracking-[0.06em] text-left border-b border-white/10">
                  <th className="py-2 pr-3 font-normal">Группа</th>
                  <th className="py-2 pr-3 font-normal text-right">Базовая цена</th>
                  <th className="py-2 pr-3 font-normal text-right">Потр./1000</th>
                  <th className="py-2 pr-3 font-normal text-right">Запас, дней</th>
                  <th className="py-2 pr-3 font-normal text-right">Эл. достатка</th>
                  <th className="py-2 pr-3 font-normal text-right">Эл. цены</th>
                  <th className="py-2 font-normal">Сырьё</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((g) => (
                  <tr
                    key={g.code}
                    onClick={() => setSelected(g.code)}
                    className="border-b border-white/[0.07] last:border-b-0 cursor-pointer hover:bg-white/[0.04] transition-colors duration-200 ease-site"
                  >
                    <td className="py-2 pr-3 text-white">
                      {g.name}
                      {g.is_food && <span className="ml-2 text-stat-energy text-xs">еда</span>}
                    </td>
                    <td className="py-2 pr-3 text-right text-white/80 whitespace-nowrap">{format(g.base_price)}</td>
                    <td className="py-2 pr-3 text-right text-white/80">{formatDecimal(g.norm_per_1000, 3)}</td>
                    <td className="py-2 pr-3 text-right text-white/80">{formatDecimal(g.norm_days, 2)}</td>
                    <td className="py-2 pr-3 text-right text-white/80">{formatDecimal(g.prosperity_elasticity, 3)}</td>
                    <td className="py-2 pr-3 text-right text-white/80">{formatDecimal(g.price_elasticity, 3)}</td>
                    <td className="py-2 text-white/60 text-xs">{chain(g) ?? <span className="text-white/30">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Cards — below lg */}
          <ul className="lg:hidden grid grid-cols-1 md:grid-cols-2 gap-3">
            {groups.map((g) => (
              <li key={g.code}>
                <button
                  type="button"
                  onClick={() => setSelected(g.code)}
                  className="w-full text-left bg-site-bg rounded-card border border-white/[0.07] p-3 flex flex-col gap-2 hover:border-gold/40 transition-colors duration-200 ease-site"
                >
                  <span className="flex items-start gap-2">
                    <span className="flex-1 min-w-0 text-white text-sm font-medium break-words">
                      {g.name}
                      {g.is_food && <span className="ml-2 text-stat-energy text-xs font-normal">еда</span>}
                    </span>
                    <span className="text-white/80 text-sm whitespace-nowrap">{format(g.base_price)}</span>
                    <ChevronRight size={16} className="text-gold shrink-0 mt-0.5" />
                  </span>
                  <span className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-white/50">
                    <span>
                      потр./1000 <span className="text-white/80">{formatDecimal(g.norm_per_1000, 3)}</span>
                    </span>
                    <span>
                      запас <span className="text-white/80">{formatDecimal(g.norm_days, 2)} дн.</span>
                    </span>
                    <span>
                      эл. <span className="text-white/80">{formatDecimal(g.prosperity_elasticity, 2)} / {formatDecimal(g.price_elasticity, 2)}</span>
                    </span>
                  </span>
                  {chain(g) && <span className="text-white/50 text-xs break-words">Сырьё: {chain(g)}</span>}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
};

export default EconomyGoodsGroups;
