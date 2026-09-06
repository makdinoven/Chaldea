import type { SubraceData } from '../types';

/**
 * FEAT-154 (task #18) — the look memo that stays next to the appearance field
 * (rules 16-17).
 *
 * Rule 17 in one line: `distinctive_features` is the appearance-only note, and
 * when it is not filled in yet the ordinary subrace `description` is shown
 * instead — the feature works before the content lands, it just reads broader.
 *
 * Parchment, because this is an extract from the Скитальцы register, not a UI
 * panel (DESIGN-SYSTEM §16).
 */

interface SubraceLookNoteProps {
  subrace: SubraceData | null;
  raceName?: string | null;
}

const SubraceLookNote = ({ subrace, raceName }: SubraceLookNoteProps) => {
  if (!subrace) {
    return (
      <div className="gray-bg rounded-card p-4">
        <p className="text-white/50 text-sm">
          Памятка об облике появится, когда на шаге «Кровь» будет выбрана подраса.
        </p>
      </div>
    );
  }

  const features = subrace.distinctive_features?.trim();
  const fallback = subrace.description?.trim();
  const body = features || fallback || null;
  /** Only the dedicated field is «отличительные особенности» (rule 17). */
  const isFallback = !features && Boolean(fallback);

  const hasRange =
    typeof subrace.height_min === 'number' && typeof subrace.height_max === 'number';

  return (
    <aside className="book-page rounded-card shadow-page p-4 sm:p-6 flex flex-col gap-3">
      <div className="flex items-center gap-3">
        {subrace.image && (
          <img
            src={subrace.image}
            alt={`Подраса: ${subrace.name}`}
            className="w-14 h-14 sm:w-16 sm:h-16 rounded-full object-cover shrink-0"
          />
        )}
        <div className="min-w-0">
          <h4 className="lore-heading text-lg sm:text-xl truncate">{subrace.name}</h4>
          <p className="text-ink-muted text-[11px] uppercase tracking-[0.08em]">
            {isFallback ? 'Общее описание подрасы' : 'Отличительные особенности'}
            {raceName ? ` · ${raceName}` : ''}
          </p>
        </div>
      </div>

      <div className="lore-divider" />

      <p className="lore-body text-[15px] sm:text-base whitespace-pre-wrap">
        {body ?? 'Об облике этой подрасы в реестре пока нет записей.'}
      </p>

      {hasRange && (
        <p className="text-ink-muted text-sm">
          Характерный рост: {subrace.height_min}–{subrace.height_max} см.
        </p>
      )}
    </aside>
  );
};

export default SubraceLookNote;
