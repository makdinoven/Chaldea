import type { DungeonTheme } from './dungeonThemes';
/* What the board needs to know about a dungeon: rooms on a grid and the corridors between them. */

export type BoardRoomType =
  | 'entrance'
  | 'battle'
  | 'boss'
  | 'treasure'
  | 'trap'
  | 'event'
  | 'rest'
  | 'merchant'
  | 'teleport'
  | 'fork'
  | 'deadend';

export interface BoardRoom {
  id: number;
  type: BoardRoomType;
  name: string;
  /** Grid cell; the board lays tiles out one cell apart. */
  col: number;
  row: number;
  /** Width × depth in floor squares, when it differs from its kind's usual size. */
  size?: [number, number];
  /** Enemy figurines waiting in a battle or boss room until it is cleared. */
  enemies?: number;
  /** A teleport room's portal: blue (a way to take) or red (a trap). */
  portal?: 'blue' | 'red';
  /** Ways to the floor above or below that start in this room. */
  passages?: BoardPassage[];
  /** A dark room with no light in it: the table shows it sunk in gloom. */
  dark?: boolean;
  /** Scouted but not yet entered: what waits there, as a label over the rock (FEAT-176). */
  scouted?: string;
}

/** Stairs, a drop or a lift from a room to a neighbouring floor. */
export interface BoardPassage {
  kind: 'stairs' | 'drop' | 'lift';
  dir: 'down' | 'up';
  /** The room it leads to (on the other floor). */
  target: number;
  /** Still locked in this run: the key it wants, or 'lever'. */
  lock?: string;
}

export interface BoardCorridor {
  from: number;
  to: number;
  /** Chance of an ambush or a trap on the way, shown as a die to roll. */
  risky?: boolean;
  /** A locked door still shut in this run: the kind of key it wants (a padlock on its doors). */
  lock?: string;
}

export interface BoardMember {
  id: number;
  name: string;
  /** Colour of the figurine's base ring. */
  color: string;
  leader?: boolean;
  /** Fell in battle: the figurine lies on its side. */
  dead?: boolean;
  /** Which miniature stands for them: 1 warrior, 2 rogue, 3 mage; anything else a plain pawn. */
  classId?: number | null;
  /** Shown in the portrait over the figurine on hover. */
  avatar?: string | null;
  level?: number | null;
  /** Holds up the party shield until the party moves on. */
  shielded?: boolean;
  /** Something just said (typed in the chat, or a vote or a mark said aloud): a bubble over the figurine. */
  speech?: { text: string; at: number } | null;
  /** Playing a minigame right now: a badge over the figurine for as long as it lasts. */
  busy?: MemberBusy | null;
}

/** What a member is busy with, as the badge over the figurine and the party frame show it. */
export interface MemberBusy {
  icon: string;
  text: string;
}

export interface BoardDungeon {
  name: string;
  /** How this floor of the miniature looks (walls, floor, light); stone when left out. */
  theme?: DungeonTheme;
  rooms: BoardRoom[];
  corridors: BoardCorridor[];
  entranceId: number;
}

/** A made-up dungeon for the sketch: branches, loops, dead ends and a long way to the lair. */
export const SKETCH_DUNGEON: BoardDungeon = {
  name: 'Пещера Грехов',
  entranceId: 1,
  rooms: [
    { id: 1, type: 'entrance', name: 'Спуск', col: 0, row: 3 },
    { id: 2, type: 'fork', name: 'Перекрёсток стражи', col: 1, row: 2, size: [4, 3] },
    { id: 3, type: 'battle', name: 'Казармы скелетов', col: 2, row: 1, size: [5, 4], enemies: 3 },
    { id: 5, type: 'treasure', name: 'Забытая кладовая', col: 3, row: 0 },
    { id: 6, type: 'rest', name: 'Тихий грот', col: 4, row: 1, size: [4, 3] },
    { id: 7, type: 'event', name: 'Источник', col: 3, row: 2, size: [5, 5] },
    { id: 8, type: 'trap', name: 'Коридор лезвий', col: 2, row: 3, size: [3, 4] },
    { id: 9, type: 'event', name: 'Плачущая статуя', col: 5, row: 0, size: [4, 4] },
    { id: 10, type: 'merchant', name: 'Лавка падальщика', col: 6, row: 1 },
    { id: 11, type: 'battle', name: 'Зал гончих', col: 5, row: 2, size: [5, 4], enemies: 2 },
    { id: 12, type: 'fork', name: 'Колодец', col: 4, row: 3, size: [3, 3] },
    { id: 13, type: 'deadend', name: 'Обвал', col: 7, row: 0, size: [3, 2] },
    { id: 14, type: 'teleport', name: 'Круг рун', col: 7, row: 2 },
    { id: 15, type: 'battle', name: 'Склеп', col: 6, row: 3, size: [4, 5], enemies: 4 },
    { id: 16, type: 'deadend', name: 'Нора', col: 1, row: 4, size: [2, 3] },
    { id: 17, type: 'treasure', name: 'Сокровищница культа', col: 3, row: 4, size: [4, 3] },
    { id: 18, type: 'event', name: 'Алтарь', col: 5, row: 4, size: [4, 4] },
    { id: 19, type: 'rest', name: 'Последний привал', col: 7, row: 4 },
    { id: 20, type: 'teleport', name: 'Разлом', col: 4, row: 5 },
    { id: 21, type: 'battle', name: 'Логово ужаса', col: 6, row: 5, size: [5, 4], enemies: 5 },
    { id: 22, type: 'boss', name: 'Сердце пещеры', col: 8, row: 5, size: [6, 6], enemies: 1 },
  ],
  corridors: [
    { from: 1, to: 2 },
    { from: 2, to: 3, risky: true },
    { from: 2, to: 8 },
    { from: 3, to: 5 },
    { from: 3, to: 7, risky: true },
    { from: 5, to: 6 },
    { from: 6, to: 7 },
    { from: 6, to: 9, risky: true },
    { from: 7, to: 12 },
    { from: 8, to: 16 },
    { from: 8, to: 17, risky: true },
    { from: 9, to: 10 },
    { from: 10, to: 13 },
    { from: 10, to: 14 },
    { from: 12, to: 11, risky: true },
    { from: 11, to: 15 },
    { from: 12, to: 18 },
    { from: 17, to: 20 },
    { from: 18, to: 21, risky: true },
    { from: 15, to: 19 },
    { from: 19, to: 22 },
    { from: 21, to: 22, risky: true },
  ],
};

export const SKETCH_PARTY: BoardMember[] = [
  { id: 1, name: 'Ашари', color: '#f0d95c', leader: true, classId: 3, level: 12 },
  { id: 2, name: 'Годрик', color: '#76a6bd', classId: 1, level: 9 },
  { id: 3, name: 'Аэлис', color: '#b06ad0', classId: 2, level: 10 },
];
