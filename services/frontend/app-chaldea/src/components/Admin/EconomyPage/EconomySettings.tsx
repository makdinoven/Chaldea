import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { fetchEconomySettings, putEconomySettings } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { useAppDispatch } from '../../../redux/store';
import { fetchCurrencyForms } from '../../../redux/slices/economySlice';
import { capitalize, formatCurrency, type CurrencyForms } from '../../../utils/currency';

const FORM_MAX = 50;
const SHORT_MAX = 20;
const MAX_TAX_PERCENT = 50;
const PREVIEW_AMOUNTS = [1, 3, 5, 21];
const FORBIDDEN_CHARS = /[<>]/;

const FIELDS: { key: keyof CurrencyForms; label: string; hint: string }[] = [
  { key: 'name', label: 'Название', hint: 'Именительный падеж, для заголовков: «Марки»' },
  { key: 'genitive', label: 'Родительный падеж', hint: '«Недостаточно марок»' },
  { key: 'one', label: 'Счёт: 1', hint: '«1 марка», «21 марка»' },
  { key: 'few', label: 'Счёт: 2–4', hint: '«3 марки»' },
  { key: 'many', label: 'Счёт: 5–20', hint: '«5 марок», «11 марок»' },
  { key: 'short', label: 'Сокращение', hint: '«100 ṃ» — для тесных мест' },
];

const fieldError = (key: keyof CurrencyForms, value: string): string | null => {
  const v = value.trim();
  if (!v) return 'Поле не может быть пустым';
  const limit = key === 'short' ? SHORT_MAX : FORM_MAX;
  if (v.length > limit) return `Не длиннее ${limit} символов`;
  if (FORBIDDEN_CHARS.test(v)) return 'Символы < и > запрещены';
  return null;
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
              <label htmlFor={`econ-form-${f.key}`} className="text-white/60 text-xs uppercase tracking-[0.06em]">
                {f.label}
              </label>
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
          <label htmlFor="econ-tax" className="text-white/60 text-xs uppercase tracking-[0.06em]">
            Налог региона в казну страны, %
          </label>
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
            <p className="text-white/40 text-xs">С каждого поступления от игроков в казну региона</p>
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
  );
};

export default EconomySettings;
