import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { AnimatePresence, motion } from 'motion/react';
import useNavigateTo from '../../hooks/useNavigateTo';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { fetchRaces } from '../../redux/slices/racesSlice';
import { fetchOriginsThunk, selectOrigins } from '../../redux/slices/originsSlice';
import { selectCurrentGameYear, selectGameTimeError } from '../../redux/slices/gameTimeSlice';
import { fetchGameTime } from '../../redux/actions/gameTimeActions';
import { useRequireAuth } from '../../hooks/useRequireAuth';

import Prologue from './Prologue/Prologue';
import StepBlood from './StepBlood/StepBlood';
import StepOrigin from './StepOrigin/StepOrigin';
import StepPath from './StepPath/StepPath';
import StepPersona from './StepPersona/StepPersona';
import StepOath from './StepOath/StepOath';
import StepContract from './StepContract/StepContract';
import Pagination from './Pagination/Pagination';
import { useWizardValidation } from './useWizardValidation';
import {
  clearCharacterDraft,
  isDraftMeaningful,
  readCharacterDraft,
  useCharacterDraftAutosave,
  type DraftSnapshot,
} from './useCharacterDraft';

import type { PassportKit } from '../CommonComponents/CharacterPassport';
import type { StartingPoint } from '../../api/startingPoints';
import { WIZARD_STEP_TITLES } from './types';
import type { RaceData, PersonaForm, PageData } from './types';

/**
 * FEAT-154 — «Регистрация Скитальца».
 *
 * Task #17 delivered the prologue and steps 1-3 (Кровь / Родина / Путь);
 * task #18 replaced the pre-feature `BiographyPage` / `SubmitPage` with
 * `StepPersona` and `StepContract`. Task #19 turns the page into the actual
 * state machine of the wizard and adds the two things the steps could not own
 * themselves:
 *
 * 1. **Gating (rules 32-33).** Until now the pagination dots jumped anywhere,
 *    contract included, past every empty field. Forward movement — the «Вперёд»
 *    button *and* the dots — is now capped by `maxReachableIndex`, and the same
 *    `useWizardValidation` result is handed to `StepContract`, so the block on
 *    «Далее» and the block on the signature are literally one set of rules.
 *    **Going back is never gated.**
 * 2. **Draft autosave (rule 35).** Every field survives an accidental F5. The
 *    draft is client-only (R9) and is dropped the moment the application is
 *    filed — see `useCharacterDraft`.
 *
 * The mock `INITIAL_CLASSES` is gone for good — every entity here comes from
 * the backend.
 */

const BLANK_PERSONA: PersonaForm = {
  biography: '',
  personality: '',
  appearance: '',
  name: '',
  age: '',
  height: '',
  weight: '',
  sex: '',
  avatarUrl: null,
  skitaltsySinceYear: null,
  skitaltsySinceSegment: null,
};

export default function CreateCharacterPage() {
  const navigateTo = useNavigateTo();
  const [prologueSeen, setPrologueSeen] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);

  const [selectedRaceId, setSelectedRaceId] = useState<number>(0);
  const [selectedSubraceId, setSelectedSubraceId] = useState<number | null>(null);
  const [selectedOriginId, setSelectedOriginId] = useState<number | null>(null);
  const [selectedClassId, setSelectedClassId] = useState<number | null>(null);
  const [selectedClassName, setSelectedClassName] = useState<string>('');
  // The live resolver preview, carried into the passport on step 6. Deliberately
  // NOT part of the draft: `StepPath` re-resolves it from the backend, and a
  // stale kit in localStorage would be exactly the lie rule 12 forbids.
  const [kitPreview, setKitPreview] = useState<PassportKit | null>(null);
  const [startLocation, setStartLocation] = useState<StartingPoint | null>(null);

  const [persona, setPersona] = useState<PersonaForm>(BLANK_PERSONA);

  // FEAT-154 (#15): races come from the shared `fetchRaces` thunk instead of a
  // raw axios call, so the wizard and the admin pages read one cached source.
  const dispatch = useAppDispatch();
  const races: RaceData[] = useAppSelector((state) => state.races.races);
  const loading = useAppSelector((state) => state.races.loading);
  const error = useAppSelector((state) => state.races.error);
  const origins = useAppSelector(selectOrigins);
  // ⚠️ The current in-game year is read at runtime and never hardcoded (§3.5).
  const currentGameYear = useAppSelector(selectCurrentGameYear);
  const gameTimeLoaded = useAppSelector((state) => state.gameTime.computed !== null);
  // Shown by the tenure field: a dead clock must not read as a slow one.
  const gameTimeError = useAppSelector(selectGameTimeError);
  const userId = useAppSelector((state) => state.user.id);
  const notifiedErrorRef = useRef<string | null>(null);

  useRequireAuth();

  useEffect(() => {
    dispatch(fetchRaces());
  }, [dispatch]);

  // The origin registry is loaded by the page, not only by step 2: the gate of
  // rule 33 needs to know whether the registry answered at all, even when the
  // player has not opened «Родина» yet. `fetchOriginsThunk` is a no-op once the
  // slice is populated, so step 2 does not fetch twice.
  useEffect(() => {
    if (origins.length === 0) dispatch(fetchOriginsThunk());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch]);

  // The tenure bounds and the passport both need the game clock.
  useEffect(() => {
    if (!gameTimeLoaded) dispatch(fetchGameTime());
  }, [dispatch, gameTimeLoaded]);

  // ── draft restore (rule 35) ──────────────────────────────────────────────
  // One attempt, once the session is known, before autosave is switched on —
  // otherwise the blank initial state would overwrite the stored draft.
  const [draftReady, setDraftReady] = useState(false);
  const [draftSubmitted, setDraftSubmitted] = useState(false);
  const restoreAttemptedRef = useRef(false);

  useEffect(() => {
    if (restoreAttemptedRef.current) return;
    if (userId === null) return; // wait for the session before touching the draft
    restoreAttemptedRef.current = true;

    const draft = readCharacterDraft(userId);
    if (draft && isDraftMeaningful(draft)) {
      setPrologueSeen(true);
      // The stored index is clamped against the CURRENT number of steps, which
      // is why splitting «Контракт» into «Присяга» + «Контракт» did not need a
      // draft version bump: a draft written when the wizard had five steps
      // carries an index of at most 4, which is still a valid step. A future
      // change that *removes* steps is covered by the same clamp. On top of
      // that, `maxReachableIndex` pulls the player back to the first
      // incomplete step anyway.
      setCurrentIndex(
        Math.min(Math.max(0, Math.trunc(draft.currentIndex)), WIZARD_STEP_TITLES.length - 1),
      );
      setSelectedRaceId(draft.selectedRaceId);
      setSelectedSubraceId(draft.selectedSubraceId);
      setSelectedOriginId(draft.selectedOriginId);
      setSelectedClassId(draft.selectedClassId);
      setSelectedClassName(draft.selectedClassName);
      setStartLocation(draft.startLocation);
      setPersona(draft.persona);
      toast('Черновик анкеты восстановлен — можно продолжить с того же места.', {
        icon: '📜',
      });
    } else if (draft) {
      // An empty leftover: nothing to restore and nothing to keep.
      clearCharacterDraft();
    }
    setDraftReady(true);
  }, [userId]);

  const draftSnapshot: DraftSnapshot = useMemo(
    () => ({
      currentIndex,
      prologueSeen,
      selectedRaceId,
      selectedSubraceId,
      selectedOriginId,
      selectedClassId,
      selectedClassName,
      startLocation,
      persona,
    }),
    [
      currentIndex,
      prologueSeen,
      selectedRaceId,
      selectedSubraceId,
      selectedOriginId,
      selectedClassId,
      selectedClassName,
      startLocation,
      persona,
    ],
  );

  useCharacterDraftAutosave(draftSnapshot, userId, draftReady && !draftSubmitted);

  // Preselect the first race once the list arrives; picking a race preselects
  // its first branch of blood so the panel is never half-empty. A restored
  // draft already carries a race, so this never overwrites it.
  useEffect(() => {
    if (races.length > 0 && selectedRaceId === 0) {
      setSelectedRaceId(races[0].id_race);
      setSelectedSubraceId(races[0].subraces[0]?.id_subrace ?? null);
    }
  }, [races, selectedRaceId]);

  // The load error must always reach the player (Frontend Error Display rule).
  useEffect(() => {
    if (error && notifiedErrorRef.current !== error) {
      notifiedErrorRef.current = error;
      toast.error(error);
    }
    if (!error) notifiedErrorRef.current = null;
  }, [error]);

  const selectedRace = races.find((race) => race.id_race === selectedRaceId) ?? null;
  const selectedSubrace =
    selectedRace?.subraces.find((subrace) => subrace.id_subrace === selectedSubraceId) ?? null;
  const selectedOrigin = useMemo(
    () => origins.find((origin) => origin.id === selectedOriginId) ?? null,
    [origins, selectedOriginId],
  );

  // ── the single set of gating rules (rules 32-33) ─────────────────────────
  const validation = useWizardValidation({
    race: selectedRace,
    subrace: selectedSubrace,
    originId: selectedOriginId,
    originsAvailable: origins.length > 0,
    classId: selectedClassId,
    persona,
    currentGameYear,
  });

  // Clearing a field on an earlier step must not leave the player standing on a
  // step they can no longer justify. Only once the catalogue has answered —
  // before that everything looks «incomplete» merely because nothing loaded.
  useEffect(() => {
    if (races.length === 0) return;
    if (currentIndex > validation.maxReachableIndex) {
      setCurrentIndex(validation.maxReachableIndex);
    }
  }, [races.length, currentIndex, validation.maxReachableIndex]);

  const handleSelectRace = (raceId: number) => {
    setSelectedRaceId(raceId);
    const race = races.find((item) => item.id_race === raceId);
    setSelectedSubraceId(race?.subraces[0]?.id_subrace ?? null);
  };

  const handleSelectClass = (classId: number, className: string) => {
    setSelectedClassId(classId);
    setSelectedClassName(className);
  };

  const handleBlocked = useCallback((message: string) => {
    toast.error(message);
  }, []);

  /** The application is filed — the draft has done its job and must not linger. */
  const handleSubmitted = useCallback(() => {
    setDraftSubmitted(true);
    clearCharacterDraft();
  }, []);

  const handleRestart = () => {
    clearCharacterDraft();
    setCurrentIndex(0);
    setPrologueSeen(false);
    setSelectedRaceId(races[0]?.id_race ?? 0);
    setSelectedSubraceId(races[0]?.subraces[0]?.id_subrace ?? null);
    setSelectedOriginId(null);
    setSelectedClassId(null);
    setSelectedClassName('');
    setKitPreview(null);
    setStartLocation(null);
    setPersona(BLANK_PERSONA);
    toast('Черновик удалён. Начинаем заново.');
  };

  const pages: PageData[] = WIZARD_STEP_TITLES.map((pageTitle, pageId) => ({
    pageId,
    pageTitle,
  }));

  const renderStep = (id: number) => {
    if (loading && races.length === 0) {
      return (
        <div className="flex items-center justify-center py-20">
          <div className="w-10 h-10 border-4 border-white/30 border-t-white rounded-full animate-spin" />
        </div>
      );
    }
    if (error && races.length === 0) {
      return <p className="text-site-red text-center py-10 px-4">{error}</p>;
    }

    switch (id) {
      case 0:
        return (
          <StepBlood
            races={races}
            selectedRaceId={selectedRaceId}
            selectedSubraceId={selectedSubraceId}
            onSelectRace={handleSelectRace}
            onSelectSubrace={setSelectedSubraceId}
          />
        );
      case 1:
        return (
          <StepOrigin
            selectedOriginId={selectedOriginId}
            onSelectOrigin={setSelectedOriginId}
            selectedSubrace={selectedSubrace}
          />
        );
      case 2:
        return (
          <StepPath
            selectedClassId={selectedClassId}
            onSelectClass={handleSelectClass}
            selectedOriginId={selectedOriginId}
            selectedOriginName={selectedOrigin?.name ?? null}
            onKitResolved={setKitPreview}
          />
        );
      case 3:
        return (
          <StepPersona
            value={persona}
            onChange={setPersona}
            selectedSubrace={selectedSubrace}
            raceName={selectedRace?.name ?? null}
            currentGameYear={currentGameYear}
            gameTimeError={gameTimeError}
          />
        );
      case 4:
        return (
          <StepOath
            startLocation={startLocation}
            onSelectStartLocation={setStartLocation}
            selectedOriginId={selectedOriginId}
          />
        );
      case 5:
        return (
          <StepContract
            persona={persona}
            race={selectedRace}
            subrace={selectedSubrace}
            origin={selectedOrigin}
            gameClass={
              selectedClassId ? { id: selectedClassId, name: selectedClassName } : null
            }
            kitPreview={kitPreview}
            startLocation={startLocation}
            currentGameYear={currentGameYear}
            submitBlocker={validation.submitBlocker}
            onSubmitted={handleSubmitted}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="rounded-card py-[37px] pb-[70px] bg-site-bg flex flex-col items-center">
      {/* Header section */}
      <div className="relative flex flex-col items-center justify-center gap-[15px] pb-[44px] mb-[15px] after:content-[''] after:absolute after:bottom-0 after:left-1/2 after:h-px after:bg-gradient-to-r after:from-transparent after:via-[#999] after:to-transparent after:z-[1] after:-translate-x-1/2 after:w-[70%]">
        <h1 className="gold-text text-2xl sm:text-[32px] font-bold uppercase text-center">
          Регистрация Скитальца
        </h1>
        <p className="w-[90%] sm:w-[45%] text-center text-base font-normal text-white">
          Здесь вы вступаете в организацию Скитальцев и создаёте героя, которым начнёте
          исследование Халдеи. Прежде чем отправить заявку на проверку, рекомендуем
          ознакомиться с{' '}
          <a
            onClick={() => navigateTo('/rules')}
            className="underline cursor-pointer hover:text-site-blue transition-colors"
          >
            правилами
          </a>
          .
        </p>
      </div>

      {!prologueSeen ? (
        <div className="w-full py-6">
          <Prologue onBegin={() => setPrologueSeen(true)} />
        </div>
      ) : (
        <>
          {/* Step title */}
          <h2 className="gold-text text-xl sm:text-[28px] font-semibold text-center mb-2 px-4">
            {`Шаг ${currentIndex + 1}. ${pages[currentIndex].pageTitle}`}
          </h2>

          {/* The draft is silent by design; this is the only place it is visible. */}
          <p className="field-hint mx-auto max-w-[720px] mb-8 px-4">
            Анкета сохраняется в этом браузере — перезагрузка страницы ничего не сотрёт.{' '}
            <button
              type="button"
              onClick={handleRestart}
              className="underline hover:text-site-blue transition-colors"
            >
              Начать заново
            </button>
          </p>

          {/* Page content */}
          <div className="flex flex-col items-center w-full flex-1 justify-between mb-10">
            <AnimatePresence mode="wait">
              <motion.div
                key={currentIndex}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.25 }}
                className="w-full"
              >
                {renderStep(pages[currentIndex].pageId)}
              </motion.div>
            </AnimatePresence>
          </div>

          {/* Pagination — forward movement is capped by the validation (rule 33) */}
          <Pagination
            pages={pages}
            currentIndex={currentIndex}
            onIndexChange={setCurrentIndex}
            maxReachableIndex={validation.maxReachableIndex}
            blockedMessage={validation.submitBlocker}
            onBlocked={handleBlocked}
          />
        </>
      )}
    </div>
  );
}
