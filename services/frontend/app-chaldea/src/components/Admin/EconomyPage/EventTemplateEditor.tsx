import { useState } from 'react';
import toast from 'react-hot-toast';
import { Plus, Trash2 } from 'lucide-react';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import EventIcon, { EVENT_ICON_NAMES } from '../../common/EventIcon';
import { postEconomyEventTemplate, putEconomyEventTemplate } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import type {
  EconEventKind,
  EconEventScope,
  EconEventTemplate,
  EconEventTemplateUpdate,
  EconEventTrigger,
  EconGoodsGroup,
  EconRegionTemplate,
} from '../../../types/economy';
import EventEffectsBuilder, {
  draftToEffect,
  effectDraftError,
  effectToDraft,
  newEffectDraft,
  type EffectDraft,
} from './EventEffectsBuilder';
import {
  KIND_LABELS,
  MAX_CHAINS,
  SCOPE_LABELS,
  SEASON_CODES,
  TRIGGER_LABELS,
  kindTextClass,
  seasonLabel,
} from './eventLabels';
import { FieldHint } from './ParamHint';
import type { FieldHintKey } from './paramHints';

/* Bounds of `EventTemplateIn` (feature file 3.8). */
const CODE_RE = /^[a-z][a-z0-9_]{1,31}$/;
const NAME_MIN = 2;
const NAME_MAX = 100;
const TEXT_MIN = 3;
const TEXT_MAX = 500;
const NOTE_MAX = 1000;
const WEIGHT_MAX = 1000;
const DURATION_MAX = 365;
const PERCENT = 100;

interface ChainDraft {
  key: number;
  code: string;
  chancePercent: string;
}

interface Draft {
  code: string;
  name: string;
  icon: string;
  kind: EconEventKind;
  playerText: string;
  adminNote: string;
  trigger: EconEventTrigger;
  weight: string;
  durationMin: string;
  durationMax: string;
  scope: EconEventScope;
  spreadPercent: string;
  regionTemplates: string[];
  seasons: string[];
  effects: EffectDraft[];
  chains: ChainDraft[];
  enabled: boolean;
}

let chainKey = 1;
const tidy = (n: number): number => Math.round(n * 1e6) / 1e6;

const toDraft = (t: EconEventTemplate | null): Draft =>
  t
    ? {
        code: t.code,
        name: t.name,
        icon: t.icon,
        kind: t.kind,
        playerText: t.player_text,
        adminNote: t.admin_note ?? '',
        trigger: t.trigger_kind,
        weight: String(t.weight),
        durationMin: String(t.duration_min_days),
        durationMax: String(t.duration_max_days),
        scope: t.scope,
        spreadPercent: String(tidy(t.spread_chance * PERCENT)),
        regionTemplates: t.region_templates ?? [],
        seasons: t.seasons ?? [],
        effects: (t.effects ?? []).map(effectToDraft),
        chains: (t.chains ?? []).map((c) => ({ key: chainKey++, code: c.code, chancePercent: String(tidy(c.chance * PERCENT)) })),
        enabled: t.is_enabled,
      }
    : {
        code: '',
        name: '',
        icon: 'alert',
        kind: 'bad',
        playerText: '',
        adminNote: '',
        trigger: 'random',
        weight: '1',
        durationMin: '3',
        durationMax: '6',
        scope: 'region',
        spreadPercent: '0',
        regionTemplates: [],
        seasons: [],
        effects: [newEffectDraft()],
        chains: [],
        enabled: true,
      };

const num = (text: string): number => (text.trim() === '' ? NaN : Number(text));
const inRange = (text: string, min: number, max: number, minExclusive = false): boolean => {
  const n = num(text);
  return Number.isFinite(n) && (minExclusive ? n > min : n >= min) && n <= max;
};

const toggle = (list: string[], value: string): string[] =>
  list.includes(value) ? list.filter((v) => v !== value) : [...list, value];

interface LabelProps {
  htmlFor?: string;
  children: string;
  hint?: FieldHintKey;
}

const Label = ({ htmlFor, children, hint }: LabelProps) => (
  <span className="flex items-center gap-1 min-w-0">
    {htmlFor ? (
      <label htmlFor={htmlFor} className="text-white/60 text-xs uppercase tracking-[0.06em]">
        {children}
      </label>
    ) : (
      <span className="text-white/60 text-xs uppercase tracking-[0.06em]">{children}</span>
    )}
    {hint && <FieldHint field={hint} label={children} />}
  </span>
);

const SectionTitle = ({ children, hint }: { children: string; hint?: FieldHintKey }) => (
  <h3 className="flex items-center gap-1.5 gold-text text-base font-medium uppercase tracking-[0.06em]">
    {children}
    {hint && <FieldHint field={hint} label={children} />}
  </h3>
);

interface EventTemplateEditorProps {
  /** null — a new template. */
  template: EconEventTemplate | null;
  templates: EconEventTemplate[];
  groups: EconGoodsGroup[];
  regionTemplates: EconRegionTemplate[];
  canEdit: boolean;
  onClose: () => void;
  onSaved: (t: EconEventTemplate) => void;
}

/** Event template editor (FEAT-187, feature file 3.10): create / edit in a modal. */
const EventTemplateEditor = ({
  template,
  templates,
  groups,
  regionTemplates,
  canEdit,
  onClose,
  onSaved,
}: EventTemplateEditorProps) => {
  const [draft, setDraft] = useState<Draft>(() => toDraft(template));
  const [saving, setSaving] = useState(false);
  const isNew = template === null;
  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));

  const codeTaken = isNew && templates.some((t) => t.code === draft.code.trim());
  const codeOk = !isNew || (CODE_RE.test(draft.code.trim()) && !codeTaken);
  const nameOk = draft.name.trim().length >= NAME_MIN && draft.name.trim().length <= NAME_MAX;
  const textOk = draft.playerText.trim().length >= TEXT_MIN && draft.playerText.trim().length <= TEXT_MAX;
  const noteOk = draft.adminNote.length <= NOTE_MAX;
  const weightOk = inRange(draft.weight, 0, WEIGHT_MAX);
  const minOk = inRange(draft.durationMin, 0, DURATION_MAX, true);
  const maxOk = inRange(draft.durationMax, 0, DURATION_MAX, true);
  const orderOk = !minOk || !maxOk || num(draft.durationMax) >= num(draft.durationMin);
  const spreadOk = inRange(draft.spreadPercent, 0, PERCENT);
  const effectsOk = draft.effects.length > 0 && draft.effects.every((e) => effectDraftError(e) === null);
  const ownCode = isNew ? draft.code.trim() : template.code;
  const chainError = (c: ChainDraft): string | null => {
    if (!c.code) return 'Выберите событие';
    if (c.code === ownCode) return 'Событие не может вызывать само себя';
    if (draft.chains.filter((x) => x.code === c.code).length > 1) return 'Это событие уже в цепочках';
    if (!inRange(c.chancePercent, 0, PERCENT)) return 'Шанс от 0 до 100 %';
    return null;
  };
  const chainsOk = draft.chains.every((c) => chainError(c) === null);
  const formOk =
    codeOk && nameOk && textOk && noteOk && weightOk && minOk && maxOk && orderOk && spreadOk && effectsOk && chainsOk;

  const save = async () => {
    const body: EconEventTemplateUpdate = {
      name: draft.name.trim(),
      icon: draft.icon,
      kind: draft.kind,
      player_text: draft.playerText.trim(),
      admin_note: draft.adminNote.trim() || null,
      trigger_kind: draft.trigger,
      weight: num(draft.weight),
      duration_min_days: num(draft.durationMin),
      duration_max_days: num(draft.durationMax),
      scope: draft.scope,
      spread_chance: tidy(num(draft.spreadPercent) / PERCENT),
      region_templates: draft.regionTemplates,
      seasons: SEASON_CODES.filter((s) => draft.seasons.includes(s)),
      effects: draft.effects.map(draftToEffect),
      chains: draft.chains.map((c) => ({ code: c.code, chance: tidy(num(c.chancePercent) / PERCENT) })),
      is_enabled: draft.enabled,
    };
    setSaving(true);
    try {
      const saved = isNew
        ? await postEconomyEventTemplate({ ...body, code: draft.code.trim() })
        : await putEconomyEventTemplate(template.id, body);
      toast.success(isNew ? 'Событие создано' : 'Событие сохранено');
      onSaved(saved);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить событие'));
      setSaving(false);
    }
  };

  const chainOptions = templates.filter((t) => t.code !== ownCode);
  const previewName = draft.name.trim() || 'Название события';
  const previewText = draft.playerText.trim() || 'Текст, который увидят игроки.';

  return (
    <ModalShell
      open
      onClose={onClose}
      dismissible={!saving}
      closeOnEscape={false}
      closeOnBackdrop={false}
      size="lg"
      title={isNew ? 'Новое событие' : `Событие «${template.name}»`}
      footer={
        <>
          <button type="button" className="btn-line w-full sm:w-auto !text-xs !py-2 !px-5" onClick={onClose} disabled={saving}>
            {canEdit ? 'Отмена' : 'Закрыть'}
          </button>
          {canEdit && (
            <button
              type="button"
              className="btn-blue w-full sm:w-auto !py-2 !px-5 !text-xs"
              disabled={!formOk || saving}
              onClick={save}
            >
              {saving ? 'Сохранение...' : isNew ? 'Создать' : 'Сохранить'}
            </button>
          )}
        </>
      }
    >
      <div className="flex flex-col gap-6 text-sm min-w-0">
        {!isNew && template.active_count > 0 && (
          <p className="field-hint">
            Сейчас идёт {template.active_count} — изменения коснутся только новых запусков: идущие события живут по
            снимку на момент старта.
          </p>
        )}

        {/* ---- main */}
        <section className="flex flex-col gap-4">
          <SectionTitle>Основное</SectionTitle>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex flex-col gap-1 min-w-0">
              <Label htmlFor="econ-ev-code">Код</Label>
              <input
                id="econ-ev-code"
                type="text"
                maxLength={32}
                className={`input-underline w-full ${codeOk ? '' : '!border-site-red'}`}
                value={draft.code}
                disabled={!isNew || !canEdit}
                placeholder="drought"
                onChange={(e) => set({ code: e.target.value.toLowerCase() })}
              />
              {isNew ? (
                codeOk ? (
                  <p className="text-white/40 text-xs">Латиница, цифры и «_»; потом не меняется.</p>
                ) : (
                  <p className="text-site-red text-xs">
                    {codeTaken ? 'Такой код уже есть' : 'С латинской буквы, 2–32 символа: a–z, 0–9, «_»'}
                  </p>
                )
              ) : (
                <p className="text-white/40 text-xs">Код не меняется: на него ссылаются цепочки.</p>
              )}
            </div>
            <div className="flex flex-col gap-1 min-w-0">
              <Label htmlFor="econ-ev-name">Название</Label>
              <input
                id="econ-ev-name"
                type="text"
                maxLength={NAME_MAX}
                className={`input-underline w-full ${nameOk ? '' : '!border-site-red'}`}
                value={draft.name}
                disabled={!canEdit}
                placeholder="Засуха"
                onChange={(e) => set({ name: e.target.value })}
              />
              {!nameOk && <p className="text-site-red text-xs">От {NAME_MIN} до {NAME_MAX} символов</p>}
            </div>
            <div className="flex flex-col gap-1 min-w-0">
              <Label hint="event_kind">Характер</Label>
              <div className="flex flex-wrap gap-2">
                {(Object.keys(KIND_LABELS) as EconEventKind[]).map((k) => (
                  <button
                    key={k}
                    type="button"
                    disabled={!canEdit}
                    aria-pressed={draft.kind === k}
                    onClick={() => set({ kind: k })}
                    className={`chip-outline rounded-full px-4 py-1.5 text-xs font-medium ${draft.kind === k ? 'chip-outline-active' : ''}`}
                  >
                    {KIND_LABELS[k]}
                  </button>
                ))}
              </div>
            </div>
            <label className="flex items-center gap-2 self-end py-1 text-sm text-white/80 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={draft.enabled}
                disabled={!canEdit}
                onChange={(e) => set({ enabled: e.target.checked })}
                className="w-4 h-4 shrink-0 accent-gold"
              />
              Включено
              <FieldHint field="event_enabled" label="Включено" />
            </label>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Иконка</Label>
            <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Иконка события">
              {EVENT_ICON_NAMES.map((name) => {
                const on = draft.icon === name;
                return (
                  <button
                    key={name}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    aria-label={name}
                    title={name}
                    disabled={!canEdit}
                    onClick={() => set({ icon: name })}
                    className={`w-9 h-9 flex items-center justify-center rounded-card border transition-colors duration-200 ease-site ${
                      on ? 'border-gold bg-gold/10 text-gold' : 'border-white/10 text-white/60 hover:text-white hover:border-white/30'
                    }`}
                  >
                    <EventIcon name={name} size={17} />
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex flex-col gap-1 min-w-0">
            <Label htmlFor="econ-ev-text" hint="event_player_text">Текст для игроков</Label>
            <textarea
              id="econ-ev-text"
              rows={3}
              maxLength={TEXT_MAX}
              className={`textarea-bordered w-full ${textOk ? '' : '!border-site-red'}`}
              value={draft.playerText}
              disabled={!canEdit}
              onChange={(e) => set({ playerText: e.target.value })}
            />
            <p className={`text-xs ${textOk ? 'text-white/40' : 'text-site-red'}`}>
              {textOk ? `${draft.playerText.trim().length} / ${TEXT_MAX}` : `От ${TEXT_MIN} до ${TEXT_MAX} символов`}
            </p>
            <div className="flex flex-col gap-1 rounded-card border border-white/[0.07] bg-site-bg p-3">
              <span className="text-white/40 text-[11px] uppercase tracking-[0.06em]">Как увидят игроки</span>
              <span className={`flex items-center gap-2 font-medium ${kindTextClass(draft.kind)}`}>
                <EventIcon name={draft.icon} size={16} className="shrink-0" />
                <span className="break-words min-w-0">{previewName}</span>
                <span className="text-white/40 text-xs font-normal shrink-0">ещё 6 дн.</span>
              </span>
              <span className="text-white/70 text-xs break-words">{previewText}</span>
            </div>
          </div>

          <div className="flex flex-col gap-1 min-w-0">
            <Label htmlFor="econ-ev-note">Заметка для админов</Label>
            <textarea
              id="econ-ev-note"
              rows={2}
              maxLength={NOTE_MAX}
              className={`textarea-bordered w-full ${noteOk ? '' : '!border-site-red'}`}
              value={draft.adminNote}
              disabled={!canEdit}
              placeholder="Зачем это событие и как оно задумано"
              onChange={(e) => set({ adminNote: e.target.value })}
            />
          </div>
        </section>

        {/* ---- when */}
        <section className="flex flex-col gap-4">
          <SectionTitle>Когда случается</SectionTitle>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex flex-col gap-1 min-w-0">
              <Label htmlFor="econ-ev-trigger" hint="event_trigger">Запуск</Label>
              <select
                id="econ-ev-trigger"
                className="input-underline w-full"
                value={draft.trigger}
                disabled={!canEdit}
                onChange={(e) => set({ trigger: e.target.value as EconEventTrigger })}
              >
                {(Object.keys(TRIGGER_LABELS) as EconEventTrigger[]).map((t) => (
                  <option key={t} value={t} className="bg-site-dark text-white">
                    {TRIGGER_LABELS[t]}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1 min-w-0">
              <Label htmlFor="econ-ev-weight" hint="event_weight">Вес</Label>
              <input
                id="econ-ev-weight"
                type="number"
                inputMode="decimal"
                min={0}
                max={WEIGHT_MAX}
                step={0.5}
                className={`input-underline w-full ${weightOk ? '' : '!border-site-red'}`}
                value={draft.weight}
                disabled={!canEdit}
                onChange={(e) => set({ weight: e.target.value })}
              />
              {!weightOk && <p className="text-site-red text-xs">От 0 до {WEIGHT_MAX}</p>}
            </div>
            <div className="flex flex-col gap-1 min-w-0">
              <Label hint="event_duration">Длительность, дн.</Label>
              <div className="grid grid-cols-2 gap-3">
                <input
                  aria-label="Минимум дней"
                  type="number"
                  inputMode="decimal"
                  min={0}
                  max={DURATION_MAX}
                  step={0.5}
                  className={`input-underline w-full ${minOk && orderOk ? '' : '!border-site-red'}`}
                  value={draft.durationMin}
                  disabled={!canEdit}
                  placeholder="от"
                  onChange={(e) => set({ durationMin: e.target.value })}
                />
                <input
                  aria-label="Максимум дней"
                  type="number"
                  inputMode="decimal"
                  min={0}
                  max={DURATION_MAX}
                  step={0.5}
                  className={`input-underline w-full ${maxOk && orderOk ? '' : '!border-site-red'}`}
                  value={draft.durationMax}
                  disabled={!canEdit}
                  placeholder="до"
                  onChange={(e) => set({ durationMax: e.target.value })}
                />
              </div>
              {(!minOk || !maxOk) && <p className="text-site-red text-xs">Больше 0 и не больше {DURATION_MAX} дней</p>}
              {minOk && maxOk && !orderOk && (
                <p className="text-site-red text-xs">Максимальная длительность меньше минимальной</p>
              )}
            </div>
            <div className="flex flex-col gap-1 min-w-0">
              <Label htmlFor="econ-ev-scope" hint="event_scope">Область</Label>
              <select
                id="econ-ev-scope"
                className="input-underline w-full"
                value={draft.scope}
                disabled={!canEdit}
                onChange={(e) => set({ scope: e.target.value as EconEventScope })}
              >
                {(Object.keys(SCOPE_LABELS) as EconEventScope[]).map((s) => (
                  <option key={s} value={s} className="bg-site-dark text-white">
                    {SCOPE_LABELS[s]}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1 min-w-0">
              <Label htmlFor="econ-ev-spread" hint="event_spread">Шанс перекинуться, %</Label>
              <input
                id="econ-ev-spread"
                type="number"
                inputMode="decimal"
                min={0}
                max={PERCENT}
                step={5}
                className={`input-underline w-full ${spreadOk ? '' : '!border-site-red'}`}
                value={draft.spreadPercent}
                disabled={!canEdit}
                onChange={(e) => set({ spreadPercent: e.target.value })}
              />
              {!spreadOk && <p className="text-site-red text-xs">От 0 до 100 %</p>}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label hint="event_region_templates">Шаблоны регионов</Label>
            <div className="flex flex-wrap gap-1.5">
              {regionTemplates.map((rt) => {
                const on = draft.regionTemplates.includes(rt.code);
                return (
                  <button
                    key={rt.code}
                    type="button"
                    disabled={!canEdit}
                    aria-pressed={on}
                    onClick={() => set({ regionTemplates: toggle(draft.regionTemplates, rt.code) })}
                    className={`chip-outline rounded-full px-3 py-1 text-[11px] font-medium ${on ? 'chip-outline-active' : ''}`}
                  >
                    {rt.name}
                  </button>
                );
              })}
              {/* Codes of templates that no longer exist stay visible so they can be removed. */}
              {draft.regionTemplates
                .filter((code) => !regionTemplates.some((rt) => rt.code === code))
                .map((code) => (
                  <button
                    key={code}
                    type="button"
                    disabled={!canEdit}
                    onClick={() => set({ regionTemplates: toggle(draft.regionTemplates, code) })}
                    className="chip-outline chip-outline-active rounded-full px-3 py-1 text-[11px] font-medium"
                  >
                    {code}
                  </button>
                ))}
            </div>
            <p className="text-white/40 text-xs">
              {draft.regionTemplates.length === 0 ? 'Ничего не отмечено — в регионах любых шаблонов.' : `Отмечено: ${draft.regionTemplates.length}`}
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label hint="event_seasons">Сезоны и праздники</Label>
            <div className="flex flex-wrap gap-1.5">
              {SEASON_CODES.map((code) => {
                const on = draft.seasons.includes(code);
                return (
                  <button
                    key={code}
                    type="button"
                    disabled={!canEdit}
                    aria-pressed={on}
                    onClick={() => set({ seasons: toggle(draft.seasons, code) })}
                    className={`chip-outline rounded-full px-3 py-1 text-[11px] font-medium ${on ? 'chip-outline-active' : ''}`}
                  >
                    {seasonLabel(code)}
                  </button>
                );
              })}
            </div>
            <p className="text-white/40 text-xs">
              {draft.seasons.length === 0 ? 'Ничего не отмечено — в любое время года.' : `Отмечено: ${draft.seasons.length}`}
            </p>
          </div>
        </section>

        {/* ---- effects */}
        <section className="flex flex-col gap-3">
          <SectionTitle hint="event_effects">Эффекты</SectionTitle>
          <EventEffectsBuilder
            effects={draft.effects}
            groups={groups}
            canEdit={canEdit}
            onChange={(effects) => set({ effects })}
          />
        </section>

        {/* ---- chains */}
        <section className="flex flex-col gap-3">
          <SectionTitle hint="event_chains">Цепочки</SectionTitle>
          {draft.chains.length === 0 && <p className="text-white/40 text-xs">Это событие не вызывает других.</p>}
          <ul className="flex flex-col gap-2">
            {draft.chains.map((c, i) => {
              const err = chainError(c);
              const known = chainOptions.some((t) => t.code === c.code);
              return (
                <li key={c.key} className="flex flex-col gap-1">
                  <div className="grid grid-cols-[minmax(0,1fr)_5.5rem_auto] items-end gap-3">
                    <select
                      aria-label={`Цепочка ${i + 1}: событие`}
                      className="input-underline w-full"
                      value={c.code}
                      disabled={!canEdit}
                      onChange={(e) =>
                        set({ chains: draft.chains.map((x) => (x.key === c.key ? { ...x, code: e.target.value } : x)) })
                      }
                    >
                      <option value="" className="bg-site-dark text-white">Выберите событие</option>
                      {!known && c.code && (
                        <option value={c.code} className="bg-site-dark text-white">{c.code}</option>
                      )}
                      {chainOptions.map((t) => (
                        <option key={t.code} value={t.code} className="bg-site-dark text-white">
                          {t.name}
                        </option>
                      ))}
                    </select>
                    <input
                      aria-label={`Цепочка ${i + 1}: шанс, %`}
                      type="number"
                      inputMode="decimal"
                      min={0}
                      max={PERCENT}
                      step={5}
                      className="input-underline w-full"
                      value={c.chancePercent}
                      disabled={!canEdit}
                      placeholder="%"
                      onChange={(e) =>
                        set({
                          chains: draft.chains.map((x) => (x.key === c.key ? { ...x, chancePercent: e.target.value } : x)),
                        })
                      }
                    />
                    {canEdit ? (
                      <button
                        type="button"
                        aria-label={`Убрать цепочку ${i + 1}`}
                        onClick={() => set({ chains: draft.chains.filter((x) => x.key !== c.key) })}
                        className="mb-1.5 text-white/50 hover:text-site-red transition-colors duration-200 ease-site"
                      >
                        <Trash2 size={14} />
                      </button>
                    ) : (
                      <span />
                    )}
                  </div>
                  {err && <p className="text-site-red text-xs">{err}</p>}
                </li>
              );
            })}
          </ul>
          {canEdit && (
            <button
              type="button"
              className="btn-line w-full sm:w-auto sm:self-start !text-xs !py-2 !px-5 inline-flex items-center justify-center gap-1.5"
              disabled={draft.chains.length >= MAX_CHAINS}
              onClick={() => set({ chains: [...draft.chains, { key: chainKey++, code: '', chancePercent: '20' }] })}
            >
              <Plus size={14} />
              Добавить цепочку
            </button>
          )}
        </section>

        {canEdit && !formOk && <p className="text-site-red text-xs">Исправьте поля, отмеченные красным.</p>}
        {!canEdit && (
          <p className="field-hint">Изменять события может только администратор с правом «economy:settings».</p>
        )}
      </div>
    </ModalShell>
  );
};

export default EventTemplateEditor;
