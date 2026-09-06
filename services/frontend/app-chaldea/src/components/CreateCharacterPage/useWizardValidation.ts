import { useMemo } from 'react';
import { validateTenure } from './StepPersona/TenureField';
import { WIZARD_STEP_TITLES } from './types';
import type { PersonaForm, RaceData, SubraceData } from './types';

/**
 * FEAT-154 (task #19) — the one place that decides whether the wizard may move
 * forward (rule 33) and whether the contract may be signed (rule 32).
 *
 * **One set of rules, not two.** `StepContract` used to carry its own
 * pre-submit check; it now reads `submitBlocker` from here, so the message that
 * stops the «Далее» button and the message that stops «Подписать контракт» can
 * never disagree.
 *
 * ### What blocks and what does not
 *
 * Blocking is reserved for fields the application genuinely cannot be filed
 * without — the ones §3.2 rejects with a 400, plus the three application texts
 * the «Личность» step marks with a star. Everything the feature calls a *soft*
 * signal stays out of this file on purpose:
 *
 * - a height outside the subrace range (rule 15) — a hint, the Coordinator judges;
 * - an origin that is not typical for the subrace (rule 11) — «редкий выбор», allowed;
 * - the believability of the tenure (rule 24) — the moderator's call, not the form's.
 *
 * The tenure *is* checked here, but only through `validateTenure`, which covers
 * exactly the two impossible cases the backend answers 400 to (a year past the
 * live game clock, a tenure longer than the character's age). Letting those
 * through would only trade a clear Russian hint for a server error.
 *
 * There is deliberately one entry per step, so `stepBlockers` and
 * `WIZARD_STEP_TITLES` stay the same length — the step indexes in every message
 * come from that same array.
 *
 * The origin and the starting point are optional on the wire (`origin_id` and
 * `start_location_id` are both nullable). The origin is still gated — it is the
 * entire point of step 2 and it decides the starter kit — but **only while the
 * registry actually answered**: if `/locations/origins` is down or empty, the
 * gate stands down rather than trapping the player in a wizard they cannot
 * finish. The starting point is never gated: §3.6 assigns a default.
 */

export interface WizardValidationInput {
  race: RaceData | null;
  subrace: SubraceData | null;
  originId: number | null;
  /** `false` while `/locations/origins` returned nothing — the gate stands down. */
  originsAvailable: boolean;
  classId: number | null;
  persona: PersonaForm;
  /** From `selectCurrentGameYear` — never a literal (§3.5). */
  currentGameYear: number | null;
}

export interface WizardValidation {
  /** One blocking message per step, in step order; `null` when the step is complete. */
  stepBlockers: (string | null)[];
  /** Index of the earliest incomplete step, or `null` when every step is complete. */
  firstBlockedStep: number | null;
  /**
   * The furthest step the player may open right now. Equals the first blocked
   * step — you can stand on an incomplete step, you just cannot walk past it.
   * Going **back** is always allowed and is not routed through this value.
   */
  maxReachableIndex: number;
  /** What stops the submit, or `null` when the application is ready to file. */
  submitBlocker: string | null;
}

/** Matches `CharacterRequest.name` — `String(20)` in character-service. */
const NAME_MAX_LENGTH = 20;

/** Every message names the step, so the player knows where to go back to. */
const onStep = (index: number, what: string): string =>
  `Шаг ${index + 1} «${WIZARD_STEP_TITLES[index]}»: ${what}`;

/**
 * Same prefix for a message that is already a full sentence (and may open with
 * a proper noun) — lower-casing it would mangle «Скитальцы».
 */
const onStepSentence = (index: number, sentence: string): string =>
  `Шаг ${index + 1} «${WIZARD_STEP_TITLES[index]}». ${sentence}`;

const bloodBlocker = (race: RaceData | null, subrace: SubraceData | null): string | null => {
  if (!race) return onStep(0, 'выберите расу.');
  if (!subrace) return onStep(0, 'выберите ветвь крови (подрасу).');
  return null;
};

const originBlocker = (originId: number | null, originsAvailable: boolean): string | null => {
  if (!originsAvailable) return null;
  if (originId === null) return onStep(1, 'выберите страну происхождения.');
  return null;
};

const pathBlocker = (classId: number | null): string | null =>
  classId === null ? onStep(2, 'выберите класс.') : null;

const personaBlocker = (
  persona: PersonaForm,
  currentGameYear: number | null,
): string | null => {
  const name = persona.name.trim();
  if (!name) return onStep(3, 'укажите имя персонажа.');
  if (name.length > NAME_MAX_LENGTH) {
    return onStep(3, `имя не длиннее ${NAME_MAX_LENGTH} символов.`);
  }
  if (!persona.appearance.trim()) return onStep(3, 'опишите внешность персонажа.');
  if (!persona.biography.trim()) return onStep(3, 'заполните биографию.');
  if (!persona.personality.trim()) return onStep(3, 'заполните характер.');

  const age = persona.age.trim() ? Number(persona.age) : NaN;
  const tenureError = validateTenure(
    persona.skitaltsySinceYear,
    persona.skitaltsySinceSegment,
    currentGameYear,
    Number.isFinite(age) ? Math.trunc(age) : null,
  );
  return tenureError ? onStepSentence(3, tenureError) : null;
};

export const useWizardValidation = (input: WizardValidationInput): WizardValidation => {
  const { race, subrace, originId, originsAvailable, classId, persona, currentGameYear } = input;

  return useMemo(() => {
    const stepBlockers: (string | null)[] = [
      bloodBlocker(race, subrace),
      originBlocker(originId, originsAvailable),
      pathBlocker(classId),
      personaBlocker(persona, currentGameYear),
      // «Присяга» requires nothing of its own: the starting point is optional
      // and a default is assigned at approval (§3.6), and the law is read, not
      // filled in. The step therefore never blocks the way to «Контракт».
      null,
      // «Контракт» is the signature itself — everything it needs was checked
      // above, and `submitBlocker` is exactly the first of those messages.
      null,
    ];

    const blockedAt = stepBlockers.findIndex((blocker) => blocker !== null);
    const firstBlockedStep = blockedAt === -1 ? null : blockedAt;

    return {
      stepBlockers,
      firstBlockedStep,
      maxReachableIndex:
        firstBlockedStep === null ? WIZARD_STEP_TITLES.length - 1 : firstBlockedStep,
      submitBlocker: firstBlockedStep === null ? null : stepBlockers[firstBlockedStep],
    };
  }, [race, subrace, originId, originsAvailable, classId, persona, currentGameYear]);
};
