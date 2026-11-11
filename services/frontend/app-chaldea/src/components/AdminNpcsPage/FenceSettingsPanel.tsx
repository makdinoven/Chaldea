import { useCallback, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { apiErrorMessage } from '../../api/errors';
import {
  fetchFenceSettings,
  saveFenceSettings,
  FENCE_CASH_TARGET_DEFAULT,
  FENCE_CASH_TARGET_MAX,
  FENCE_PRICE_PCT_DEFAULT,
  FENCE_PRICE_PCT_MAX,
  FENCE_PRICE_PCT_MIN,
  type FenceSettingsIn,
  type FenceSettingsOut,
} from '../../api/npcAdmin';
import { useCurrency } from '../../hooks/useCurrency';
import { useDirtyReport } from '../Admin/ExpandableList/useDirtyReport';

/*
  FEAT-211 — «Скупка» of a «Скупщик» NPC: what stolen goods he takes, at what
  share of the region market price, and how much cash the 6 h refill keeps in
  his till (from the residents' purse of his region).
*/

interface FenceSettingsPanelProps {
  npcId: number;
  /** forwards the unsaved-settings flag to the NPC panel (FEAT-208 dirty guard) */
  onDirtyChange?: (dirty: boolean) => void;
}

/** The 12 goods groups of the economy (`econ_goods_groups`); bales exist for each of them. */
const GOODS_GROUPS: { code: string; name: string }[] = [
  { code: 'food', name: 'Продовольствие' },
  { code: 'ore_metal', name: 'Руда и металл' },
  { code: 'wood', name: 'Древесина' },
  { code: 'herbs', name: 'Травы и реагенты' },
  { code: 'hides_textiles', name: 'Шкуры и ткани' },
  { code: 'magic', name: 'Магические материалы' },
  { code: 'weapons', name: 'Оружие' },
  { code: 'armor', name: 'Броня и одежда' },
  { code: 'jewelry', name: 'Украшения' },
  { code: 'potions', name: 'Зелья' },
  { code: 'tools', name: 'Ремесленный инвентарь' },
  { code: 'household', name: 'Быт и мебель' },
];

interface FenceForm {
  isActive: boolean;
  pricePct: string;
  groups: string[];
  cashTarget: string;
}

const formFrom = (s: FenceSettingsOut): FenceForm => ({
  isActive: s.is_active,
  pricePct: String(s.price_pct ?? FENCE_PRICE_PCT_DEFAULT),
  groups: [...(s.accepted_groups ?? [])].sort(),
  cashTarget: String(s.cash_target ?? FENCE_CASH_TARGET_DEFAULT),
});

const bodyFrom = (f: FenceForm): FenceSettingsIn => ({
  is_active: f.isActive,
  price_pct: Number(f.pricePct),
  accepted_groups: [...f.groups].sort(),
  cash_target: Number(f.cashTarget),
});

const sameForm = (a: FenceForm, b: FenceForm) => JSON.stringify(bodyFrom(a)) === JSON.stringify(bodyFrom(b));

/** Client-side mirror of the A12 bounds (the server re-checks everything). */
const validate = (f: FenceForm): string | null => {
  const pct = Number(f.pricePct);
  if (!/^\d+$/.test(f.pricePct.trim()) || pct < FENCE_PRICE_PCT_MIN || pct > FENCE_PRICE_PCT_MAX) {
    return `Цена скупки: целое число от ${FENCE_PRICE_PCT_MIN} до ${FENCE_PRICE_PCT_MAX} %`;
  }
  const cash = Number(f.cashTarget);
  if (!/^\d+$/.test(f.cashTarget.trim()) || cash > FENCE_CASH_TARGET_MAX) {
    return `Целевая касса: целое число от 0 до ${FENCE_CASH_TARGET_MAX.toLocaleString('ru-RU')}`;
  }
  return null;
};

const FenceSettingsPanel = ({ npcId, onDirtyChange }: FenceSettingsPanelProps) => {
  const { format } = useCurrency();
  const [settings, setSettings] = useState<FenceSettingsOut | null>(null);
  const [form, setForm] = useState<FenceForm | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const apply = useCallback((s: FenceSettingsOut) => {
    setSettings(s);
    setForm(formFrom(s));
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    fetchFenceSettings(npcId)
      .then(apply)
      .catch((err) => {
        const msg = apiErrorMessage(err, 'Не удалось загрузить настройки скупки');
        setLoadError(msg);
        toast.error(msg);
      })
      .finally(() => setLoading(false));
  }, [npcId, apply]);

  useEffect(() => {
    setFormError(null);
    load();
  }, [load]);

  const dirty = useMemo(() => !!(settings && form && !sameForm(form, formFrom(settings))), [settings, form]);
  useDirtyReport(dirty, onDirtyChange);

  const update = (patch: Partial<FenceForm>) => {
    setForm((f) => (f ? { ...f, ...patch } : f));
    setFormError(null);
  };

  const toggleGroup = (code: string) => {
    if (!form) return;
    update({
      groups: form.groups.includes(code) ? form.groups.filter((g) => g !== code) : [...form.groups, code].sort(),
    });
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
      apply(await saveFenceSettings(npcId, bodyFrom(form)));
      toast.success('Настройки скупки сохранены');
    } catch (err) {
      const msg = apiErrorMessage(err, 'Не удалось сохранить настройки скупки');
      setFormError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  if (loading && !settings) {
    return (
      <div className="gray-bg p-4 sm:p-6 flex items-center justify-center">
        <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

  if (loadError || !settings || !form) {
    return (
      <div className="gray-bg p-4 sm:p-6 flex flex-col gap-3">
        <h3 className="gold-text text-xl font-semibold uppercase tracking-[0.06em]">Скупка</h3>
        <p className="text-site-red text-sm">{loadError ?? 'Не удалось загрузить настройки скупки'}</p>
        <button type="button" onClick={load} className="btn-line !w-auto !px-6 self-start">
          Повторить
        </button>
      </div>
    );
  }

  const allGroups = form.groups.length === 0;

  return (
    <div className="gray-bg p-4 sm:p-6 flex flex-col gap-5 min-w-0">
      <div className="flex flex-col gap-1">
        <h3 className="gold-text text-xl font-semibold uppercase tracking-[0.06em]">Скупка</h3>
        <p className="text-white/50 text-xs">
          Скупщик покупает у игроков краденые тюки (после налётов на караваны) — дешевле рыночной цены края. Платит из
          своей кассы; каждый пересчёт экономики касса пополняется из кошелька жителей края до целевой суммы.
        </p>
      </div>

      {/* Status */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="flex flex-col gap-0.5 rounded-card border border-white/10 bg-white/[0.03] px-3 py-2 min-w-0">
          <span className="text-white/50 text-[11px] uppercase tracking-[0.06em]">Касса сейчас</span>
          <span className="text-gold text-sm font-medium">{format(settings.cash)}</span>
        </div>
        <div className="flex flex-col gap-0.5 rounded-card border border-white/10 bg-white/[0.03] px-3 py-2 min-w-0">
          <span className="text-white/50 text-[11px] uppercase tracking-[0.06em]">Край</span>
          <span className="text-white text-sm break-words">{settings.region_name ?? 'не определён'}</span>
        </div>
        <div className="flex flex-col gap-0.5 rounded-card border border-white/10 bg-white/[0.03] px-3 py-2 min-w-0">
          <span className="text-white/50 text-[11px] uppercase tracking-[0.06em]">Пополнение кассы</span>
          <span className={`text-sm ${settings.refill_active ? 'text-stat-energy' : 'text-site-red'}`}>
            {settings.refill_active ? 'идёт каждый пересчёт' : 'не идёт (край вне экономики)'}
          </span>
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm text-white cursor-pointer self-start">
        <input
          type="checkbox"
          className="accent-gold w-4 h-4"
          checked={form.isActive}
          disabled={saving}
          onChange={(e) => update({ isActive: e.target.checked })}
        />
        {form.isActive ? 'Скупает краденое' : 'Не скупает (выключен)'}
      </label>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 sm:max-w-[560px]">
        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Цена скупки, % от рынка края</span>
          <input
            type="text"
            inputMode="numeric"
            className="input-underline w-full"
            value={form.pricePct}
            disabled={saving}
            onChange={(e) => update({ pricePct: e.target.value.replace(/[^\d]/g, '').slice(0, 3) })}
          />
          <span className="text-white/40 text-[11px]">
            {FENCE_PRICE_PCT_MIN}–{FENCE_PRICE_PCT_MAX}; по умолчанию {FENCE_PRICE_PCT_DEFAULT}
          </span>
        </label>
        <label className="flex flex-col gap-1 min-w-0">
          <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Целевая касса</span>
          <input
            type="text"
            inputMode="numeric"
            className="input-underline w-full"
            value={form.cashTarget}
            disabled={saving}
            onChange={(e) => update({ cashTarget: e.target.value.replace(/[^\d]/g, '').slice(0, 8) })}
          />
          <span className="text-white/40 text-[11px]">
            0–{FENCE_CASH_TARGET_MAX.toLocaleString('ru-RU')}; по умолчанию {FENCE_CASH_TARGET_DEFAULT}
          </span>
        </label>
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Какие товары берёт</span>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={saving}
            onClick={() => update({ groups: [] })}
            className={`chip-outline rounded-full px-3 py-1 text-xs ${allGroups ? 'chip-outline-active' : ''}`}
          >
            Все группы
          </button>
          {GOODS_GROUPS.map((g) => (
            <button
              key={g.code}
              type="button"
              disabled={saving}
              aria-pressed={form.groups.includes(g.code)}
              onClick={() => toggleGroup(g.code)}
              className={`chip-outline rounded-full px-3 py-1 text-xs ${
                form.groups.includes(g.code) ? 'chip-outline-active' : ''
              }`}
            >
              {g.name}
            </button>
          ))}
        </div>
        <span className="text-white/40 text-[11px]">
          {allGroups ? 'Берёт краденое всех групп.' : `Берёт только выбранные группы: ${form.groups.length}.`}
        </span>
      </div>

      {formError && <p className="text-site-red text-sm">{formError}</p>}

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn-blue !px-6" disabled={!dirty || saving} onClick={() => void handleSave()}>
          {saving ? 'Сохранение...' : 'Сохранить'}
        </button>
        {dirty && !saving && (
          <button
            type="button"
            className="text-sm text-white/50 hover:text-white transition-colors duration-200"
            onClick={() => {
              setForm(formFrom(settings));
              setFormError(null);
            }}
          >
            Отменить изменения
          </button>
        )}
      </div>
    </div>
  );
};

export default FenceSettingsPanel;
