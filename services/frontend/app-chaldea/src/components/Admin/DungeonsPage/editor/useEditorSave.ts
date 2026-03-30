import { useState, useCallback } from 'react';
import toast from 'react-hot-toast';
import type { DungeonRoom, DungeonCorridor } from '../../../../api/dungeons';
import {
  createRoom,
  updateRoom,
  deleteRoom,
  createCorridor,
  updateCorridor,
  deleteCorridor,
  bulkUpdateRoomPositions,
} from '../../../../api/dungeons';

interface UseEditorSaveProps {
  dungeonId: number;
  serverRooms: DungeonRoom[];
  serverCorridors: DungeonCorridor[];
  currentRooms: DungeonRoom[];
  currentCorridors: DungeonCorridor[];
  onSaveComplete: () => void;
}

interface UseEditorSaveReturn {
  save: () => Promise<void>;
  isSaving: boolean;
}

const roomFieldsChanged = (a: DungeonRoom, b: DungeonRoom): boolean => {
  return (
    a.room_type !== b.room_type ||
    a.name !== b.name ||
    a.description !== b.description ||
    a.image_url !== b.image_url ||
    a.sort_order !== b.sort_order ||
    a.is_entrance !== b.is_entrance ||
    a.is_boss_room !== b.is_boss_room ||
    a.is_mana_core_room !== b.is_mana_core_room ||
    JSON.stringify(a.room_config) !== JSON.stringify(b.room_config)
  );
};

const corridorFieldsChanged = (a: DungeonCorridor, b: DungeonCorridor): boolean => {
  return (
    a.stamina_cost !== b.stamina_cost ||
    a.is_bidirectional !== b.is_bidirectional ||
    a.random_battle_chance !== b.random_battle_chance ||
    JSON.stringify(a.random_battle_mob_ids) !== JSON.stringify(b.random_battle_mob_ids) ||
    a.trap_chance !== b.trap_chance ||
    JSON.stringify(a.trap_config) !== JSON.stringify(b.trap_config) ||
    a.description !== b.description ||
    a.source_handle !== b.source_handle ||
    a.target_handle !== b.target_handle
  );
};

const useEditorSave = ({
  dungeonId,
  serverRooms,
  serverCorridors,
  currentRooms,
  currentCorridors,
  onSaveComplete,
}: UseEditorSaveProps): UseEditorSaveReturn => {
  const [isSaving, setIsSaving] = useState(false);

  const save = useCallback(async () => {
    setIsSaving(true);

    // Map temp IDs (negative) to real IDs after creation
    const tempToRealId = new Map<number, number>();

    try {
      // Step 1: Delete removed rooms
      const currentRoomIds = new Set(currentRooms.map((r) => r.id));
      const deletedRooms = serverRooms.filter((r) => !currentRoomIds.has(r.id));

      for (const room of deletedRooms) {
        await deleteRoom(room.id);
      }

      // Step 2: Create new rooms (negative temp IDs)
      const newRooms = currentRooms.filter((r) => r.id < 0);

      for (const room of newRooms) {
        const { id: _tempId, dungeon_id: _dId, ...payload } = room;
        const created = await createRoom(dungeonId, payload);
        tempToRealId.set(room.id, created.id);
      }

      // Step 3: Update changed rooms
      const serverRoomMap = new Map(serverRooms.map((r) => [r.id, r]));
      const updatedRooms = currentRooms.filter((r) => {
        if (r.id < 0) return false;
        const server = serverRoomMap.get(r.id);
        if (!server) return false;
        return roomFieldsChanged(r, server);
      });

      for (const room of updatedRooms) {
        const { id: _id, dungeon_id: _dId, ...payload } = room;
        await updateRoom(room.id, payload);
      }

      // Step 4: Bulk update positions for all rooms (except deleted ones)
      const positionsPayload = currentRooms.map((r) => ({
        room_id: tempToRealId.get(r.id) ?? r.id,
        position_x: r.position_x ?? 0,
        position_y: r.position_y ?? 0,
      }));

      if (positionsPayload.length > 0) {
        await bulkUpdateRoomPositions(dungeonId, positionsPayload);
      }

      // Step 5: Delete removed corridors
      const currentCorridorIds = new Set(currentCorridors.map((c) => c.id));
      const deletedCorridors = serverCorridors.filter((c) => !currentCorridorIds.has(c.id));

      for (const corridor of deletedCorridors) {
        await deleteCorridor(corridor.id);
      }

      // Step 6: Create new corridors (negative temp IDs), map room IDs
      const newCorridors = currentCorridors.filter((c) => c.id < 0);

      for (const corridor of newCorridors) {
        const fromId = tempToRealId.get(corridor.from_room_id) ?? corridor.from_room_id;
        const toId = tempToRealId.get(corridor.to_room_id) ?? corridor.to_room_id;
        const { id: _id, dungeon_id: _dId, ...payload } = corridor;
        await createCorridor(dungeonId, {
          ...payload,
          from_room_id: fromId,
          to_room_id: toId,
        });
      }

      // Step 7: Update changed corridors
      const serverCorridorMap = new Map(serverCorridors.map((c) => [c.id, c]));
      const updatedCorridors = currentCorridors.filter((c) => {
        if (c.id < 0) return false;
        const server = serverCorridorMap.get(c.id);
        if (!server) return false;
        return corridorFieldsChanged(c, server);
      });

      for (const corridor of updatedCorridors) {
        const { id: _id, dungeon_id: _dId, from_room_id: _from, to_room_id: _to, ...payload } = corridor;
        await updateCorridor(corridor.id, payload);
      }

      // Step 8: Reload data
      onSaveComplete();
      toast.success('Изменения сохранены');
    } catch (err: unknown) {
      let message = 'Неизвестная ошибка';
      if (err instanceof Error) message = err.message;
      if (typeof err === 'object' && err !== null && 'response' in err) {
        const resp = (err as { response?: { status?: number; data?: { detail?: string }; config?: { url?: string; method?: string } } }).response;
        const detail = resp?.data?.detail;
        const url = resp?.config?.url ?? '';
        const method = resp?.config?.method ?? '';
        message = `${resp?.status} ${method.toUpperCase()} ${url}${detail ? ': ' + (typeof detail === 'string' ? detail : JSON.stringify(detail)) : ''}`;
      }
      toast.error(`Ошибка сохранения: ${message}`);
    } finally {
      setIsSaving(false);
    }
  }, [dungeonId, serverRooms, serverCorridors, currentRooms, currentCorridors, onSaveComplete]);

  return { save, isSaving };
};

export default useEditorSave;
