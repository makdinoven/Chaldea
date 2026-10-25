import type { DungeonCorridor, DungeonRoom } from '../../api/dungeons';
import type { DungeonTheme } from './dungeonThemes';
import type { BoardDungeon, BoardRoomType } from './boardTypes';

/*
  The admin editor's rooms and corridors as a board for the 3D miniature. One
  cell of the editor's grid is one room slot on the table.
*/

/** Editor pixels per room slot: the editor snaps rooms to this grid. */
export const ROOM_CELL_PX = 180;

/** The board cell of an editor position, or null when the room was never placed. */
export const gridCellOf = (x: number | null | undefined, y: number | null | undefined): [number, number] | null =>
  x == null || y == null ? null : [Math.round(x / ROOM_CELL_PX), Math.round(y / ROOM_CELL_PX)];

/** A room's footprint override from the editor (grid_w × grid_d), when it has one. */
export const gridSizeOf = (w: number | null | undefined, d: number | null | undefined): [number, number] | undefined =>
  w && d ? [w, d] : undefined;

/** What a room looks like on the table: the entrance flag wins over its kind. */
export const boardTypeOf = (room: Pick<DungeonRoom, 'room_type' | 'is_entrance'>): BoardRoomType =>
  room.is_entrance ? 'entrance' : room.room_type;

export const editorToBoard = (
  name: string,
  rooms: DungeonRoom[],
  corridors: DungeonCorridor[],
  theme?: DungeonTheme,
): BoardDungeon => {
  const entrance = rooms.find((r) => r.is_entrance) ?? rooms[0];
  return {
    name,
    theme,
    entranceId: entrance?.id ?? 0,
    rooms: rooms.map((r) => {
      const [col, row] = gridCellOf(r.position_x ?? 0, r.position_y ?? 0)!;
      return {
        id: r.id,
        type: boardTypeOf(r),
        name: r.name || 'Без названия',
        col,
        row,
        size: gridSizeOf(r.grid_w, r.grid_d),
      };
    }),
    corridors: corridors.map((c) => ({
      from: c.from_room_id,
      to: c.to_room_id,
      risky: c.random_battle_chance > 0 || c.trap_chance > 0,
    })),
  };
};
