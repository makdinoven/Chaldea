import type { DungeonRoom, DungeonCorridor } from '../../../../api/dungeons';
import { LAYOUT_SPACING } from './constants';

interface PositionedRoom {
  room_id: number;
  position_x: number;
  position_y: number;
}

/**
 * Auto-layout rooms in a grid pattern using BFS from the entrance.
 * Rooms that already have position_x/position_y keep their positions.
 * Unreachable rooms are placed in a row below the main grid.
 */
export const autoLayoutRooms = (
  rooms: DungeonRoom[],
  corridors: DungeonCorridor[],
): PositionedRoom[] => {
  if (rooms.length === 0) return [];

  // Build adjacency list (both directions for bidirectional corridors)
  const adj = new Map<number, number[]>();
  for (const room of rooms) {
    adj.set(room.id, []);
  }
  for (const c of corridors) {
    adj.get(c.from_room_id)?.push(c.to_room_id);
    if (c.is_bidirectional) {
      adj.get(c.to_room_id)?.push(c.from_room_id);
    }
  }

  // Identify rooms with existing positions (skip in auto-layout)
  const hasPosition = new Set<number>();
  for (const room of rooms) {
    if (room.position_x != null && room.position_y != null) {
      hasPosition.add(room.id);
    }
  }

  // Find entrance room, fall back to first room
  const entrance = rooms.find((r) => r.is_entrance) ?? rooms[0];

  // BFS from entrance
  const visited = new Set<number>();
  const positions = new Map<number, { x: number; y: number }>();

  // Queue entries: [roomId, gridX, gridY]
  const queue: [number, number, number][] = [[entrance.id, 0, 0]];
  visited.add(entrance.id);

  // Track occupied grid cells to avoid overlap
  const occupiedCells = new Set<string>();

  // Pre-mark cells for rooms that already have positions
  // (We don't place them on the BFS grid, but we record their existence)

  while (queue.length > 0) {
    const [roomId, gx, gy] = queue.shift()!;

    // If this room already has a saved position, keep it
    if (hasPosition.has(roomId)) {
      const room = rooms.find((r) => r.id === roomId)!;
      positions.set(roomId, { x: room.position_x!, y: room.position_y! });
    } else {
      // Find a free cell near the target grid position
      const pos = findFreeCell(gx, gy, occupiedCells);
      occupiedCells.add(`${pos.x},${pos.y}`);
      positions.set(roomId, {
        x: pos.x * LAYOUT_SPACING,
        y: pos.y * LAYOUT_SPACING,
      });
    }

    // Enqueue neighbors
    const neighbors = adj.get(roomId) ?? [];
    let dirIndex = 0;
    // Directions: right, down, left, up
    const directions = [
      [1, 0],
      [0, 1],
      [-1, 0],
      [0, -1],
    ];

    for (const neighborId of neighbors) {
      if (visited.has(neighborId)) continue;
      visited.add(neighborId);

      const dir = directions[dirIndex % directions.length];
      dirIndex++;
      queue.push([neighborId, gx + dir[0], gy + dir[1]]);
    }
  }

  // Place rooms not reached by BFS in a line below
  let maxY = 0;
  for (const { y } of positions.values()) {
    if (y > maxY) maxY = y;
  }
  const orphanY = maxY + LAYOUT_SPACING * 2;
  let orphanX = 0;

  for (const room of rooms) {
    if (!positions.has(room.id)) {
      if (hasPosition.has(room.id)) {
        positions.set(room.id, { x: room.position_x!, y: room.position_y! });
      } else {
        positions.set(room.id, { x: orphanX, y: orphanY });
        orphanX += LAYOUT_SPACING;
      }
    }
  }

  // Build result
  const result: PositionedRoom[] = [];
  for (const room of rooms) {
    const pos = positions.get(room.id)!;
    result.push({
      room_id: room.id,
      position_x: pos.x,
      position_y: pos.y,
    });
  }

  return result;
};

/**
 * Find a free grid cell starting from (targetX, targetY).
 * If the target cell is occupied, spiral outward to find a free one.
 */
const findFreeCell = (
  targetX: number,
  targetY: number,
  occupied: Set<string>,
): { x: number; y: number } => {
  const key = `${targetX},${targetY}`;
  if (!occupied.has(key)) {
    return { x: targetX, y: targetY };
  }

  // Spiral search
  for (let radius = 1; radius <= 20; radius++) {
    for (let dx = -radius; dx <= radius; dx++) {
      for (let dy = -radius; dy <= radius; dy++) {
        if (Math.abs(dx) !== radius && Math.abs(dy) !== radius) continue;
        const k = `${targetX + dx},${targetY + dy}`;
        if (!occupied.has(k)) {
          return { x: targetX + dx, y: targetY + dy };
        }
      }
    }
  }

  // Fallback (very unlikely)
  return { x: targetX + 100, y: targetY };
};
