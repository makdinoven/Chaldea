/**
 * FEAT-154 — shared types of the «Регистрация Скитальца» wizard.
 *
 * Races and subraces are re-exported from `racesSlice` on purpose: the wizard
 * reads them through the shared `fetchRaces` thunk (task #15), so a second,
 * drifting copy of the shape here would be a bug waiting to happen.
 */

export type {
  StatPreset,
  Race as RaceData,
  Subrace as SubraceData,
} from '../../redux/slices/racesSlice';

/**
 * The six steps of the wizard, in order. Single source of truth for the step
 * heading, the pagination labels, the number of pagination dots and the «на
 * каком шаге» part of every validation message (task #19) — a second copy would
 * drift. Everything that depends on «how many steps are there» derives from
 * this array's length, so adding or removing a step is a one-line change here.
 *
 * «Присяга» (the posting and the law of the organisation) was split out of
 * «Контракт» (the passport and the signature): on one page the passport drew
 * all the attention and the law went unread.
 */
export const WIZARD_STEP_TITLES = [
  'Кровь',
  'Родина',
  'Путь',
  'Личность',
  'Присяга',
  'Контракт',
] as const;

export interface Biography {
  biography: string;
  personality: string;
  appearance: string;
  name: string;
  age: string;
  height: string;
  weight: string;
  sex: string;
}

export interface CarouselItem {
  id: number;
  name: string;
  image: string | null;
}

export interface VerticalCarouselProps {
  items: CarouselItem[];
  selectedId: number;
  onSelect: (id: number) => void;
}

export interface PageData {
  pageId: number;
  pageTitle: string;
}

/**
 * Everything the «Личность» step collects (task #18).
 *
 * `avatarUrl` is the permanent S3 URL returned by
 * `POST /photo/upload_character_request_avatar` — never a blob preview, and
 * never the literal `'string'` the pre-feature form used to send. It stays
 * optional: an upload failure must not block the application (rule 21, D5).
 *
 * The tenure pair is the in-world «в Скитальцах с» (rules 22-24). It carries no
 * mechanical benefit whatsoever — a new Скиталец is always УР 1.
 * ⚠️ The current in-game year is NEVER hardcoded: it comes from
 * `computed.year` of `GET /locations/game-time` at runtime.
 */
export interface PersonaForm extends Biography {
  avatarUrl: string | null;
  skitaltsySinceYear: number | null;
  /** Segment index 0..7 into `YEAR_SEGMENTS`. */
  skitaltsySinceSegment: number | null;
}
