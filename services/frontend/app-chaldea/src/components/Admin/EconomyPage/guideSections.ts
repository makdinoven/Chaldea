import { createContext, useContext } from 'react';

/**
 * FEAT-185 — sections of the «Как настроить» guide tab (EconomyGuide.tsx).
 *
 * Any economy tab can jump into the guide without new props:
 *   const openGuide = useOpenGuide();  openGuide('recipe-hunger');
 * or render `<GuideLink section="tick">…</GuideLink>` / `<GuideIntro section="tick">…</GuideIntro>`.
 * EconomyPage provides the context: it switches to the guide tab and scrolls to the section.
 */
export const GUIDE_SECTION_IDS = [
  'checklist',
  'overview',
  'accounts',
  'money-flow',
  'tick',
  'regions',
  'merchants',
  'banks',
  'events',
  'recipes',
  'recipe-hunger',
  'recipe-empty-treasury',
  'recipe-merchant-cash',
  'recipe-bank-interest',
  'recipe-invariant',
  'recipe-prices',
  'recipe-population-scale',
  'recipe-events',
] as const;

export type GuideSectionId = (typeof GUIDE_SECTION_IDS)[number];

/** Human titles (for links and the guide's own table of contents). */
export const GUIDE_SECTION_TITLE: Record<GuideSectionId, string> = {
  checklist: 'Чек-лист запуска',
  overview: 'Как устроена экономика',
  accounts: 'Где лежат деньги',
  'money-flow': 'Схема движения денег',
  tick: 'Что происходит каждые 6 часов',
  regions: 'Жители, товары и цены',
  merchants: 'Торговцы НПС',
  banks: 'Банки',
  recipes: 'Что делать, если…',
  'recipe-hunger': 'Голод в регионе',
  'recipe-empty-treasury': 'Пустая казна',
  'recipe-merchant-cash': 'Торговцу нечем платить',
  'recipe-bank-interest': 'Банк не платит проценты',
  'recipe-invariant': 'Сводка пишет «Расхождение»',
  'recipe-prices': 'Цены растут или падают',
  'recipe-population-scale': 'Перешли на масштаб населения (регионы раздуты)',
  events: 'События регионов',
  'recipe-events': 'Событий слишком много, мало или нет',
};

/** Tabs of the admin «Экономика» page (EconomyPage.tsx). */
export type EconomyTabId =
  | 'guide'
  | 'summary'
  | 'journal'
  | 'actions'
  | 'regions'
  | 'goods'
  | 'items'
  | 'templates'
  | 'merchants'
  | 'banks'
  | 'events'
  | 'tick'
  | 'settings';

/** DOM id of a section's anchor inside the guide. */
export const guideAnchorId = (section: GuideSectionId): string => `econ-guide-${section}`;

/** Opens the guide tab (optionally at a section). No-op outside EconomyPage. */
export type OpenGuide = (section?: GuideSectionId) => void;

export const EconomyGuideContext = createContext<OpenGuide>(() => undefined);

export const useOpenGuide = (): OpenGuide => useContext(EconomyGuideContext);
