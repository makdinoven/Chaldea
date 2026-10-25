import type { SessionMember, SessionState } from '../../api/dungeons';
import type { BoardCorridor, BoardDungeon, BoardMember, BoardPassage, BoardRoom, BoardRoomType, MemberBusy } from './boardTypes';
import { gridCellOf, gridSizeOf } from './editorToBoard';
import { floorTheme, type DungeonTheme } from './dungeonThemes';

/*
  A live run as a board: only what the party knows. The room it stands in and
  the rooms it has explored are built; the rooms behind the current exits lie
  face down, with a neutral look so the card never gives away what is inside.

  The server only describes the current room's surroundings, so the board keeps
  a memory of everything seen during the run: rooms and corridors never vanish
  from the table when a later state leaves them out, and a room placed without
  editor coordinates keeps the cell it was given.
*/

/** How an unknown room is drawn until the party gets there: a plain crossroads. */
const UNKNOWN_TYPE: BoardRoomType = 'fork';
const UNKNOWN_NAME = 'Неизведанное';

const BOARD_TYPES = new Set<BoardRoomType>([
  'entrance', 'battle', 'boss', 'treasure', 'trap', 'event', 'rest', 'merchant', 'teleport', 'fork', 'deadend',
]);

/** Colours of the figurines' base rings, handed out in party order. */
const MEMBER_COLORS = ['#f0d95c', '#76a6bd', '#b06ad0', '#6fbf73', '#e08a4c', '#d65c7a', '#5cc7c0', '#c9c9c9'];

/** Where a room without editor coordinates may go next to a placed neighbour, nearest first. */
const NEAR_OFFSETS: [number, number][] = [
  [1, 0], [0, 1], [-1, 0], [0, -1], [1, 1], [-1, 1], [1, -1], [-1, -1],
  [2, 0], [0, 2], [-2, 0], [0, -2],
];
const MAX_FREE_CELL_RING = 30;

interface KnownRoom {
  id: number;
  /** null while the party has only seen the door to it. */
  type: BoardRoomType | null;
  name: string;
  /** Cell from the editor's coordinates, when the room has them. */
  cell: [number, number] | null;
  size?: [number, number];
  /** Done with: enemies beaten, trap sprung, event chosen, red portal seen through, chest emptied, rest taken. */
  cleared: boolean;
  enemies?: number;
  portal?: 'blue' | 'red';
  floor: number;
  dark?: boolean;
  scouted?: string;
}

type Passage = 'corridor' | 'stairs' | 'drop' | 'lift';

interface KnownCorridor {
  from: number;
  to: number;
  lock?: string;
  passage: Passage;
}

/** What a door still wants while it is shut in this run: its key, or a lever. */
const lockOf = (c: { lock_key?: string | null; locked?: boolean }) =>
  c.locked ? (c.lock_key ? c.lock_key : 'lever') : undefined;

export interface BoardMemory {
  sessionId: number | null;
  rooms: Map<number, KnownRoom>;
  /** By corridor id. */
  corridors: Map<number, KnownCorridor>;
  /** Cells given to rooms without coordinates; they keep them for the whole run. */
  placed: Map<number, [number, number]>;
}

export const createBoardMemory = (): BoardMemory => ({
  sessionId: null,
  rooms: new Map(),
  corridors: new Map(),
  placed: new Map(),
});

export interface SessionBoard {
  /** The floor the party is on: the table shows one floor at a time. */
  dungeon: BoardDungeon;
  /** Rooms standing on the table: the current one and the explored ones (every floor). */
  revealed: Set<number>;
  /** Rooms done with (see KnownRoom.cleared): the table shows them spent. */
  cleared: Set<number>;
  floor: number;
  floors: number;
  /** The floor of every room the party knows of. */
  floorOf: Map<number, number>;
}

const toBoardType = (roomType: string, isEntrance = false): BoardRoomType => {
  if (isEntrance) return 'entrance';
  return BOARD_TYPES.has(roomType as BoardRoomType) ? (roomType as BoardRoomType) : UNKNOWN_TYPE;
};

const cellKey = ([c, r]: [number, number]) => `${c},${r}`;

/** Gives every room of one floor a grid cell: its editor cell, or a free one next to a placed neighbour. */
const placeRooms = (
  memory: BoardMemory,
  roomIds: Set<number>,
  corridors: KnownCorridor[],
): Map<number, [number, number]> => {
  const cells = new Map<number, [number, number]>();
  const taken = new Set<string>();
  const take = (id: number, cell: [number, number]) => {
    cells.set(id, cell);
    taken.add(cellKey(cell));
  };
  memory.rooms.forEach((room) => {
    if (!roomIds.has(room.id)) return;
    const cell = room.cell ?? memory.placed.get(room.id);
    if (cell) take(room.id, cell);
  });

  const neighbours = new Map<number, number[]>();
  corridors.forEach(({ from, to }) => {
    neighbours.set(from, [...(neighbours.get(from) ?? []), to]);
    neighbours.set(to, [...(neighbours.get(to) ?? []), from]);
  });

  const freeCellNear = (origin: [number, number]): [number, number] | null => {
    for (const [dc, dr] of NEAR_OFFSETS) {
      const cell: [number, number] = [origin[0] + dc, origin[1] + dr];
      if (!taken.has(cellKey(cell))) return cell;
    }
    return null;
  };
  const anyFreeCell = (): [number, number] => {
    for (let ring = 0; ring <= MAX_FREE_CELL_RING; ring++) {
      for (let dc = -ring; dc <= ring; dc++) {
        for (let dr = -ring; dr <= ring; dr++) {
          if (Math.max(Math.abs(dc), Math.abs(dr)) !== ring) continue;
          const cell: [number, number] = [dc, dr];
          if (!taken.has(cellKey(cell))) return cell;
        }
      }
    }
    return [MAX_FREE_CELL_RING + 1, 0];
  };

  // Breadth-first from the placed rooms: each unplaced room goes beside a neighbour that has a cell.
  let pending = [...roomIds].filter((id) => !cells.has(id));
  while (pending.length > 0) {
    const before = pending.length;
    pending = pending.filter((id) => {
      const anchor = (neighbours.get(id) ?? []).map((n) => cells.get(n)).find(Boolean);
      if (!anchor) return true;
      const cell = freeCellNear(anchor) ?? anyFreeCell();
      take(id, cell);
      memory.placed.set(id, cell);
      return false;
    });
    if (pending.length === before) {
      // Nothing placed links to the rest: start them anywhere free.
      const id = pending.shift()!;
      const cell = anyFreeCell();
      take(id, cell);
      memory.placed.set(id, cell);
    }
  }
  return cells;
};

/** Folds a session state into the run's memory and builds the board from it. */
export const sessionToBoard = (state: SessionState, memory: BoardMemory): SessionBoard => {
  if (memory.sessionId !== state.session_id) {
    memory.sessionId = state.session_id;
    memory.rooms.clear();
    memory.corridors.clear();
    memory.placed.clear();
  }

  const learn = (room: KnownRoom) => {
    const known = memory.rooms.get(room.id);
    if (!known) {
      memory.rooms.set(room.id, { ...room });
      return;
    }
    known.cell = room.cell ?? known.cell;
    known.size = room.size ?? known.size;
    known.floor = room.floor;
    // Only its door seen this time: a room already seen stays as it was.
    if (room.type === null) return;
    known.type = room.type;
    known.name = room.name;
    known.cleared = room.cleared;
    known.enemies = room.enemies ?? known.enemies;
    known.portal = room.portal ?? known.portal;
    known.dark = room.dark;
  };
  const scoutLabel = (s: NonNullable<SessionState['current_room']>['exits'][number]['scout']) => {
    if (!s) return undefined;
    const parts = [SCOUT_KIND[s.room_type] ?? 'комната'];
    if (s.mob_count) parts[0] += ` ×${s.mob_count}`;
    if (s.trap && !s.disarmed) parts.push('ловушка');
    if (s.ambush) parts.push('засада?');
    return parts.join(' · ');
  };

  (state.explored_rooms ?? []).forEach((r) =>
    learn({
      id: r.id,
      type: toBoardType(r.room_type, r.is_entrance),
      name: r.name,
      cell: gridCellOf(r.position_x, r.position_y),
      size: gridSizeOf(r.grid_w, r.grid_d),
      cleared: r.is_cleared || !!r.used,
      enemies: r.mob_count ?? undefined,
      portal: r.portal ?? undefined,
      floor: r.floor ?? 1,
      dark: !!r.dark,
    }),
  );

  const current = state.current_room;
  if (current) {
    learn({
      id: current.id,
      type: toBoardType(current.room_type, current.is_entrance),
      name: current.name,
      cell: gridCellOf(current.position_x, current.position_y),
      size: gridSizeOf(current.grid_w, current.grid_d),
      cleared:
        current.is_cleared ||
        (current.room_type === 'treasure' && !!current.room_config_visible?.loot_collected) ||
        (current.room_type === 'rest' && !!current.room_config_visible?.rest_used),
      enemies:
        typeof current.room_config_visible?.mob_count === 'number' ? current.room_config_visible.mob_count : undefined,
      portal:
        current.room_type === 'teleport' ? (current.room_config_visible?.portal === 'red' ? 'red' : 'blue') : undefined,
      floor: current.floor ?? 1,
      dark: !!current.dark,
    });
    current.exits.forEach((exit) => {
      const label = scoutLabel(exit.scout);
      const seen = memory.rooms.get(exit.to_room_id);
      if (seen && label) seen.scouted = label;
      learn({
        id: exit.to_room_id,
        type: null,
        name: UNKNOWN_NAME,
        cell: gridCellOf(exit.position_x, exit.position_y),
        size: gridSizeOf(exit.grid_w, exit.grid_d),
        cleared: false,
        floor: exit.to_floor ?? current.floor ?? 1,
        scouted: label,
      });
      memory.corridors.set(exit.corridor_id, {
        from: current.id,
        to: exit.to_room_id,
        lock: lockOf(exit),
        passage: exit.passage ?? 'corridor',
      });
    });
  }

  // Doors seen from rooms the party has left: the map keeps them (where, not what).
  (state.seen_doors ?? []).forEach((d) => {
    learn({
      id: d.to_room_id,
      type: null,
      name: UNKNOWN_NAME,
      cell: gridCellOf(d.position_x, d.position_y),
      size: gridSizeOf(d.grid_w, d.grid_d),
      cleared: false,
      floor: d.floor ?? memory.rooms.get(d.from_room_id)?.floor ?? 1,
    });
    memory.corridors.set(d.corridor_id, {
      from: d.from_room_id,
      to: d.to_room_id,
      lock: lockOf(d),
      passage: d.passage ?? 'corridor',
    });
  });

  // A door seen from behind its lock opens without a key: the current room's exits know best.
  const exitLocks = new Map((state.current_room?.exits ?? []).map((e) => [e.corridor_id, lockOf(e)]));
  (state.explored_corridors ?? []).forEach((c) => {
    if (memory.rooms.has(c.from_room_id) && memory.rooms.has(c.to_room_id)) {
      memory.corridors.set(c.corridor_id, {
        from: c.from_room_id,
        to: c.to_room_id,
        lock: exitLocks.has(c.corridor_id) ? exitLocks.get(c.corridor_id) : lockOf(c),
        passage: c.passage ?? 'corridor',
      });
    }
  });

  const revealed = new Set<number>();
  const cleared = new Set<number>();
  const floorOf = new Map<number, number>();
  memory.rooms.forEach((room) => {
    if (room.type !== null) revealed.add(room.id);
    if (room.type !== null && room.cleared) cleared.add(room.id);
    floorOf.set(room.id, room.floor);
  });
  const floor = current?.floor ?? 1;
  return {
    dungeon: boardOfFloor(memory, state.dungeon_name, floor, current?.id ?? null, floorTheme(state.theme, state.floor_themes, floor)),
    revealed,
    cleared,
    floor,
    floors: Math.max(state.floors ?? 1, ...floorOf.values()),
    floorOf,
  };
};

/** One floor of the remembered run, as the table lays it out. */
export const boardOfFloor = (
  memory: BoardMemory,
  name: string,
  floor: number,
  currentId: number | null,
  theme?: DungeonTheme,
): BoardDungeon => {
  const onFloor = new Set([...memory.rooms.values()].filter((r) => r.floor === floor).map((r) => r.id));
  const sameFloor = [...memory.corridors.values()].filter(
    (c) => c.passage === 'corridor' && onFloor.has(c.from) && onFloor.has(c.to),
  );
  // Stairs, drops and lifts start in a room of this floor and lead to the next one.
  const passages = new Map<number, BoardPassage[]>();
  memory.corridors.forEach((c) => {
    if (c.passage === 'corridor') return;
    [
      [c.from, c.to],
      [c.to, c.from],
    ].forEach(([here, there]) => {
      if (!onFloor.has(here)) return;
      const thereFloor = memory.rooms.get(there)?.floor;
      if (thereFloor === undefined || thereFloor === floor) return;
      const dir = thereFloor > floor ? 'down' : 'up';
      if (c.passage === 'drop' && dir === 'up') return; // a drop is one way: nothing to climb from below
      const list = passages.get(here) ?? [];
      if (!list.some((p) => p.target === there)) {
        list.push({ kind: c.passage as BoardPassage['kind'], dir, target: there, lock: c.lock });
      }
      passages.set(here, list);
    });
  });

  const cells = placeRooms(memory, onFloor, sameFloor);
  const rooms: BoardRoom[] = [];
  memory.rooms.forEach((room) => {
    if (!onFloor.has(room.id)) return;
    const [col, row] = cells.get(room.id)!;
    rooms.push({
      id: room.id,
      type: room.type ?? UNKNOWN_TYPE,
      name: room.type !== null ? room.name || 'Без названия' : UNKNOWN_NAME,
      col,
      row,
      size: room.size,
      enemies: room.type !== null ? room.enemies : undefined,
      portal: room.type !== null ? room.portal : undefined,
      passages: room.type !== null ? passages.get(room.id) : undefined,
      dark: room.type !== null ? room.dark : undefined,
      scouted: room.type === null ? room.scouted : undefined,
    });
  });

  // One path per pair of rooms, however many corridors join them.
  const pairs = new Map<string, BoardCorridor>();
  sameFloor.forEach(({ from, to, lock }) => {
    const key = `${Math.min(from, to)}-${Math.max(from, to)}`;
    if (from === to) return;
    const known = pairs.get(key);
    if (known) {
      known.lock = known.lock ?? lock;
      return;
    }
    pairs.set(key, { from, to, lock });
  });
  const corridors = [...pairs.values()];

  const entrance = [...memory.rooms.values()].find((r) => r.type === 'entrance' && r.floor === floor);
  return {
    name,
    theme,
    rooms,
    corridors,
    entranceId: entrance?.id ?? (currentId !== null && onFloor.has(currentId) ? currentId : rooms[0]?.id ?? 0),
  };
};

/** What a scout calls a room's kind, on its label over the rock. */
const SCOUT_KIND: Record<string, string> = {
  battle: 'бой',
  boss: 'логово босса',
  treasure: 'сокровищница',
  trap: 'комната-ловушка',
  event: 'событие',
  rest: 'привал',
  merchant: 'торговец',
  teleport: 'портал',
  fork: 'развилка',
  deadend: 'тупик',
};

/** The party as figurines: a colour per member in a stable order, the leader marked, the fallen laid down,
 *  the one holding up the party shield (if any) glowing behind it. */
export const membersToPawns = (
  members: SessionMember[],
  shieldHolder: number | null = null,
  speech: Map<number, { text: string; at: number }> = new Map(),
  busy: Map<number, MemberBusy> = new Map(),
): BoardMember[] =>
  [...members]
    .sort((a, b) => a.character_id - b.character_id)
    .map((m, i) => ({
      id: m.character_id,
      name: m.name,
      color: MEMBER_COLORS[i % MEMBER_COLORS.length],
      leader: m.is_leader,
      dead: m.status === 'dead',
      classId: m.class_id,
      avatar: m.avatar,
      level: m.level,
      shielded: m.character_id === shieldHolder,
      speech: speech.get(m.character_id) ?? null,
      busy: busy.get(m.character_id) ?? null,
    }));
