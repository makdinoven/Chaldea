import { megalinkNumber } from '../../../api/charactersPublic';

/**
 * FEAT-154 — the Скитальцы wax stamp plus the Megalink number (rule 27, D11).
 *
 * The number is DERIVED from the character id (`СК-{id:06d}`), never stored.
 * Before approval there is no id, so the passport says so instead of inventing
 * a placeholder number.
 *
 * `showNumber={false}` renders the stamp alone. The full passport uses that:
 * there the Megalink is a `passport-field` row in «Информация о персонаже»,
 * and repeating it under the portrait would read as a caption to the picture.
 */
interface PassportSealProps {
  characterId?: number | null;
  /** `compact` shrinks the seal for the grid card. */
  compact?: boolean;
  /** `false` = the wax stamp only; the number is printed by the caller. */
  showNumber?: boolean;
}

const PassportSeal = ({
  characterId,
  compact = false,
  showNumber = true,
}: PassportSealProps) => {
  const assigned = typeof characterId === 'number' && characterId > 0;

  return (
    <div className="flex items-center gap-3 sm:gap-4">
      <div
        className={`wax-seal ${compact ? 'scale-[0.62] -ml-3 -mr-2 sm:scale-75 sm:ml-0 sm:mr-0' : ''}`}
        aria-hidden="true"
      >
        <span className={compact ? 'text-base' : 'text-lg sm:text-xl'}>СК</span>
      </div>

      {showNumber ? (
        <div className="min-w-0">
          <div className="passport-field-label">Мегалинк</div>
          {assigned ? (
            <div
              className={`lore-heading ${compact ? 'text-base' : 'text-lg sm:text-xl'} tracking-[0.06em]`}
            >
              {megalinkNumber(characterId as number)}
            </div>
          ) : (
            <div className={`lore-body italic ${compact ? 'text-xs' : 'text-sm'} text-ink-muted`}>
              будет присвоен при регистрации
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
};

export default PassportSeal;
