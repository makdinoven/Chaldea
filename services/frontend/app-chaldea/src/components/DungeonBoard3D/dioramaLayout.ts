import type { BoardDungeon, BoardRoomType } from './boardTypes';

/*
  Turns a dungeon graph into a miniature: every room becomes a block of floor
  squares, every corridor a one-square-wide path routed along the grid, and a
  wall stands on every edge where floor meets nothing — so doorways appear by
  themselves wherever a corridor runs into a room.
*/

/** Side of one floor square, in world units. */
export const SQUARE = 0.42;
/** Squares between the centres of neighbouring rooms on the dungeon's grid. */
const ROOM_SPACING = 7;

/** Room sizes in squares (width × depth); the boss's lair is the biggest. */
export const FOOTPRINT: Record<BoardRoomType, [number, number]> = {
  entrance: [3, 3],
  battle: [4, 4],
  boss: [5, 5],
  treasure: [3, 3],
  trap: [3, 4],
  event: [4, 4],
  rest: [3, 3],
  merchant: [4, 3],
  teleport: [3, 3],
  fork: [3, 3],
  deadend: [3, 3],
};

/** Who a square or wall belongs to: a room, or a corridor between two rooms. */
export type PieceOwner = { kind: 'room'; id: number } | { kind: 'corridor'; key: string };

export const ownerKey = (owner: PieceOwner) => (owner.kind === 'room' ? `r${owner.id}` : `c${owner.key}`);
export const corridorKey = (from: number, to: number) => `${Math.min(from, to)}-${Math.max(from, to)}`;

export interface FloorSquare {
  x: number;
  z: number;
}

export interface WallSegment {
  /** World position of the segment's middle (on the floor). */
  x: number;
  z: number;
  /** Runs along x (true) or along z (false). */
  alongX: boolean;
  /** Which side of its square it bounds: used to pick walls the camera sees well. */
  side: 'north' | 'south' | 'west' | 'east';
}

export interface Piece {
  owner: PieceOwner;
  floor: FloorSquare[];
  walls: WallSegment[];
  pillars: FloorSquare[];
}

export interface RoomInfo {
  id: number;
  type: BoardRoomType;
  /** Picks the landmark of an event room ("Алтарь…" gets the altar). */
  name?: string;
  /** World centre of the room's floor. */
  center: [number, number];
  /** World size of the room's floor. */
  size: [number, number];
}

/** Where a corridor runs into a room: the gap in the wall a door stands in. */
export interface Doorway {
  roomId: number;
  /** `corridorKey(from, to)` of the corridor it ends. */
  corridor: string;
  /** World position of the middle of the gap (on the floor). */
  x: number;
  z: number;
  /** Unit step from the corridor into the room. */
  into: [number, number];
}

export interface DioramaLayout {
  pieces: Map<string, Piece>;
  rooms: Map<number, RoomInfo>;
  /** One per corridor end: the door into each room a corridor reaches. */
  doorways: Doorway[];
  /** Problems an editor should hear about: rooms overlapping, corridors cutting through rooms. */
  warnings: string[];
  /** World size of the area the dungeon covers, for sizing the board under it. */
  width: number;
  depth: number;
  /** World centre of that area: the board is laid under it. (0, 0) unless `fixedOrigin`. */
  center: [number, number];
}

export interface DioramaLayoutOptions {
  /**
   * Keep grid cell (0, 0) at the world origin instead of centring the dungeon.
   * A live run uses it: rooms appear one by one, and centring would shift every
   * room already on the board each time the known map grows.
   */
  fixedOrigin?: boolean;
}

const cellKey = (x: number, z: number) => `${x},${z}`;

export const buildDioramaLayout = (dungeon: BoardDungeon, options: DioramaLayoutOptions = {}): DioramaLayout => {
  const owners = new Map<string, PieceOwner>();
  const warnings: string[] = [];
  const nameOf = new Map(dungeon.rooms.map((r) => [r.id, r.name]));
  const overlapping = new Set<string>();
  const roomCells = new Map<number, { x0: number; z0: number; w: number; d: number; cx: number; cz: number }>();

  // Rooms: a block of squares around the room's grid point.
  dungeon.rooms.forEach((room) => {
    const [w, d] = room.size ?? FOOTPRINT[room.type];
    const cx = room.col * ROOM_SPACING;
    const cz = room.row * ROOM_SPACING;
    const x0 = cx - Math.floor(w / 2);
    const z0 = cz - Math.floor(d / 2);
    roomCells.set(room.id, { x0, z0, w, d, cx, cz });
    for (let x = x0; x < x0 + w; x++) {
      for (let z = z0; z < z0 + d; z++) {
        const k = cellKey(x, z);
        const other = owners.get(k);
        if (other?.kind === 'room' && other.id !== room.id) {
          const pair = [other.id, room.id].sort((a, b) => a - b).join('-');
          if (!overlapping.has(pair)) {
            overlapping.add(pair);
            warnings.push(`Комнаты «${nameOf.get(other.id)}» и «${room.name}» наезжают друг на друга — разнесите их.`);
          }
        }
        owners.set(k, { kind: 'room', id: room.id });
      }
    }
  });

  /** Squares of a corridor turning once: along x first, or along z first. */
  const route = (a: { cx: number; cz: number }, b: { cx: number; cz: number }, xFirst: boolean) => {
    const cells: [number, number][] = [];
    const stepX = Math.sign(b.cx - a.cx);
    const stepZ = Math.sign(b.cz - a.cz);
    if (xFirst) {
      for (let x = a.cx; x !== b.cx; x += stepX) cells.push([x, a.cz]);
      for (let z = a.cz; z !== b.cz; z += stepZ) cells.push([b.cx, z]);
    } else {
      for (let z = a.cz; z !== b.cz; z += stepZ) cells.push([a.cx, z]);
      for (let x = a.cx; x !== b.cx; x += stepX) cells.push([x, b.cz]);
    }
    cells.push([b.cx, b.cz]);
    return cells;
  };
  /** Rooms (other than its own two) a route would cut through. */
  const crossed = (cells: [number, number][], from: number, to: number) => {
    const ids = new Set<number>();
    cells.forEach(([x, z]) => {
      const o = owners.get(cellKey(x, z));
      if (o?.kind === 'room' && o.id !== from && o.id !== to) ids.add(o.id);
    });
    return ids;
  };

  // Corridors: along the first room's row, then down the second room's column.
  dungeon.corridors.forEach(({ from, to }) => {
    const a = roomCells.get(from);
    const b = roomCells.get(to);
    if (!a || !b) return;
    const owner: PieceOwner = { kind: 'corridor', key: corridorKey(from, to) };
    const claim = (x: number, z: number) => {
      const k = cellKey(x, z);
      if (!owners.has(k)) owners.set(k, owner);
    };
    // Of the two ways to turn, take the one that doesn't cut through another room.
    const xFirst = route(a, b, true);
    const zFirst = route(a, b, false);
    const crossX = crossed(xFirst, from, to);
    const crossZ = crossed(zFirst, from, to);
    const best = crossX.size <= crossZ.size ? { cells: xFirst, cross: crossX } : { cells: zFirst, cross: crossZ };
    if (best.cross.size > 0) {
      const through = [...best.cross].map((id) => `«${nameOf.get(id)}»`).join(', ');
      warnings.push(
        `Коридор «${nameOf.get(from)}» — «${nameOf.get(to)}» проходит через ${through}: передвиньте комнаты, чтобы путь был свободен.`,
      );
    }
    best.cells.forEach(([x, z]) => claim(x, z));
  });

  // Centre the whole dungeon on the board.
  const cells = [...owners.keys()].map((k) => k.split(',').map(Number) as [number, number]);
  if (cells.length === 0) {
    return { pieces: new Map(), rooms: new Map(), doorways: [], warnings, width: 4, depth: 4, center: [0, 0] };
  }
  const xs = cells.map(([x]) => x);
  const zs = cells.map(([, z]) => z);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minZ = Math.min(...zs);
  const maxZ = Math.max(...zs);
  const offX = options.fixedOrigin ? 0.5 : (minX + maxX + 1) / 2;
  const offZ = options.fixedOrigin ? 0.5 : (minZ + maxZ + 1) / 2;
  const wx = (x: number) => (x - offX + 0.5) * SQUARE;
  const wz = (z: number) => (z - offZ + 0.5) * SQUARE;

  const pieces = new Map<string, Piece>();
  const pieceOf = (owner: PieceOwner) => {
    const key = ownerKey(owner);
    let piece = pieces.get(key);
    if (!piece) {
      piece = { owner, floor: [], walls: [], pillars: [] };
      pieces.set(key, piece);
    }
    return piece;
  };
  const pillarSeen = new Set<string>();
  const addPillar = (piece: Piece, gx: number, gz: number) => {
    const k = `${gx},${gz}`;
    if (pillarSeen.has(k)) return;
    pillarSeen.add(k);
    piece.pillars.push({ x: (gx - offX) * SQUARE, z: (gz - offZ) * SQUARE });
  };

  // The corridor square touching a room, nearest the room's middle, holds the door.
  const doorwayAt = new Map<string, { doorway: Doorway; distance: number }>();
  const noteDoorway = (key: string, x: number, z: number, dx: number, dz: number) => {
    const neighbour = owners.get(cellKey(x + dx, z + dz));
    if (neighbour?.kind !== 'room') return;
    const [a, b] = key.split('-').map(Number);
    if (neighbour.id !== a && neighbour.id !== b) return;
    const c = roomCells.get(neighbour.id)!;
    const distance = Math.abs(x + dx - c.cx) + Math.abs(z + dz - c.cz);
    const id = `${key}|${neighbour.id}`;
    const known = doorwayAt.get(id);
    if (known && known.distance <= distance) return;
    doorwayAt.set(id, {
      distance,
      doorway: {
        roomId: neighbour.id,
        corridor: key,
        x: wx(x) + (dx * SQUARE) / 2,
        z: wz(z) + (dz * SQUARE) / 2,
        into: [dx, dz],
      },
    });
  };

  owners.forEach((owner, k) => {
    const [x, z] = k.split(',').map(Number);
    const piece = pieceOf(owner);
    if (owner.kind === 'corridor') {
      noteDoorway(owner.key, x, z, 0, -1);
      noteDoorway(owner.key, x, z, 0, 1);
      noteDoorway(owner.key, x, z, -1, 0);
      noteDoorway(owner.key, x, z, 1, 0);
    }
    piece.floor.push({ x: wx(x), z: wz(z) });
    const open = (nx: number, nz: number) => owners.has(cellKey(nx, nz));
    if (!open(x, z - 1)) {
      piece.walls.push({ x: wx(x), z: wz(z) - SQUARE / 2, alongX: true, side: 'north' });
      addPillar(piece, x, z);
      addPillar(piece, x + 1, z);
    }
    if (!open(x, z + 1)) {
      piece.walls.push({ x: wx(x), z: wz(z) + SQUARE / 2, alongX: true, side: 'south' });
      addPillar(piece, x, z + 1);
      addPillar(piece, x + 1, z + 1);
    }
    if (!open(x - 1, z)) {
      piece.walls.push({ x: wx(x) - SQUARE / 2, z: wz(z), alongX: false, side: 'west' });
      addPillar(piece, x, z);
      addPillar(piece, x, z + 1);
    }
    if (!open(x + 1, z)) {
      piece.walls.push({ x: wx(x) + SQUARE / 2, z: wz(z), alongX: false, side: 'east' });
      addPillar(piece, x + 1, z);
      addPillar(piece, x + 1, z + 1);
    }
  });

  const rooms = new Map<number, RoomInfo>();
  dungeon.rooms.forEach((room) => {
    const c = roomCells.get(room.id)!;
    rooms.set(room.id, {
      id: room.id,
      type: room.type,
      name: room.name,
      center: [wx(c.x0) + ((c.w - 1) * SQUARE) / 2, wz(c.z0) + ((c.d - 1) * SQUARE) / 2],
      size: [c.w * SQUARE, c.d * SQUARE],
    });
  });

  return {
    pieces,
    rooms,
    doorways: [...doorwayAt.values()].map((d) => d.doorway),
    warnings,
    width: (maxX - minX + 1) * SQUARE,
    depth: (maxZ - minZ + 1) * SQUARE,
    center: [((minX + maxX + 1) / 2 - offX) * SQUARE, ((minZ + maxZ + 1) / 2 - offZ) * SQUARE],
  };
};
