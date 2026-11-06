import { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { X } from 'lucide-react';
import {
  FACTION_CONDITION_LABEL,
  FACTION_CONDITION_TYPES,
  FACTION_LIMITS,
  adminSetConditions,
  type FactionConditionAdmin,
  type FactionConditionInput,
  type FactionConditionParams,
  type FactionConditionType,
} from '../../../api/factions';
import { FAME_TIER_CODES, INFAMY_TIER_CODES } from '../../../api/shadowAdmin';
import { fetchWorldGraph } from '../../../api/worldGraph';
import { fetchSubclasses, type Subclass } from '../../../api/subclasses';
import { apiErrorMessage } from '../../../api/errors';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { fetchRaces } from '../../../redux/slices/racesSlice';
import ReputationTierSelect from '../ReputationPage/ReputationTierSelect';
import { renownTierName, useFameTierOptions, useRenownTierNames } from '../ReputationPage/useShadowRefs';
import { FIELD, INT_RE, LABEL, NonRepeatableQuestSelect, OPTION, useFactionOptions } from './adminShared';

interface ConditionsEditorProps {
  factionId: number;
  conditions: FactionConditionAdmin[];
  canEdit: boolean;
  onSaved: () => void;
}

interface Block {
  key: number;
  type: FactionConditionType;
  params: FactionConditionParams;
}

const CLASS_OPTIONS = [
  { id: 1, name: 'Воин' },
  { id: 2, name: 'Плут' },
  { id: 3, name: 'Маг' },
];

const DEFAULT_PARAMS: Record<FactionConditionType, FactionConditionParams> = {
  region_reputation: { region_id: null, min_tier: null },
  fame: { min_tier: null, max_tier: null },
  infamy: { min_tier: null, max_tier: null },
  level: { min_level: 1 },
  class: { class_ids: [] },
  subclass: { subclass_keys: [] },
  race: { race_ids: [], subrace_ids: [] },
  quest: { quest_id: null },
  not_in_faction: { faction_id: null },
};

const ids = (v: unknown): number[] => (Array.isArray(v) ? v.map(Number).filter((n) => Number.isFinite(n)) : []);
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : []);
const numOrNull = (v: unknown): number | null => (v == null || v === '' ? null : Number(v));
const strOrNull = (v: unknown): string | null => (v == null || v === '' ? null : String(v));
const toggle = <T,>(list: T[], value: T): T[] => (list.includes(value) ? list.filter((x) => x !== value) : [...list, value]);

/** Strip empty optional keys; returns an error text for an incomplete block. */
const toInput = (b: Block): { input?: FactionConditionInput; error?: string } => {
  const p = b.params;
  const label = FACTION_CONDITION_LABEL[b.type];
  switch (b.type) {
    case 'region_reputation':
      if (!numOrNull(p.region_id) || !strOrNull(p.min_tier)) return { error: `${label}: выберите край и ступень` };
      return { input: { type: b.type, params: { region_id: numOrNull(p.region_id), min_tier: strOrNull(p.min_tier) } } };
    case 'fame':
    case 'infamy': {
      const out: FactionConditionParams = {};
      if (strOrNull(p.min_tier)) out.min_tier = strOrNull(p.min_tier);
      if (strOrNull(p.max_tier)) out.max_tier = strOrNull(p.max_tier);
      if (!out.min_tier && !out.max_tier) return { error: `${label}: укажите «не ниже» и/или «не выше»` };
      return { input: { type: b.type, params: out } };
    }
    case 'level': {
      const lvl = numOrNull(p.min_level);
      if (!lvl || lvl < 1 || lvl > FACTION_LIMITS.rankLevelMax) return { error: `${label}: от 1 до ${FACTION_LIMITS.rankLevelMax}` };
      return { input: { type: b.type, params: { min_level: lvl } } };
    }
    case 'class':
      if (ids(p.class_ids).length === 0) return { error: `${label}: отметьте хотя бы один класс` };
      return { input: { type: b.type, params: { class_ids: ids(p.class_ids) } } };
    case 'subclass':
      if (strs(p.subclass_keys).length === 0) return { error: `${label}: отметьте хотя бы один подкласс` };
      return { input: { type: b.type, params: { subclass_keys: strs(p.subclass_keys) } } };
    case 'race': {
      if (ids(p.race_ids).length === 0) return { error: `${label}: отметьте хотя бы одну расу` };
      const out: FactionConditionParams = { race_ids: ids(p.race_ids) };
      if (ids(p.subrace_ids).length > 0) out.subrace_ids = ids(p.subrace_ids);
      return { input: { type: b.type, params: out } };
    }
    case 'quest':
      if (!numOrNull(p.quest_id)) return { error: `${label}: выберите задание` };
      return { input: { type: b.type, params: { quest_id: numOrNull(p.quest_id) } } };
    case 'not_in_faction':
      if (!numOrNull(p.faction_id)) return { error: `${label}: выберите фракцию` };
      return { input: { type: b.type, params: { faction_id: numOrNull(p.faction_id) } } };
    default:
      return { error: 'Неизвестный тип условия' };
  }
};

const ChipCheck = ({ checked, label, onClick, disabled }: { checked: boolean; label: string; onClick: () => void; disabled: boolean }) => (
  <button
    type="button"
    disabled={disabled}
    onClick={onClick}
    className={`chip-outline rounded-full px-3 py-1 text-xs ${checked ? 'chip-outline-active' : ''} disabled:opacity-60`}
  >
    {label}
  </button>
);

/** Entry conditions — typed blocks, all must hold; saving replaces the whole list. */
const ConditionsEditor = ({ factionId, conditions, canEdit, onSaved }: ConditionsEditorProps) => {
  const dispatch = useAppDispatch();
  const races = useAppSelector((s) => s.races.races);
  const fameTiers = useFameTierOptions();
  const renownNames = useRenownTierNames();
  const { factions, error: factionsError } = useFactionOptions();
  const [regions, setRegions] = useState<{ id: number; name: string }[]>([]);
  const [subclasses, setSubclasses] = useState<Subclass[]>([]);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [saving, setSaving] = useState(false);
  const ro = !canEdit;

  useEffect(() => {
    setBlocks(conditions.map((c, i) => ({ key: i, type: c.type, params: { ...DEFAULT_PARAMS[c.type], ...c.params } })));
  }, [conditions]);

  useEffect(() => {
    if (races.length === 0) void dispatch(fetchRaces());
  }, [dispatch, races.length]);

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
    fetchSubclasses()
      .then((list) => !cancelled && setSubclasses(list))
      .catch((e: unknown) => !cancelled && toast.error(e instanceof Error ? e.message : 'Не удалось загрузить подклассы'));
    return () => {
      cancelled = true;
    };
  }, []);

  const infamyOptions = useMemo(
    () => INFAMY_TIER_CODES.map((code) => ({ code, name: renownTierName(renownNames, 'infamy', code) })),
    [renownNames],
  );
  const fameOptions = fameTiers.length ? fameTiers : FAME_TIER_CODES.map((code) => ({ code, name: code }));

  const update = (key: number, patch: FactionConditionParams) =>
    setBlocks((prev) => prev.map((b) => (b.key === key ? { ...b, params: { ...b.params, ...patch } } : b)));

  const add = () => {
    if (blocks.length >= FACTION_LIMITS.conditionsMax) {
      toast.error(`Условий — не больше ${FACTION_LIMITS.conditionsMax}`);
      return;
    }
    const key = blocks.reduce((m, b) => Math.max(m, b.key), -1) + 1;
    setBlocks((prev) => [...prev, { key, type: 'level', params: { ...DEFAULT_PARAMS.level } }]);
  };

  const save = async () => {
    const inputs: FactionConditionInput[] = [];
    for (const b of blocks) {
      const r = toInput(b);
      if (r.error) {
        toast.error(r.error);
        return;
      }
      if (r.input) inputs.push(r.input);
    }
    setSaving(true);
    try {
      await adminSetConditions(factionId, inputs);
      toast.success('Условия вступления сохранены');
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить условия'));
    } finally {
      setSaving(false);
    }
  };

  const tierRange = (b: Block, options: { code: string; name: string }[]) => (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {(['min_tier', 'max_tier'] as const).map((k) => (
        <label key={k} className="flex flex-col gap-1 min-w-0">
          <span className={LABEL}>{k === 'min_tier' ? 'Не ниже' : 'Не выше'}</span>
          <select
            value={strOrNull(b.params[k]) ?? ''}
            disabled={ro}
            onChange={(e) => update(b.key, { [k]: e.target.value || null })}
            className={FIELD}
          >
            <option value="" className={OPTION}>— не важно —</option>
            {options.map((o) => (
              <option key={o.code} value={o.code} className={OPTION}>
                {o.name}
              </option>
            ))}
          </select>
        </label>
      ))}
    </div>
  );

  const renderParams = (b: Block) => {
    const p = b.params;
    switch (b.type) {
      case 'region_reputation':
        return (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1 min-w-0">
              <span className={LABEL}>Край</span>
              <select value={numOrNull(p.region_id) ?? ''} disabled={ro} onChange={(e) => update(b.key, { region_id: e.target.value ? Number(e.target.value) : null })} className={FIELD}>
                <option value="" className={OPTION}>— выберите —</option>
                {regions.map((r) => (
                  <option key={r.id} value={r.id} className={OPTION}>
                    {r.name}
                  </option>
                ))}
              </select>
            </label>
            <ReputationTierSelect label="Не ниже ступени" value={strOrNull(p.min_tier)} disabled={ro} onChange={(code) => update(b.key, { min_tier: code })} />
          </div>
        );
      case 'fame':
        return tierRange(b, fameOptions);
      case 'infamy':
        return tierRange(b, infamyOptions);
      case 'level':
        return (
          <label className="flex flex-col gap-1 sm:max-w-[200px]">
            <span className={LABEL}>Уровень от</span>
            <input
              inputMode="numeric"
              value={p.min_level == null ? '' : String(p.min_level)}
              disabled={ro}
              onChange={(e) => INT_RE.test(e.target.value) && update(b.key, { min_level: e.target.value === '' ? null : Number(e.target.value) })}
              className={FIELD}
            />
          </label>
        );
      case 'class':
        return (
          <div className="flex flex-wrap gap-1.5">
            {CLASS_OPTIONS.map((c) => (
              <ChipCheck key={c.id} label={c.name} disabled={ro} checked={ids(p.class_ids).includes(c.id)} onClick={() => update(b.key, { class_ids: toggle(ids(p.class_ids), c.id) })} />
            ))}
          </div>
        );
      case 'subclass':
        return (
          <div className="flex flex-col gap-2">
            {CLASS_OPTIONS.map((c) => {
              const list = subclasses.filter((s) => s.class_id === c.id);
              if (list.length === 0) return null;
              return (
                <div key={c.id} className="flex flex-col gap-1">
                  <span className="text-white/40 text-xs">{c.name}</span>
                  <div className="flex flex-wrap gap-1.5">
                    {list.map((s) => (
                      <ChipCheck key={s.key} label={s.name} disabled={ro} checked={strs(p.subclass_keys).includes(s.key)} onClick={() => update(b.key, { subclass_keys: toggle(strs(p.subclass_keys), s.key) })} />
                    ))}
                  </div>
                </div>
              );
            })}
            {subclasses.length === 0 && <span className="text-white/40 text-xs">Загрузка подклассов...</span>}
          </div>
        );
      case 'race': {
        const chosen = ids(p.race_ids);
        const subs = races.filter((r) => chosen.includes(r.id_race)).flatMap((r) => r.subraces);
        return (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap gap-1.5">
              {races.map((r) => (
                <ChipCheck
                  key={r.id_race}
                  label={r.name}
                  disabled={ro}
                  checked={chosen.includes(r.id_race)}
                  onClick={() => {
                    const next = toggle(chosen, r.id_race);
                    const allowed = new Set(races.filter((x) => next.includes(x.id_race)).flatMap((x) => x.subraces.map((s) => s.id_subrace)));
                    update(b.key, { race_ids: next, subrace_ids: ids(p.subrace_ids).filter((s) => allowed.has(s)) });
                  }}
                />
              ))}
            </div>
            {subs.length > 0 && (
              <div className="flex flex-col gap-1">
                <span className="text-white/40 text-xs">Подрасы (не отмечено — любая)</span>
                <div className="flex flex-wrap gap-1.5">
                  {subs.map((s) => (
                    <ChipCheck key={s.id_subrace} label={s.name} disabled={ro} checked={ids(p.subrace_ids).includes(s.id_subrace)} onClick={() => update(b.key, { subrace_ids: toggle(ids(p.subrace_ids), s.id_subrace) })} />
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      }
      case 'quest':
        return (
          <div className="sm:max-w-md">
            <NonRepeatableQuestSelect value={numOrNull(p.quest_id)} disabled={ro} onChange={(id) => update(b.key, { quest_id: id })} />
          </div>
        );
      case 'not_in_faction':
        return (
          <label className="flex flex-col gap-1 sm:max-w-md">
            <span className={LABEL}>Фракция</span>
            <select value={numOrNull(p.faction_id) ?? ''} disabled={ro} onChange={(e) => update(b.key, { faction_id: e.target.value ? Number(e.target.value) : null })} className={FIELD}>
              <option value="" className={OPTION}>— выберите —</option>
              {factions
                .filter((f) => f.id !== factionId)
                .map((f) => (
                  <option key={f.id} value={f.id} className={OPTION}>
                    {f.name}
                    {f.is_secret ? ' (тайная)' : ''}
                  </option>
                ))}
            </select>
            {factionsError && <span className="text-site-red text-xs">{factionsError}</span>}
          </label>
        );
      default:
        return null;
    }
  };

  return (
    <section className="gray-bg p-4 sm:p-6 flex flex-col gap-4">
      <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Условия вступления ({blocks.length})</h3>
      <p className="text-white/40 text-xs">
        Все условия должны выполняться одновременно. Игрок видит их в каталоге с отметками; славу и слухи — только
        названиями ступеней. Кто перестал соответствовать — получает предупреждение, а по истечении срока исключается.
        Непримиримые пары враждебности добавляют условие «не состоит» сами.
      </p>
      {blocks.length === 0 && <p className="text-white/50 text-sm">Условий нет — вступить может любой персонаж (не НПС).</p>}
      <div className="flex flex-col gap-3">
        {blocks.map((b) => (
          <div key={b.key} className="flex flex-col gap-3 bg-white/[0.03] border border-white/[0.06] rounded-card p-3">
            <div className="flex items-center gap-2">
              <select
                value={b.type}
                disabled={ro}
                onChange={(e) => {
                  const type = e.target.value as FactionConditionType;
                  setBlocks((prev) => prev.map((x) => (x.key === b.key ? { ...x, type, params: { ...DEFAULT_PARAMS[type] } } : x)));
                }}
                className="input-underline !text-sm flex-1 min-w-0 sm:max-w-xs"
              >
                {FACTION_CONDITION_TYPES.map((t) => (
                  <option key={t} value={t} className={OPTION}>
                    {FACTION_CONDITION_LABEL[t]}
                  </option>
                ))}
              </select>
              {!ro && (
                <button type="button" onClick={() => setBlocks((prev) => prev.filter((x) => x.key !== b.key))} className="text-site-red hover:text-white transition-colors p-1 ml-auto" aria-label="Убрать условие">
                  <X size={16} />
                </button>
              )}
            </div>
            {renderParams(b)}
          </div>
        ))}
      </div>
      {canEdit && (
        <div className="flex flex-col sm:flex-row gap-3">
          <button type="button" onClick={add} className="btn-line !w-full sm:!w-auto !text-sm !px-4 !py-1.5">
            + Добавить условие
          </button>
          <button type="button" onClick={() => void save()} disabled={saving} className="btn-blue !w-full sm:!w-auto !text-sm !px-6 !py-2 disabled:opacity-50">
            {saving ? 'Сохранение...' : 'Сохранить условия'}
          </button>
        </div>
      )}
    </section>
  );
};

export default ConditionsEditor;
