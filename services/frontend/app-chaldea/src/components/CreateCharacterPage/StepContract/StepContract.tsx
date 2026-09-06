import { useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import useNavigateTo from '../../../hooks/useNavigateTo';
import { useAppSelector } from '../../../redux/store';
import {
  createCharacterRequest,
  type CharacterRequestPayload,
} from '../../../api/characterRequests';
import type { StartingPoint } from '../../../api/startingPoints';
import type { OriginCountry } from '../../../api/origins';
import {
  CharacterPassport,
  fromWizardDraft,
  type PassportKit,
  type PassportStats,
} from '../../CommonComponents/CharacterPassport';
import type { PersonaForm, RaceData, SubraceData } from '../types';

/**
 * FEAT-154 — step 6, «Контракт». Replaces `SubmitPage.tsx`.
 *
 * Two things happen here and nothing else: the player reads his own passport
 * back, and signs — which submits the application. The point of first
 * assignment and the law of the organisation moved to step 5, «Присяга»: they
 * are read and decided on, and next to the passport they were not being read
 * at all.
 *
 * The passport is the same `CharacterPassport` the moderator and every other
 * player will see (rule 26); the wizard feeds it through `fromWizardDraft`, so
 * nothing is re-fetched and nothing is fabricated.
 *
 * ⚠️ `avatar` carries the uploaded S3 URL or `null`. The literal `'string'` the
 * old page sent is gone, and an absent avatar is a valid application.
 */

interface StepContractProps {
  persona: PersonaForm;
  race: RaceData | null;
  subrace: SubraceData | null;
  origin: OriginCountry | null;
  gameClass: { id: number; name: string } | null;
  /** Live `/starter-kits/resolve` preview handed up by the «Путь» step. */
  kitPreview: PassportKit | null;
  /** Chosen on step 5 — shown on the passport, not editable here. */
  startLocation: StartingPoint | null;
  /** From `selectCurrentGameYear` — never a literal (§3.5). */
  currentGameYear: number | null;
  /**
   * FEAT-154 (task #19) — what stops the signature, or `null` when the
   * application is ready to file. Computed once by `useWizardValidation` in
   * `CreateCharacterPage` and handed down, so this step and the «Далее» gate
   * cannot drift into two different sets of required fields (rules 32-33).
   * This step deliberately owns no validation of its own any more.
   */
  submitBlocker: string | null;
  /** Lets the wizard drop the saved draft once the application is in. */
  onSubmitted?: () => void;
}

/** Blank string → `null`, so an untouched field is absent, not empty. */
const nullable = (value: string): string | null => {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
};

const toNullableNumber = (value: string): number | null => {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : null;
};

const StepContract = ({
  persona,
  race,
  subrace,
  origin,
  gameClass,
  kitPreview,
  startLocation,
  currentGameYear,
  submitBlocker,
  onSubmitted,
}: StepContractProps) => {
  const navigateTo = useNavigateTo();
  const userId = useAppSelector((state) => state.user.id);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const stats: PassportStats | null = useMemo(() => {
    const preset = subrace?.stat_preset;
    return preset ? ({ ...preset } as PassportStats) : null;
  }, [subrace]);

  const passportData = useMemo(
    () =>
      fromWizardDraft({
        name: persona.name.trim() || 'Без имени',
        avatarUrl: persona.avatarUrl,
        race: race ? { id: race.id_race, name: race.name } : null,
        subrace: subrace
          ? {
              id: subrace.id_subrace,
              name: subrace.name,
              image: subrace.image,
              typicalOriginIds: subrace.typical_origin_ids ?? null,
            }
          : null,
        gameClass,
        origin,
        stats,
        kitPreview,
        startLocation: startLocation ? { id: startLocation.id, name: startLocation.name } : null,
        skitaltsySinceYear: persona.skitaltsySinceYear,
        skitaltsySinceSegment: persona.skitaltsySinceSegment,
        sex: persona.sex || null,
        age: persona.age,
        height: persona.height,
        weight: persona.weight,
        appearance: persona.appearance,
        biography: persona.biography,
        personality: persona.personality,
      }),
    [persona, race, subrace, origin, gameClass, stats, kitPreview, startLocation],
  );

  /**
   * The single source of truth for «what is still missing», computed by
   * `useWizardValidation` (task #19). It names the step to go back to, and it
   * is the same value that keeps the «Вперёд» button shut — one set of rules,
   * one message. Soft signals (an unusual height, a rare origin, a debatable
   * tenure) never appear here: they are hints, not blocks.
   *
   * A missing race / subrace / class cannot actually be reached from here —
   * the gate would not have let the player onto this step — but the check
   * still stands as the last line before the network call.
   */
  const missing = submitBlocker;

  const handleSubmit = async () => {
    if (missing || !race || !subrace || !gameClass) {
      const message = missing ?? 'Заявка заполнена не полностью — вернитесь на предыдущие шаги.';
      setSubmitError(message);
      toast.error(message);
      return;
    }
    if (!userId) {
      const message = 'Сессия истекла — войдите заново, чтобы отправить заявку.';
      setSubmitError(message);
      toast.error(message);
      return;
    }

    const payload: CharacterRequestPayload = {
      user_id: userId,
      name: persona.name.trim(),
      id_race: race!.id_race,
      id_subrace: subrace!.id_subrace,
      id_class: gameClass!.id,
      appearance: persona.appearance.trim(),
      biography: nullable(persona.biography),
      personality: nullable(persona.personality),
      // `background` is no longer collected: «Предыстория» merged into
      // «Биография». The column stays nullable and the passport still renders
      // the text of characters who filled it in before the merge.
      sex: persona.sex || null,
      age: toNullableNumber(persona.age),
      height: nullable(persona.height),
      weight: nullable(persona.weight),
      // Optional by design: an upload failure never blocks the application.
      avatar: persona.avatarUrl,
      origin_id: origin?.id ?? null,
      start_location_id: startLocation?.id ?? null,
      skitaltsy_since_year: persona.skitaltsySinceYear,
      skitaltsy_since_segment: persona.skitaltsySinceSegment,
    };

    setSubmitting(true);
    setSubmitError(null);
    try {
      await createCharacterRequest(payload);
      toast.success(
        'Заявка подана. Следить за решением Координатора можно в «Моих заявках».',
      );
      onSubmitted?.();
      // FEAT-154 (task #20): «Мои заявки» now exists, so the player lands on the
      // status of what he just filed instead of a generic home page.
      navigateTo('/my-requests');
    } catch (err) {
      const message =
        err instanceof Error && err.message
          ? err.message
          : 'Не удалось отправить заявку. Попробуйте позже.';
      setSubmitError(message);
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="w-full flex flex-col gap-8 px-4 md:px-[60px]">
      {/* The passport — the same component the moderator and other players see */}
      <section className="flex flex-col gap-3">
        <h3 className="gold-text text-lg sm:text-xl font-semibold">Ваш паспорт Скитальца</h3>
        <p className="field-hint max-w-[720px]">
          Так вас увидят Координатор и другие Скитальцы. Мегалинк и дата регистрации
          появятся, когда заявку одобрят.
        </p>

        <CharacterPassport
          data={passportData}
          currentGameYear={currentGameYear}
          // The player's own contract: the posting they picked and the kit they
          // will be issued are the whole content of this step.
          audience="self"
          footer={
            <div className="flex flex-col items-center gap-3 w-full">
              {submitError && (
                <p className="text-site-red text-sm text-center max-w-[520px]">{submitError}</p>
              )}
              {!submitError && missing && (
                <p className="text-white/50 text-[13px] sm:text-sm text-center max-w-[520px]">{missing}</p>
              )}
              <button
                type="button"
                className="btn-blue"
                onClick={() => void handleSubmit()}
                disabled={submitting}
              >
                {submitting ? 'Отправка…' : 'Подписать контракт'}
              </button>
            </div>
          }
        />
      </section>
    </div>
  );
};

export default StepContract;
