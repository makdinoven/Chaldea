import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchArticleBySlug } from '../../../api/archive';
import {
  extractArticleBlocksFrom,
  extractArticleSection,
  type ArticleBlock,
} from '../../../utils/articleSection';
import ArchiveLinkPreview from '../../CommonComponents/ArchiveLinkPreview/ArchiveLinkPreview';

/**
 * FEAT-154 — the law of the organisation, on the «Присяга» step.
 *
 * This block used to be four titles and a link: the player signed a contract
 * whose terms lived one click away, and most of them never made that click.
 * It now says outright **what counts as an offence and what it costs** —
 * because that is the part the player has to know *before* he signs.
 *
 * ### Where the text comes from — and how it is found
 *
 * From the Архив article «Скитальцы», at runtime. The Архив is the single
 * source of truth for lore: a copy of the two lists in this file would read a
 * little cleaner and would start lying the first time a lore editor touched
 * the article, with nothing to catch the drift. So **nothing about the
 * offences is written here** — not even as a fallback.
 *
 * The lookup is deliberately two-tiered, because the thing most likely to
 * break quietly is the article being rewritten:
 *
 * 1. **By heading** — everything under «Законы и правила», up to the next
 *    heading. Exact (after whitespace/case normalisation), so a renamed
 *    heading fails loudly to tier 2 instead of grabbing the wrong section.
 * 2. **By content** — if that heading is gone, everything from the first
 *    paragraph that mentions Анафема / Домнацио Мемориае / «карается», up to
 *    the next heading. Renaming the heading does not move the rules.
 * 3. **Neither matched, or the Архив is unreachable** — the sheet says so in
 *    one line and points at the article. An honest «читайте в Архиве» beats a
 *    stale copy of rules that may no longer be the rules.
 *
 * The text is **never** rendered through `dangerouslySetInnerHTML` — only
 * plain strings cross out of the parser (see `articleSection.ts`).
 */

const SKITALTSY_ARTICLE_SLUG = 'skitaltsy';

/** The heading inside that article that opens the section we need. */
const LAWS_SECTION_HEADING = 'Законы и правила';

/**
 * Tier 2 of the lookup: the rules themselves, wherever they ended up. These
 * are the words of the *measures*, not of any single offence — an offence can
 * be renamed, «Анафема» cannot be, since the whole institution is named after
 * it.
 */
const LAWS_CONTENT_PATTERN = /Анафем|Домнацио|Карается/i;

/** How many blocks tier 2 may pull in before it is clearly overreaching. */
const MAX_FALLBACK_BLOCKS = 24;

/** «Карается анафемой.» / «Карается Домнацио Мемориае.» at the end of an item. */
const PENALTY_RE = /\s*Карается\s+([^.]+)\.\s*$/i;

/** «Сокрытие доли: остальной текст» — the item's own name, if it has one. */
const TITLE_RE = /^([^.:]{3,60}):\s+(.+)$/s;

interface ParsedOffence {
  title: string | null;
  text: string;
  penalty: string | null;
}

const parseOffence = (raw: string): ParsedOffence => {
  let text = raw;
  let penalty: string | null = null;

  const penaltyMatch = text.match(PENALTY_RE);
  if (penaltyMatch) {
    penalty = penaltyMatch[1].trim();
    text = text.replace(PENALTY_RE, '').trim();
  }

  const titleMatch = text.match(TITLE_RE);
  if (titleMatch) {
    return { title: titleMatch[1].trim(), text: titleMatch[2].trim(), penalty };
  }
  return { title: null, text, penalty };
};

/**
 * The article writes the penalty in the instrumental case — «карается
 * анафемой» — which reads wrong on a badge. The badge names the measure
 * itself. An unrecognised measure is shown as written rather than dropped:
 * a new penalty in the Архив must still reach the player.
 */
const penaltyLabel = (penalty: string): string => {
  if (/анафем/i.test(penalty)) return 'Анафема';
  if (/домнацио/i.test(penalty)) return 'Домнацио Мемориае';
  return penalty.charAt(0).toUpperCase() + penalty.slice(1);
};

/** Анафема is a lesser measure than Домнацио Мемориае — ochre vs red. */
const penaltyBadgeClass = (penalty: string): string =>
  /анафем/i.test(penalty) ? 'lore-badge lore-badge-warn' : 'lore-badge lore-badge-danger';

type SectionState =
  | { status: 'loading' }
  | { status: 'ready'; blocks: ArticleBlock[] }
  | { status: 'unavailable' };

/** Tier 1, then tier 2, then nothing — see the module comment. */
const findLawBlocks = (content: string | null): ArticleBlock[] => {
  const bySection = extractArticleSection(content, LAWS_SECTION_HEADING);
  if (bySection.length > 0) return bySection;
  return extractArticleBlocksFrom(content, LAWS_CONTENT_PATTERN, {
    maxBlocks: MAX_FALLBACK_BLOCKS,
  });
};

/** One request per session: the step is revisited, the article is not refetched. */
let sectionCache: SectionState | null = null;

const OffenceList = ({ items, ordered }: { items: string[]; ordered: boolean }) => {
  const ListTag = ordered ? 'ol' : 'ul';
  return (
    <ListTag
      className={`flex flex-col gap-3 ${
        ordered ? 'list-decimal' : 'list-disc'
      } pl-5 marker:text-ink-muted marker:font-lore`}
    >
      {items.map((item, index) => {
        const { title, text, penalty } = parseOffence(item);
        return (
          <li key={index} className="pl-1">
            <div className="flex flex-col gap-1">
              {title && (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="lore-heading text-base">{title}</span>
                  {penalty && (
                    <span className={penaltyBadgeClass(penalty)}>{penaltyLabel(penalty)}</span>
                  )}
                </div>
              )}
              <p className="lore-body text-sm">{text}</p>
              {!title && penalty && (
                <span className={`${penaltyBadgeClass(penalty)} self-start`}>
                  {penaltyLabel(penalty)}
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ListTag>
  );
};

const LawsOfTheOrder = () => {
  const [section, setSection] = useState<SectionState>(
    () => sectionCache ?? { status: 'loading' },
  );

  useEffect(() => {
    if (sectionCache) {
      setSection(sectionCache);
      return undefined;
    }

    let cancelled = false;
    setSection({ status: 'loading' });

    fetchArticleBySlug(SKITALTSY_ARTICLE_SLUG)
      .then((article) => {
        const blocks = findLawBlocks(article.content);
        const next: SectionState =
          blocks.length > 0 ? { status: 'ready', blocks } : { status: 'unavailable' };
        sectionCache = next;
        if (!cancelled) setSection(next);
      })
      .catch(() => {
        // Deliberately quiet: the sheet says in its own words that the Архив
        // is unreachable and points at the article, so a red toast on a step
        // the player did not ask to load would only be noise. The failure is
        // cached, so a dead slug is not retried on every visit.
        const next: SectionState = { status: 'unavailable' };
        sectionCache = next;
        if (!cancelled) setSection(next);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="book-page rounded-card shadow-page p-5 sm:p-8 flex flex-col gap-4">
      <div>
        <h3 className="lore-heading text-xl sm:text-2xl">Законы Скитальцев</h3>
        <p className="text-ink-muted text-xs uppercase tracking-[0.08em]">
          Прочтите прежде, чем подписывать
        </p>
      </div>

      <div className="lore-divider" />

      <p className="lore-body text-sm">
        Вступая в Скитальцев, вы получаете мегалинк, Координатора и УР 1 — начальную оценку
        по внутренней шкале организации. Взамен на вас распространяется её право.
      </p>

      {section.status === 'ready' ? (
        <div className="flex flex-col gap-4">
          {section.blocks.map((block, index) =>
            block.kind === 'paragraph' ? (
              <p key={index} className="lore-body text-sm">
                {block.text}
              </p>
            ) : (
              <OffenceList key={index} items={block.items} ordered={block.ordered} />
            ),
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {section.status === 'loading' ? (
            <span className="flex items-center gap-2 text-ink-muted text-sm">
              <span className="w-3.5 h-3.5 border-2 border-ink-muted/30 border-t-ink-muted rounded-full animate-spin" />
              Архив листает страницы…
            </span>
          ) : (
            /*
              No stale copy of the rules lives here on purpose: an honest
              pointer at the Архив is safer than a list that may no longer be
              the list. The link below is always rendered.
            */
            <p className="lore-body text-sm">
              Свод правил сейчас недоступен — Архив не отвечает или статья была
              переписана. Прочтите «Законы и правила» в статье Архива прежде, чем
              подписывать контракт: за нарушения назначают Анафему (исключение) или
              Домнацио Мемориае (проклятие памяти).
            </p>
          )}
        </div>
      )}

      <div className="lore-divider" />

      <div className="flex flex-col gap-3">
        <ArchiveLinkPreview>
          <a
            href={`/archive/${SKITALTSY_ARTICLE_SLUG}`}
            data-archive-slug={SKITALTSY_ARTICLE_SLUG}
          >
            Полная статья Архива: Скитальцы
          </a>
        </ArchiveLinkPreview>

        <Link
          to={`/archive/${SKITALTSY_ARTICLE_SLUG}`}
          className="self-start inline-flex items-center gap-2 px-4 py-2 rounded-card
            border border-ink-muted/50 bg-parchment-light/50 text-ink font-lore text-sm
            hover:bg-parchment-dark transition-colors duration-200"
        >
          Читать дальше в статье
          <span aria-hidden="true">→</span>
        </Link>
      </div>
    </section>
  );
};

export default LawsOfTheOrder;
