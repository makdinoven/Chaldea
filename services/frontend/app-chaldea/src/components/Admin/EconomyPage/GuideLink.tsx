import type { ReactNode } from 'react';
import { BookOpen } from 'lucide-react';
import { GUIDE_SECTION_TITLE, useOpenGuide, type GuideSectionId } from './guideSections';

interface GuideLinkProps {
  section: GuideSectionId;
  /** Link text; defaults to the section title. */
  children?: ReactNode;
  className?: string;
}

/** An inline link that opens the «Как настроить» tab at a section (FEAT-185). */
export const GuideLink = ({ section, children, className = '' }: GuideLinkProps) => {
  const openGuide = useOpenGuide();
  return (
    <button
      type="button"
      onClick={() => openGuide(section)}
      className={`inline text-left text-site-blue hover:text-white underline-offset-2 hover:underline transition-colors duration-200 ease-site ${className}`}
    >
      {children ?? GUIDE_SECTION_TITLE[section]}
    </button>
  );
};

interface GuideIntroProps {
  section: GuideSectionId;
  /** One line: what this tab is for. */
  children: ReactNode;
  /** Link text; defaults to «Подробнее в гайде». */
  linkText?: string;
}

/** The «что здесь» line on top of an economy tab, with a link into the guide (FEAT-185). */
export const GuideIntro = ({ section, children, linkText = 'Подробнее в гайде' }: GuideIntroProps) => (
  <p className="flex items-start gap-2 text-white/60 text-sm max-w-3xl">
    <BookOpen size={15} className="shrink-0 mt-0.5 text-gold/70" />
    <span>
      {children}{' '}
      <GuideLink section={section}>{linkText} →</GuideLink>
    </span>
  </p>
);

export default GuideLink;
