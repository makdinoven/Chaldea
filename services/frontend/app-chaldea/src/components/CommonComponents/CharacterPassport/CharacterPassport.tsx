import type { KeyboardEvent, ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { megalinkNumber } from '../../../api/charactersPublic';
import { SEGMENT_LABELS, YEAR_SEGMENTS } from '../../../utils/gameTime';
import PassportKitBlock from './PassportKitBlock';
import PassportSeal from './PassportSeal';
import PassportStatBlock from './PassportStatBlock';
import { PASSPORT_STAT_ORDER } from './types';
import type {
  PassportAudience,
  PassportData,
  PassportStatus,
  PassportVariant,
} from './types';

/**
 * FEAT-154 — the Скиталец passport (rules 25-27).
 *
 * ONE presentational component behind FOUR call sites; the differences between
 * the sources live in `adapters.ts`, never here. Nothing is fetched and nothing
 * is read from the store — everything arrives through `data`.
 *
 * - Free text is rendered ONLY through `whitespace-pre-wrap`. There is no
 *   `dangerouslySetInnerHTML` in this folder and there must never be one (R9).
 * - The in-game year is never hardcoded. `currentGameYear` is optional and
 *   comes from `selectCurrentGameYear` (the game clock); without it the tenure
 *   is printed as given, just without «в строю N лет».
 */
interface CharacterPassportProps {
  data: PassportData;
  /** `full` (default) = the whole sheet. `compact` = the grid card. */
  variant?: PassportVariant;
  /**
   * Current in-game year, from `selectCurrentGameYear` (`gameTimeSlice`).
   * **Never pass a literal** — the clock is moved before launch.
   */
  currentGameYear?: number | null;
  /** Makes the whole sheet activatable — used by the list grid. */
  onClick?: () => void;
  /**
   * Who is reading this sheet.
   *
   * `'public'` (the DEFAULT) hides the **recruitment record** — the kit the
   * organisation issued and the posting it assigned. A stranger browsing other
   * players' characters has no business with either: the issued equipment is
   * the least interesting thing about someone else's character and only bloats
   * the sheet, and where a player started is nobody else's business.
   *
   * `'self'` shows it, for the three surfaces that are the player's own record
   * or the judgement of it: the wizard's contract step (choosing the posting
   * and being shown the kit IS that step), «Мои заявки», and the moderator
   * screen (the assignment is part of what is being judged).
   *
   * ONE prop rather than a boolean per row, so a future call site cannot set
   * half of the record public and half of it private. **Defaults to `'public'`**
   * — a new surface then discloses nothing until it says otherwise.
   *
   * Nothing is stripped from `PassportData`: this only decides what is drawn.
   */
  audience?: PassportAudience;
  /** Extra content under the sheet: moderator buttons, «Подписать контракт», … */
  footer?: ReactNode;
  className?: string;
}

const SEX_LABELS: Record<string, string> = {
  male: 'Мужской',
  female: 'Женский',
  genderless: 'Бесполый',
};

const STATUS_LABELS: Record<PassportStatus, string> = {
  pending: 'На рассмотрении',
  approved: 'Одобрена',
  rejected: 'Отклонена',
};

const STATUS_BADGE_CLASS: Record<PassportStatus, string> = {
  pending: 'lore-badge',
  approved: 'lore-badge lore-badge-ok',
  rejected: 'lore-badge lore-badge-danger',
};

const DASH = '—';

const formatRegisteredAt = (iso: string | null | undefined): string => {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return DASH;
  return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
};

/** «Весна 1787 г.» — the segment index maps into the shared game calendar. */
const formatTenure = (data: PassportData, currentGameYear?: number | null): string => {
  const tenure = data.skitaltsySince;
  if (!tenure) return DASH;

  const segment =
    typeof tenure.segment === 'number' ? YEAR_SEGMENTS[tenure.segment] : undefined;
  const segmentLabel = segment ? SEGMENT_LABELS[segment.name] : undefined;
  const base = segmentLabel ? `${segmentLabel} ${tenure.year} г.` : `${tenure.year} г.`;

  if (typeof currentGameYear !== 'number') return base;
  const years = currentGameYear - tenure.year;
  if (years < 0) return base;
  return `${base} (в строю ${years} ${years === 1 ? 'год' : years < 5 ? 'года' : 'лет'})`;
};

/** «Рюджин из Империи Шинзо» — the one line that carries the most identity. */
const formatLineage = (data: PassportData): string => {
  const who = data.subraceName ?? data.raceName;
  if (who && data.origin?.name) return `${who} из ${data.origin.name}`;
  return who ?? data.origin?.name ?? DASH;
};

/**
 * The only `src` we are willing to hand to an `<img>`.
 *
 * `characters.avatar` still carries legacy junk — literally the string
 * `"string"`, the trace of the very bug FEAT-154 fixed. Such a value is
 * TRUTHY, so a bare `avatarUrl || subraceImage` fallback never fires and the
 * browser resolves `src="string"` against the current path: a `GET
 * /characters/string` (405) and a broken tile in the grid.
 *
 * Deliberately cheap and predictable rather than real URL validation: a value
 * is usable only if it is absolute (`http(s)://`, protocol-relative), rooted
 * (`/...`) or an inline image. Anything else — `""`, `"   "`, `"string"`, a
 * bare filename — counts as absent, so the subrace picture takes over.
 */
const usableImageSrc = (value?: string | null): string | null => {
  const src = value?.trim();
  if (!src) return null;
  return /^(https?:\/\/|\/\/|\/|data:image\/)/i.test(src) ? src : null;
};

const Portrait = ({
  data,
  compact,
}: {
  data: PassportData;
  compact: boolean;
}) => {
  const src = usableImageSrc(data.avatarUrl) ?? usableImageSrc(data.subraceImage);
  // Full = a centred medallion at the head of the sheet. Fixed square sizes,
  // never `w-full`: at 360px a full-width portrait would eat the whole screen.
  const size = compact
    ? 'h-14 w-14 sm:h-16 sm:w-16'
    : 'h-32 w-32 sm:h-40 sm:w-40 md:h-48 md:w-48';

  return (
    <div
      className={`${size} shrink-0 overflow-hidden rounded-card border border-ink/25 bg-parchment-dark`}
    >
      {src ? (
        <img src={src} alt={data.name} className="h-full w-full object-cover" loading="lazy" />
      ) : (
        <span className="flex h-full w-full items-center justify-center lore-heading text-2xl text-ink-muted">
          {data.name.charAt(0).toUpperCase()}
        </span>
      )}
    </div>
  );
};

/** One label/value ruling. Prints «—» rather than disappearing (rule 27). */
const Field = ({ label, value }: { label: string; value?: ReactNode }) => (
  <div className="passport-field">
    <span className="passport-field-label">{label}</span>
    <span className="passport-field-value ml-auto text-right">{value || DASH}</span>
  </div>
);

/** Player-written text. `whitespace-pre-wrap` only — never raw HTML (R9). */
const FreeText = ({ title, body }: { title: string; body?: string | null }) => {
  if (!body) return null;
  return (
    <section>
      <h3 className="lore-heading text-lg sm:text-xl">{title}</h3>
      <p className="lore-body mt-2 whitespace-pre-wrap break-words">{body}</p>
    </section>
  );
};

const CharacterPassport = ({
  data,
  variant = 'full',
  currentGameYear = null,
  audience = 'public',
  onClick,
  footer,
  className = '',
}: CharacterPassportProps) => {
  const compact = variant === 'compact';
  /** The recruitment record — issued kit and first posting — is owner-only. */
  const showRecruitmentRecord = audience === 'self';
  const interactive = typeof onClick === 'function';

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (!interactive) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onClick?.();
    }
  };

  const rareOrigin = data.originIsTypical === false && !!data.origin;

  /** Any free text at all? Without it the chronicle band and its rule are skipped. */
  const hasChronicle = Boolean(
    data.appearance || data.biography || data.personality || data.background,
  );

  /**
   * Does the second column have anything to say? `PassportStatBlock` and
   * `PassportKitBlock` both render `null` when they were given nothing, and a
   * moderation request carries neither — so without this the two-column band
   * would leave exactly the empty half this rework exists to remove, just on a
   * different screen. Mirrors `PassportStatBlock`'s own emptiness test.
   */
  const hasLedger = Boolean(
    (data.stats && PASSPORT_STAT_ORDER.some((key) => typeof data.stats?.[key] === 'number')) ||
      (showRecruitmentRecord && data.starterKit),
  );

  const badges = (
    <div className="flex flex-wrap items-center gap-2">
      {data.status ? (
        <span className={STATUS_BADGE_CLASS[data.status]}>{STATUS_LABELS[data.status]}</span>
      ) : null}
      {rareOrigin ? (
        <span className="lore-badge lore-badge-warn" title="Нетипичная родина для этой подрасы">
          Редкий выбор
        </span>
      ) : null}
      {data.isNpc ? <span className="lore-badge">НПС</span> : null}
    </div>
  );

  /**
   * The registry serial. It lives in «Информация о персонаже» beside УР and the
   * dates — it is the same class of datum — and NOT under the portrait, where a
   * number reads as a caption to the picture. The wax stamp stays in the header
   * without it (`showNumber={false}`); the stamp is the mark, this is the record.
   */
  const megalinkValue =
    typeof data.characterId === 'number' && data.characterId > 0 ? (
      megalinkNumber(data.characterId)
    ) : (
      <span className="italic text-ink-muted">будет присвоен при регистрации</span>
    );

  const originValue = data.origin ? (
    <span className="inline-flex items-center gap-2">
      {data.origin.emblemUrl ? (
        <img
          src={data.origin.emblemUrl}
          alt=""
          className="h-5 w-5 shrink-0 object-contain"
          loading="lazy"
        />
      ) : null}
      {data.origin.archiveSlug ? (
        <Link
          to={`/archive/${data.origin.archiveSlug}`}
          className="underline decoration-ink/40 underline-offset-2 hover:decoration-ink"
        >
          {data.origin.name}
        </Link>
      ) : (
        data.origin.name
      )}
    </span>
  ) : undefined;

  const interactiveProps = interactive
    ? {
        role: 'button' as const,
        tabIndex: 0,
        onClick,
        onKeyDown: handleKeyDown,
        className: 'cursor-pointer transition-shadow duration-200 ease-site hover:shadow-hover',
      }
    : {};

  // ── compact: the card in the characters grid (rule 26) ────────────────────
  if (compact) {
    return (
      <article
        {...interactiveProps}
        className={`book-page rounded-card shadow-page flex h-full flex-col gap-3 p-4 ${
          interactiveProps.className ?? ''
        } ${className}`}
      >
        <div className="flex items-center gap-3">
          <Portrait data={data} compact />
          <div className="min-w-0 flex-1">
            <h3 className="lore-heading truncate text-lg">{data.name}</h3>
            <p className="lore-body truncate text-sm text-ink-muted">{formatLineage(data)}</p>
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <Field label="УР" value={data.level ?? undefined} />
          <Field label="Путь" value={data.className ?? undefined} />
        </div>

        <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-1">
          <PassportSeal characterId={data.characterId} compact />
          {badges}
        </div>

        {footer}
      </article>
    );
  }

  // ── full: three stacked bands — portrait header, two columns, chronicle ──
  return (
    <article
      {...interactiveProps}
      className={`book-page rounded-card shadow-page animate-fade-in overflow-hidden ${
        interactiveProps.className ?? ''
      } ${className}`}
    >
      <div className="p-4 sm:p-6 md:p-8">
        {/* Band 1 — the identity header: portrait, name, seal, all centred. */}
        <header className="flex flex-col items-center gap-3 text-center">
          <p className="passport-field-label">Реестр Цитадели</p>
          <h2 className="lore-heading text-2xl sm:text-3xl">Паспорт Скитальца</h2>

          <div className="mt-1">
            <Portrait data={data} compact={false} />
          </div>

          <div className="min-w-0 w-full">
            <h3 className="lore-heading text-xl break-words sm:text-2xl">{data.name}</h3>
            <p className="lore-body mt-1 break-words text-ink-muted">{formatLineage(data)}</p>
          </div>

          <PassportSeal characterId={data.characterId} showNumber={false} />

          {/* `badges` is left-aligned by its own `flex`; centre it here only. */}
          <div className="flex w-full justify-center">{badges}</div>
        </header>

        <div className="lore-divider my-5 sm:my-6" />

        {/*
          Band 2 — the ledger. No `book-page-gutter`: with the portrait lifted
          into the header and the chronicle dropped below, this is one sheet
          with two columns, not a two-page spread, and a vertical spine would
          read as a leftover. Horizontal `lore-divider` rules separate instead.

          `md:grid-cols-2` only when the second column has content: a moderation
          request has neither stats nor kit, and an empty half is exactly what
          this rework removes.
        */}
        <div className={`grid gap-6 ${hasLedger ? 'md:grid-cols-2 md:gap-10' : ''}`}>
          {/* Column one — the passport rows. Alone on the sheet it is capped
              and centred, so the label/value rulings do not stretch apart. */}
          <div
            className={`flex flex-col gap-4 ${hasLedger ? '' : 'mx-auto w-full md:max-w-2xl'}`}
          >
            <h3 className="lore-heading text-lg sm:text-xl">Информация о персонаже</h3>

            <div className="flex flex-col gap-2">
              <Field label="Мегалинк" value={megalinkValue} />
              <Field label="УР" value={data.level ?? undefined} />
              <Field label="Раса" value={data.raceName ?? undefined} />
              <Field label="Подраса" value={data.subraceName ?? undefined} />
              <Field label="Родина" value={originValue} />
              <Field label="Путь" value={data.className ?? undefined} />
              <Field label="Пол" value={data.sex ? SEX_LABELS[data.sex] ?? data.sex : undefined} />
              <Field label="Возраст" value={data.age ?? undefined} />
              <Field label="Рост" value={data.height ?? undefined} />
              <Field label="Вес" value={data.weight ?? undefined} />
              <Field label="Дата регистрации" value={formatRegisteredAt(data.registeredAt)} />
              <Field label="В Скитальцах с" value={formatTenure(data, currentGameYear)} />
              {showRecruitmentRecord ? (
                <Field label="Первое назначение" value={data.startLocation?.name} />
              ) : null}
            </div>

            {data.status === 'rejected' && data.rejectionReason ? (
              <div className="rounded-card border border-[#8b1a1a]/40 bg-[#8b1a1a]/10 p-3">
                <p className="passport-field-label">Причина отказа</p>
                <p className="lore-body mt-1 whitespace-pre-wrap break-words text-sm">
                  {data.rejectionReason}
                </p>
              </div>
            ) : null}
          </div>

          {/* Column two — what this Скиталец is worth and what he carries */}
          {hasLedger ? (
            <div className="flex flex-col gap-5">
              <PassportStatBlock stats={data.stats} derived={data.derived} />
              {showRecruitmentRecord ? (
                <PassportKitBlock kit={data.starterKit} isSnapshot={data.starterKitIsSnapshot} />
              ) : null}
            </div>
          ) : null}
        </div>

        {/*
          The chronicle. Player-written text runs to thousands of characters, so
          it lives BELOW the two columns at full width instead of inside one of
          them — otherwise that column grows for screens while the other ends
          after a single viewport and leaves a vast empty half.
        */}
        {hasChronicle ? (
          <>
            <div className="lore-divider my-6 sm:my-8" />
            <div className="flex flex-col gap-6 sm:gap-8">
              <FreeText title="Внешность" body={data.appearance} />
              <FreeText title="Биография" body={data.biography} />
              <FreeText title="Характер" body={data.personality} />
              <FreeText title="Предыстория" body={data.background} />
            </div>
          </>
        ) : null}

        {footer ? <div className="mt-6">{footer}</div> : null}
      </div>
    </article>
  );
};

export default CharacterPassport;
