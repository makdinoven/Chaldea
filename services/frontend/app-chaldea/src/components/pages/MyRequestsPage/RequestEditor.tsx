import { useMemo, useState, type ReactNode } from 'react';
import toast from 'react-hot-toast';
import {
  updateCharacterRequest,
  type CharacterRequestUpdatePayload,
  type MyCharacterRequest,
} from '../../../api/characterRequests';
import type { StartingPoint } from '../../../api/startingPoints';
import { useAppSelector } from '../../../redux/store';
import { selectOrigins } from '../../../redux/slices/originsSlice';
import StepBlood from '../../CreateCharacterPage/StepBlood/StepBlood';
import StepOrigin from '../../CreateCharacterPage/StepOrigin/StepOrigin';
import StepPath from '../../CreateCharacterPage/StepPath/StepPath';
import StepPersona from '../../CreateCharacterPage/StepPersona/StepPersona';
import StartingPointPicker from '../../CreateCharacterPage/StepOath/StartingPointPicker';
import { useWizardValidation } from '../../CreateCharacterPage/useWizardValidation';
import { WIZARD_STEP_TITLES } from '../../CreateCharacterPage/types';
import type { PersonaForm, RaceData } from '../../CreateCharacterPage/types';

/**
 * FEAT-154 (task #20) — editing a **rejected** application (rules 29-30).
 *
 * The whole point of rule 30 is «не заполняя всё заново», so this is not a new
 * form: it is the wizard's own five steps, prefilled from the stored request
 * and stacked on one scrollable sheet instead of being walked through a step
 * machine. Reusing `StepBlood` / `StepOrigin` / `StepPath` / `StepPersona` /
 * `StartingPointPicker` verbatim means the avatar upload, the tenure bounds,
 * the subrace look memo, the starter-kit preview and the «редкий выбор» hint
 * all behave exactly as they did at creation time — a bespoke compact form
 * would have had to reimplement every one of them and would drift the moment
 * the wizard changes.
 *
 * Gating is the same `useWizardValidation` the wizard uses (rules 32-33), so
 * the message that blocks «Отправить заново» is literally the message that
 * blocks «Далее» in the wizard.
 *
 * ⚠️ Rule 30a: only a `rejected` request may be edited — the backend answers
 * 409 otherwise. The caller renders this editor for nothing else.
 */

interface RequestEditorProps {
  request: MyCharacterRequest;
  races: RaceData[];
  racesLoading: boolean;
  racesError: string | null;
  /** From `selectCurrentGameYear` — never a literal (§3.5). */
  currentGameYear: number | null;
  /** From `selectGameTimeError` — set when the game clock failed to load. */
  gameTimeError?: string | null;
  onCancel: () => void;
  /** Handed the request as the backend returned it — `pending`, reason cleared. */
  onSaved: (updated: MyCharacterRequest) => void;
}

const numberToInput = (value: number | null): string =>
  value === null || value === undefined ? '' : String(value);

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

const personaFromRequest = (request: MyCharacterRequest): PersonaForm => ({
  name: request.name ?? '',
  appearance: request.appearance ?? '',
  biography: request.biography ?? '',
  personality: request.personality ?? '',
  sex: request.sex ?? '',
  age: numberToInput(request.age),
  height: request.height ?? '',
  weight: request.weight ?? '',
  avatarUrl: request.avatar ?? null,
  skitaltsySinceYear: request.skitaltsy_since_year ?? null,
  skitaltsySinceSegment: request.skitaltsy_since_segment ?? null,
});

/** One stacked section, titled after the wizard step it came from. */
const EditorSection = ({
  index,
  children,
}: {
  index: number;
  children: ReactNode;
}) => (
  <section className="flex w-full flex-col gap-4">
    <h3 className="gold-text px-4 text-lg font-semibold sm:text-xl">
      {`${index + 1}. ${WIZARD_STEP_TITLES[index]}`}
    </h3>
    {children}
  </section>
);

const RequestEditor = ({
  request,
  races,
  racesLoading,
  racesError,
  currentGameYear,
  gameTimeError = null,
  onCancel,
  onSaved,
}: RequestEditorProps) => {
  const origins = useAppSelector(selectOrigins);

  const [selectedRaceId, setSelectedRaceId] = useState<number>(request.id_race ?? 0);
  const [selectedSubraceId, setSelectedSubraceId] = useState<number | null>(
    request.id_subrace ?? null,
  );
  const [selectedOriginId, setSelectedOriginId] = useState<number | null>(
    request.origin_id ?? null,
  );
  const [selectedClassId, setSelectedClassId] = useState<number | null>(
    request.id_class ?? null,
  );
  const [startLocationId, setStartLocationId] = useState<number | null>(
    request.start_location_id ?? null,
  );
  const [persona, setPersona] = useState<PersonaForm>(() => personaFromRequest(request));

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const selectedRace = races.find((race) => race.id_race === selectedRaceId) ?? null;
  const selectedSubrace =
    selectedRace?.subraces.find((subrace) => subrace.id_subrace === selectedSubraceId) ?? null;
  const selectedOrigin = useMemo(
    () => origins.find((origin) => origin.id === selectedOriginId) ?? null,
    [origins, selectedOriginId],
  );

  const validation = useWizardValidation({
    race: selectedRace,
    subrace: selectedSubrace,
    originId: selectedOriginId,
    originsAvailable: origins.length > 0,
    classId: selectedClassId,
    persona,
    currentGameYear,
  });

  const handleSelectRace = (raceId: number) => {
    setSelectedRaceId(raceId);
    // Switching the race invalidates the branch of blood — preselect the first
    // one so the panel is never half-empty, exactly as the wizard does.
    const race = races.find((item) => item.id_race === raceId);
    setSelectedSubraceId(race?.subraces[0]?.id_subrace ?? null);
  };

  const handleSelectStartLocation = (point: StartingPoint | null) => {
    setStartLocationId(point?.id ?? null);
  };

  const handleSave = async () => {
    if (validation.submitBlocker) {
      setSaveError(validation.submitBlocker);
      toast.error(validation.submitBlocker);
      return;
    }
    if (!selectedRace || !selectedSubrace || selectedClassId === null) {
      const message = 'Заявка заполнена не полностью — проверьте расу, подрасу и класс.';
      setSaveError(message);
      toast.error(message);
      return;
    }

    const payload: CharacterRequestUpdatePayload = {
      name: persona.name.trim(),
      id_race: selectedRace.id_race,
      id_subrace: selectedSubrace.id_subrace,
      id_class: selectedClassId,
      appearance: persona.appearance.trim(),
      biography: nullable(persona.biography),
      personality: nullable(persona.personality),
      // «Предыстория» is no longer an editable field — it merged into
      // «Биография». The stored text is echoed back UNCHANGED rather than
      // omitted: `resubmit_character_request` overwrites every field in
      // `EDITABLE_REQUEST_FIELDS` with whatever the payload carries, so an
      // omitted `background` would arrive as `None` and erase what the player
      // wrote before the merge. The passport still displays it.
      background: request.background ?? null,
      sex: persona.sex || null,
      age: toNullableNumber(persona.age),
      height: nullable(persona.height),
      weight: nullable(persona.weight),
      // Optional by design: an upload failure never blocks the application.
      avatar: persona.avatarUrl,
      origin_id: selectedOriginId,
      start_location_id: startLocationId,
      skitaltsy_since_year: persona.skitaltsySinceYear,
      skitaltsy_since_segment: persona.skitaltsySinceSegment,
    };

    setSaving(true);
    setSaveError(null);
    try {
      const updated = await updateCharacterRequest(request.id, payload);
      toast.success('Заявка отправлена на повторное рассмотрение.');
      onSaved(updated);
    } catch (error) {
      // Every failure reaches the player — 403 / 404 / 409 (rule 30a) / 400 all
      // arrive as a Russian message from `apiErrorMessage`.
      const message =
        error instanceof Error && error.message
          ? error.message
          : 'Не удалось сохранить заявку. Попробуйте позже.';
      setSaveError(message);
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  if (racesLoading && races.length === 0) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-white/30 border-t-white" />
      </div>
    );
  }

  if (racesError && races.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 py-12">
        <p className="text-site-red px-4 text-center text-sm">{racesError}</p>
        <button type="button" className="btn-line w-auto px-5" onClick={onCancel}>
          Вернуться к заявкам
        </button>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-8">
      <div className="flex flex-col gap-3 px-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h2 className="gold-text text-xl font-semibold sm:text-2xl">
            Исправление заявки
          </h2>
          <p className="field-hint mt-1">
            Всё, что вы заполняли раньше, уже здесь — поправьте только то, на что указал
            Координатор, и отправьте заявку заново.
          </p>
        </div>
        <button
          type="button"
          className="btn-line w-full shrink-0 px-5 sm:w-auto"
          onClick={onCancel}
          disabled={saving}
        >
          Отмена
        </button>
      </div>

      {request.rejection_reason ? (
        <div className="mx-4 rounded-card border border-site-red/40 bg-site-red/10 p-4">
          <p className="text-site-red text-xs font-semibold uppercase">Причина отказа</p>
          {/* Moderator-written text — always plain text, never HTML (R9). */}
          <p className="text-white mt-2 whitespace-pre-wrap break-words text-sm">
            {request.rejection_reason}
          </p>
        </div>
      ) : null}

      <EditorSection index={0}>
        <StepBlood
          races={races}
          selectedRaceId={selectedRaceId}
          selectedSubraceId={selectedSubraceId}
          onSelectRace={handleSelectRace}
          onSelectSubrace={setSelectedSubraceId}
        />
      </EditorSection>

      <EditorSection index={1}>
        <StepOrigin
          selectedOriginId={selectedOriginId}
          onSelectOrigin={setSelectedOriginId}
          selectedSubrace={selectedSubrace}
        />
      </EditorSection>

      <EditorSection index={2}>
        <StepPath
          selectedClassId={selectedClassId}
          onSelectClass={(classId) => setSelectedClassId(classId)}
          selectedOriginId={selectedOriginId}
          selectedOriginName={selectedOrigin?.name ?? null}
        />
      </EditorSection>

      <EditorSection index={3}>
        <StepPersona
          value={persona}
          onChange={setPersona}
          selectedSubrace={selectedSubrace}
          raceName={selectedRace?.name ?? null}
          currentGameYear={currentGameYear}
          gameTimeError={gameTimeError}
        />
      </EditorSection>

      <EditorSection index={4}>
        <div className="flex flex-col gap-3 px-4 md:px-[60px]">
          <p className="field-hint max-w-[720px]">
            Точка первого назначения. Список утверждён организацией — позже мир открыт
            целиком.
          </p>
          <StartingPointPicker
            selectedId={startLocationId}
            onSelect={handleSelectStartLocation}
            originId={selectedOriginId}
          />
        </div>
      </EditorSection>

      <div className="flex flex-col items-center gap-3 px-4 pb-4">
        {saveError ? (
          <p className="text-site-red max-w-[520px] text-center text-sm">{saveError}</p>
        ) : null}
        {!saveError && validation.submitBlocker ? (
          <p className="text-white/50 max-w-[520px] text-center text-[13px] sm:text-sm">
            {validation.submitBlocker}
          </p>
        ) : null}
        <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
          <button
            type="button"
            className="btn-blue disabled:opacity-50"
            onClick={() => void handleSave()}
            disabled={saving}
          >
            {saving ? 'Отправка…' : 'Отправить заново'}
          </button>
          <button
            type="button"
            className="btn-line disabled:opacity-50"
            onClick={onCancel}
            disabled={saving}
          >
            Отмена
          </button>
        </div>
      </div>
    </div>
  );
};

export default RequestEditor;
