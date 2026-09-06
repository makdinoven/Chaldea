import { useMemo } from 'react';
import AvatarUploader from './AvatarUploader';
import SubraceLookNote from './SubraceLookNote';
import TenureField from './TenureField';
import type { PersonaForm, SubraceData } from '../types';

/**
 * FEAT-154 (task #18) — step 4, «Личность». Replaces `BiographyPage.jsx`
 * (migrated to TSX + Tailwind, its SCSS module deleted — T1/T3).
 *
 * What the step adds over the old form:
 * - a portrait that actually uploads (rule 21) and is still optional;
 * - a permanently visible look memo for the chosen subrace (rules 16-17);
 * - a soft height hint against the subrace range (rule 15) — a **warning**,
 *   never a block: the moderator decides, not the form;
 * - the in-world «в Скитальцах с» tenure (rules 22-24);
 * - the Coordinator's prompt under the biography.
 *
 * Free text is stored verbatim and is rendered elsewhere only through
 * `whitespace-pre-wrap` — never `dangerouslySetInnerHTML`.
 */

interface StepPersonaProps {
  value: PersonaForm;
  onChange: (next: PersonaForm) => void;
  selectedSubrace: SubraceData | null;
  raceName?: string | null;
  /** From `selectCurrentGameYear` — never a literal (§3.5). */
  currentGameYear: number | null;
  /** From `selectGameTimeError` — set when the game clock failed to load. */
  gameTimeError?: string | null;
}

const SEX_OPTIONS = [
  { value: 'male', label: 'Мужской' },
  { value: 'female', label: 'Женский' },
  { value: 'genderless', label: 'Бесполый' },
];

/** Matches `CharacterRequest.name` — `String(20)` in character-service. */
const NAME_MAX_LENGTH = 20;

const TEXT_AREAS: {
  id: 'appearance' | 'biography' | 'personality';
  label: string;
  required?: boolean;
  hint?: string;
  /** The hint states a requirement — it gets the louder, backed variant. */
  hintIsRequirement?: boolean;
  rows: number;
}[] = [
  {
    id: 'appearance',
    label: 'Внешность',
    required: true,
    hint: 'Опишите, каким вас увидят другие. Памятка об облике подрасы — рядом.',
    rows: 6,
  },
  {
    id: 'biography',
    label: 'Биография',
    required: true,
    // Merged with the former «Предыстория» (they covered the same ground and
    // players had to guess the boundary). The Coordinator still asks, but the
    // ask is now a stated requirement — it is what the moderator looks for.
    // Worded without assuming gender: «как вы стали», never «стал».
    hint: 'Координатор спрашивает: «Кто ты и что привело тебя сюда?» Обязательно напишите, как вы стали Скитальцем — без этого заявку вернут.',
    hintIsRequirement: true,
    rows: 10,
  },
  {
    id: 'personality',
    label: 'Характер',
    required: true,
    hint: 'Нрав, привычки, с чем вы не миритесь.',
    rows: 6,
  },
];

const StepPersona = ({
  value,
  onChange,
  selectedSubrace,
  raceName,
  currentGameYear,
  gameTimeError = null,
}: StepPersonaProps) => {
  const patch = (fields: Partial<PersonaForm>) => onChange({ ...value, ...fields });

  const ageNumber = useMemo(() => {
    const parsed = Number(value.age);
    return value.age !== '' && Number.isFinite(parsed) ? parsed : null;
  }, [value.age]);

  /**
   * Rule 15 — a height outside the subrace range is unusual, not forbidden.
   * The message says so explicitly so nobody hunts for a blocked button.
   */
  const heightWarning = useMemo(() => {
    const min = selectedSubrace?.height_min;
    const max = selectedSubrace?.height_max;
    if (typeof min !== 'number' || typeof max !== 'number') return null;
    const height = Number(value.height);
    if (value.height === '' || !Number.isFinite(height)) return null;
    if (height >= min && height <= max) return null;
    return `Для подрасы «${selectedSubrace?.name}» обычен рост ${min}–${max} см. Ваш выбор допустим — просто он редкий, и его оценит Координатор.`;
  }, [selectedSubrace, value.height]);

  const heightRangeHint =
    typeof selectedSubrace?.height_min === 'number' &&
    typeof selectedSubrace?.height_max === 'number'
      ? `Обычно ${selectedSubrace.height_min}–${selectedSubrace.height_max} см`
      : null;

  return (
    <div className="w-full flex flex-col gap-6 px-4 md:px-[60px]">
      <p className="field-hint max-w-[720px]">
        Всё, что вы напишете здесь, попадёт в реестр Цитадели и в ваш паспорт. Поля со
        звёздочкой обязательны.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,280px)_1fr] gap-6 lg:gap-8">
        {/* Left column — portrait and the subrace look memo (rules 16-17) */}
        <div className="flex flex-col gap-6">
          <AvatarUploader
            value={value.avatarUrl}
            onChange={(avatarUrl) => patch({ avatarUrl })}
            fallbackImage={selectedSubrace?.image ?? null}
            characterName={value.name}
          />
          <SubraceLookNote subrace={selectedSubrace} raceName={raceName} />
        </div>

        {/* Right column — the application itself */}
        <form className="flex flex-col gap-8" onSubmit={(event) => event.preventDefault()}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-5">
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className="text-white text-sm sm:text-base">Имя персонажа*</span>
              <input
                className="input-underline"
                type="text"
                maxLength={NAME_MAX_LENGTH}
                placeholder="Как вас внесут в реестр"
                value={value.name}
                onChange={(event) => patch({ name: event.target.value })}
              />
              <span className="text-white/40 text-[11px]">
                {value.name.length}/{NAME_MAX_LENGTH}
              </span>
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white text-sm sm:text-base">Возраст</span>
              <input
                className="input-underline"
                type="number"
                inputMode="numeric"
                min={0}
                placeholder="лет"
                value={value.age}
                onChange={(event) => patch({ age: event.target.value })}
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white text-sm sm:text-base">Пол</span>
              <select
                className="input-underline"
                value={value.sex}
                onChange={(event) => patch({ sex: event.target.value })}
              >
                <option value="" className="bg-site-dark text-white">Не указан</option>
                {SEX_OPTIONS.map((option) => (
                  <option
                    key={option.value}
                    value={option.value}
                    className="bg-site-dark text-white"
                  >
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white text-sm sm:text-base">Рост, см</span>
              <input
                className="input-underline"
                type="number"
                inputMode="numeric"
                min={0}
                placeholder="см"
                value={value.height}
                onChange={(event) => patch({ height: event.target.value })}
              />
              {heightRangeHint && !heightWarning && (
                <span className="text-white/40 text-[11px]">{heightRangeHint}</span>
              )}
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white text-sm sm:text-base">Вес, кг</span>
              <input
                className="input-underline"
                type="number"
                inputMode="numeric"
                min={0}
                placeholder="кг"
                value={value.weight}
                onChange={(event) => patch({ weight: event.target.value })}
              />
            </label>

            {heightWarning && (
              <p
                role="status"
                className="sm:col-span-2 text-gold text-[13px] sm:text-sm leading-snug border border-gold/40 rounded-card px-3 py-2"
              >
                {heightWarning}
              </p>
            )}

            <div className="sm:col-span-2">
              <TenureField
                year={value.skitaltsySinceYear}
                segment={value.skitaltsySinceSegment}
                onChange={(skitaltsySinceYear, skitaltsySinceSegment) =>
                  patch({ skitaltsySinceYear, skitaltsySinceSegment })
                }
                currentGameYear={currentGameYear}
                gameTimeError={gameTimeError}
                age={ageNumber}
              />
            </div>
          </div>

          <div className="flex flex-col gap-6">
            {TEXT_AREAS.map((field) => (
              <label key={field.id} className="flex flex-col gap-2">
                <span className="text-white text-sm sm:text-base">
                  {field.label}
                  {field.required ? '*' : ''}
                </span>
                <textarea
                  className="textarea-bordered w-full"
                  rows={field.rows}
                  value={value[field.id]}
                  onChange={(event) => patch({ [field.id]: event.target.value } as Partial<PersonaForm>)}
                />
                {field.hint && (
                  <span
                    className={
                      field.hintIsRequirement
                        ? 'field-hint field-hint-strong'
                        : 'field-hint'
                    }
                  >
                    {field.hint}
                  </span>
                )}
              </label>
            ))}
          </div>
        </form>
      </div>
    </div>
  );
};

export default StepPersona;
