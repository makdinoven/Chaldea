import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { fetchEconomySettings, fetchEconomySim, patchEconomySimParams, putEconomySettings } from '../../../api/economyAdmin';
import { fetchMintQuotas } from '../../../api/mint';
import { apiErrorMessage } from '../../../api/errors';
import { useCurrency } from '../../../hooks/useCurrency';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { fetchCurrencyForms } from '../../../redux/slices/economySlice';
import { selectPermissions } from '../../../redux/slices/userSlice';
import type { QuotaEntry } from '../../../types/economy';
import { capitalize, formatCurrency, type CurrencyForms } from '../../../utils/currency';
import { hasPermission } from '../../../utils/permissions';
import { seasonName } from '../../../utils/seasonPeriod';
import { GuideIntro } from './GuideLink';
import { FieldHint, SimParamHint } from './ParamHint';
import { formatDateTime } from './economyLabels';
import type { FieldHintKey } from './paramHints';

const FORM_MAX = 50;
const SHORT_MAX = 20;
const MAX_TAX_PERCENT = 50;
const PREVIEW_AMOUNTS = [1, 3, 5, 21];
const FORBIDDEN_CHARS = /[<>]/;

const FIELDS: { key: keyof CurrencyForms; label: string; hint: string; help: FieldHintKey }[] = [
  { key: 'name', label: 'Название', hint: 'Именительный падеж, для заголовков: «Марки»', help: 'currency_name' },
  { key: 'genitive', label: 'Родительный падеж', hint: '«Недостаточно марок»', help: 'currency_genitive' },
  { key: 'one', label: 'Счёт: 1', hint: '«1 марка», «21 марка»', help: 'currency_one' },
  { key: 'few', label: 'Счёт: 2–4', hint: '«3 марки»', help: 'currency_few' },
  { key: 'many', label: 'Счёт: 5–20', hint: '«5 марок», «11 марок»', help: 'currency_many' },
  { key: 'short', label: 'Сокращение', hint: '«100 ṃ» — для тесных мест', help: 'currency_short' },
];

const fieldError = (key: keyof CurrencyForms, value: string): string | null => {
  const v = value.trim();
  if (!v) return 'Поле не может быть пустым';
  const limit = key === 'short' ? SHORT_MAX : FORM_MAX;
  if (v.length > limit) return `Не длиннее ${limit} символов`;
  if (FORBIDDEN_CHARS.test(v)) return 'Символы < и > запрещены';
  return null;
};

/** `quota_season_amount` bounds (`ECON_SIM_PARAM_BOUNDS`, feature file 3.5). */
const QUOTA_MAX = 1_000_000_000;
const QUOTA_NUMBERS = { def: 0, min: 0, max: QUOTA_MAX };

/** FEAT-191 «Квота сезона»: a sim param, saved alone so the rest of the params stay as stored. */
const SeasonQuotaCard = ({ canSettings }: { canSettings: boolean }) => {
  const canEmit = hasPermission(useAppSelector(selectPermissions), 'economy:emit');
  const canEdit = canSettings && canEmit;
  const { format } = useCurrency();
  const [stored, setStored] = useState<number | null>(null);
  const [value, setValue] = useState('');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [lastQuota, setLastQuota] = useState<QuotaEntry | null>(null);
  const [quotaError, setQuotaError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchEconomySim()
      .then((sim) => {
        if (cancelled) return;
        const amount = sim.params.quota_season_amount ?? 0;
        setStored(amount);
        setValue(String(amount));
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = apiErrorMessage(e, 'Не удалось загрузить квоту сезона');
        setLoadError(msg);
        toast.error(msg);
      });
    fetchMintQuotas(1)
      .then((list) => {
        if (!cancelled) setLastQuota(list[0] ?? null);
      })
      .catch((e) => {
        if (!cancelled) setQuotaError(apiErrorMessage(e, 'Не удалось загрузить историю квот'));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const n = Number(value.trim());
  const valid = value.trim() !== '' && Number.isInteger(n) && n >= 0 && n <= QUOTA_MAX;
  const dirty = stored !== null && valid && n !== stored;

  const save = async () => {
    setSaving(true);
    try {
      const sim = await patchEconomySimParams({ quota_season_amount: n });
      const amount = sim.params.quota_season_amount ?? n;
      setStored(amount);
      setValue(String(amount));
      toast.success('Квота сезона сохранена');
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить квоту сезона'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
      <div className="flex flex-col gap-1">
        <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Квота сезона</h2>
        <p className="text-white/50 text-sm">
          Один раз в начале каждого игрового сезона (сезон + праздник, 49 дней) эта сумма выпускается эмиссией в
          казны регионов, участвующих в пересчёте, пропорционально населению. 0 — квоты нет.
        </p>
      </div>
      {loadError ? (
        <p className="text-site-red text-sm">{loadError}</p>
      ) : stored === null ? (
        <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      ) : (
        <div className="flex flex-col sm:flex-row sm:items-end gap-4">
          <div className="flex flex-col gap-1 sm:max-w-[320px] w-full">
            <span className="flex items-center gap-1 min-w-0">
              <label htmlFor="econ-quota" className="text-white/60 text-xs uppercase tracking-[0.06em]">
                Сумма за сезон
              </label>
              <SimParamHint param="quota_season_amount" label="Квота сезона" numbers={QUOTA_NUMBERS} />
            </span>
            <input
              id="econ-quota"
              type="text"
              inputMode="numeric"
              className="input-underline w-full"
              value={value}
              disabled={!canEdit || saving}
              onChange={(e) => setValue(e.target.value.replace(/[^\d]/g, '').slice(0, 10))}
            />
            {!valid ? (
              <p className="text-site-red text-xs">Целое число от 0 до {QUOTA_MAX.toLocaleString('ru-RU')}</p>
            ) : (
              <p className="text-white/40 text-xs">{n > 0 ? `${format(n)} за сезон` : 'Квота выключена'}</p>
            )}
          </div>
          {canEdit && (
            <button
              type="button"
              className="btn-blue w-full sm:w-auto !px-6"
              disabled={!dirty || saving}
              onClick={() => void save()}
            >
              {saving ? 'Сохранение...' : 'Сохранить'}
            </button>
          )}
        </div>
      )}
      {!canEdit && (
        <p className="field-hint">Менять квоту может администратор с правами «economy:settings» и «economy:emit».</p>
      )}
      {quotaError ? (
        <p className="text-site-red text-xs">{quotaError}</p>
      ) : (
        <p className="text-white/50 text-xs">
          {lastQuota
            ? `Последняя выдача: ${seasonName(lastQuota.season, lastQuota.year)} — ${format(lastQuota.amount)} в ${lastQuota.regions} рег., ${formatDateTime(lastQuota.created_at)}`
            : 'Квота ещё не выдавалась.'}
        </p>
      )}
    </section>
  );
};

interface EconomySettingsProps {
  canEdit: boolean;
  /** Called after a successful save (the summary shows the tax rate). */
  onSaved: () => void;
}

/** Currency word forms with a live preview and the region → country tax rate. */
const EconomySettings = ({ canEdit, onSaved }: EconomySettingsProps) => {
  const dispatch = useAppDispatch();
  const [forms, setForms] = useState<CurrencyForms | null>(null);
  const [taxPercent, setTaxPercent] = useState('');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchEconomySettings()
      .then((s) => {
        if (cancelled) return;
        setForms(s.currency);
        setTaxPercent(String(Math.round(s.country_tax_rate * 10000) / 100));
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = apiErrorMessage(e, 'Не удалось загрузить настройки экономики');
        setLoadError(msg);
        toast.error(msg);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loadError) return <p className="text-site-red text-sm">{loadError}</p>;
  if (!forms) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

  const errors = FIELDS.map((f) => fieldError(f.key, forms[f.key]));
  const taxNumber = Number(taxPercent);
  const taxValid = taxPercent.trim() !== '' && Number.isFinite(taxNumber) && taxNumber >= 0 && taxNumber <= MAX_TAX_PERCENT;
  const formValid = errors.every((e) => e === null) && taxValid;
  const previewForms: CurrencyForms = Object.fromEntries(
    Object.entries(forms).map(([k, v]) => [k, (v as string).trim()]),
  ) as unknown as CurrencyForms;

  const save = async () => {
    setSaving(true);
    try {
      const saved = await putEconomySettings({
        currency: previewForms,
        country_tax_rate: Math.round(taxNumber * 100) / 10000,
      });
      setForms(saved.currency);
      setTaxPercent(String(Math.round(saved.country_tax_rate * 10000) / 100));
      toast.success('Настройки экономики сохранены');
      // Refresh the site-wide wording right away.
      dispatch(fetchCurrencyForms({ force: true }));
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить настройки экономики'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <GuideIntro section="money-flow">
        Здесь — название валюты во всей игре и доля налога, которую казна региона отдаёт казне страны. «?» у поля
        объясняет, на что оно влияет.
      </GuideIntro>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2 bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-5 min-w-0">
          <div className="flex flex-col gap-1">
            <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Название валюты</h2>
            <p className="text-white/50 text-sm">
              Весь текст игры про деньги берёт слова отсюда. Другие сервисы подхватят изменения в течение минуты.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            {FIELDS.map((f, i) => (
              <div key={f.key} className="flex flex-col gap-1 min-w-0">
                <span className="flex items-center gap-1 min-w-0">
                  <label htmlFor={`econ-form-${f.key}`} className="text-white/60 text-xs uppercase tracking-[0.06em]">
                    {f.label}
                  </label>
                  <FieldHint field={f.help} label={f.label} />
                </span>
                <input
                  id={`econ-form-${f.key}`}
                  type="text"
                  className="input-underline w-full"
                  value={forms[f.key]}
                  maxLength={f.key === 'short' ? SHORT_MAX : FORM_MAX}
                  disabled={!canEdit}
                  onChange={(e) => setForms({ ...forms, [f.key]: e.target.value })}
                />
                {errors[i] ? (
                  <p className="text-site-red text-xs">{errors[i]}</p>
                ) : (
                  <p className="text-white/40 text-xs">{f.hint}</p>
                )}
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-1 sm:max-w-[320px]">
            <span className="flex items-center gap-1 min-w-0">
              <label htmlFor="econ-tax" className="text-white/60 text-xs uppercase tracking-[0.06em]">
                Налог региона в казну страны, %
              </label>
              <FieldHint field="country_tax" label="Налог региона в казну страны" />
            </span>
            <input
              id="econ-tax"
              type="number"
              min={0}
              max={MAX_TAX_PERCENT}
              step={0.5}
              className="input-underline w-full"
              value={taxPercent}
              disabled={!canEdit}
              onChange={(e) => setTaxPercent(e.target.value)}
            />
            {!taxValid ? (
              <p className="text-site-red text-xs">От 0 до {MAX_TAX_PERCENT}%</p>
            ) : (
              <p className="text-white/40 text-xs">С каждого поступления в казну региона: налоги, платежи игроков, комиссии банков</p>
            )}
          </div>

          {canEdit ? (
            <button type="button" className="btn-blue w-full sm:w-auto sm:self-start !px-6" disabled={!formValid || saving} onClick={save}>
              {saving ? 'Сохранение...' : 'Сохранить'}
            </button>
          ) : (
            <p className="field-hint">Изменять настройки может только администратор с правом «economy:settings».</p>
          )}
        </section>

        <section className="self-start w-full bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-3 min-w-0">
          <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Предпросмотр</h2>
          {errors.some((e) => e !== null) ? (
            <p className="text-white/40 text-sm italic">Заполните все поля, чтобы увидеть предпросмотр.</p>
          ) : (
            <ul className="flex flex-col gap-2 text-sm">
              {PREVIEW_AMOUNTS.map((n) => (
                <li key={n} className="text-white break-words">{formatCurrency(n, { forms: previewForms })}</li>
              ))}
              <li className="text-white break-words">{formatCurrency(1500, { forms: previewForms, short: true })}</li>
              <li className="text-white/70 break-words">Недостаточно {previewForms.genitive}</li>
              <li className="text-white/70 break-words">{capitalize(previewForms.name)}: 250</li>
            </ul>
          )}
        </section>
      </div>
      <SeasonQuotaCard canSettings={canEdit} />
    </div>
  );
};

export default EconomySettings;
