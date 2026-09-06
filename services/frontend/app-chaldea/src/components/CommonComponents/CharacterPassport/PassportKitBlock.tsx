import type { PassportKit } from './types';

/**
 * FEAT-154 — the starter kit as printed on the passport (rules 12, 12d).
 *
 * The heading changes with WHAT the kit is, which is the whole point of
 * `starterKitIsSnapshot`:
 *
 * - `null`  → the wizard preview. Nothing is granted yet → «Что будет выдано».
 * - `true`  → the frozen record of what was actually issued at approval.
 * - `false` → the same record, but reconstructed for a character created before
 *   this feature (D18). The passport says so in a muted caption instead of
 *   passing a live re-resolve off as the original document.
 */
interface PassportKitBlockProps {
  kit?: PassportKit | null;
  isSnapshot?: boolean | null;
}

const PassportKitBlock = ({ kit, isSnapshot }: PassportKitBlockProps) => {
  if (!kit) return null;

  const isPreview = isSnapshot === null || isSnapshot === undefined;
  const isEmpty = kit.items.length === 0 && kit.skills.length === 0 && kit.currency <= 0;

  return (
    <section>
      <h3 className="lore-heading text-lg sm:text-xl">
        {isPreview ? 'Что будет выдано' : 'Выдано при вступлении'}
      </h3>

      {isSnapshot === false ? (
        <p className="lore-body mt-1 text-xs italic text-ink-muted">
          Запись восстановлена по реестру — оригинал выдачи не сохранился.
        </p>
      ) : null}

      {isEmpty ? (
        <p className="lore-body mt-2 text-sm text-ink-muted">Набор не назначен.</p>
      ) : (
        <>
          {kit.items.length > 0 ? (
            <ul className="mt-3 flex flex-col gap-2">
              {kit.items.map((item) => (
                <li key={`item-${item.id}`} className="flex items-center gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-[6px] border border-ink/20 bg-parchment-light">
                    {item.imageUrl ? (
                      <img
                        src={item.imageUrl}
                        alt=""
                        className="h-full w-full object-cover"
                        loading="lazy"
                      />
                    ) : (
                      <span className="lore-heading text-xs text-ink-muted">?</span>
                    )}
                  </span>
                  <span className="lore-body min-w-0 flex-1 break-words">{item.name}</span>
                  {item.quantity > 1 ? (
                    <span className="lore-body shrink-0 text-sm text-ink-muted">
                      ×{item.quantity}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}

          {kit.skills.length > 0 ? (
            <>
              <p className="passport-field-label mt-4 block">Навыки</p>
              <ul className="mt-2 flex flex-wrap gap-2">
                {kit.skills.map((skill) => (
                  <li key={`skill-${skill.id}`} className="lore-badge">
                    {skill.iconUrl ? (
                      <img src={skill.iconUrl} alt="" className="h-4 w-4 object-contain" />
                    ) : null}
                    {skill.name}
                  </li>
                ))}
              </ul>
            </>
          ) : null}

          {kit.currency > 0 ? (
            <div className="passport-field mt-4">
              <span className="passport-field-label">Содержание</span>
              <span className="passport-field-value ml-auto">
                {kit.currency} мон.
              </span>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
};

export default PassportKitBlock;
