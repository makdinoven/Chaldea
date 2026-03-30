import type { Node, Edge } from 'reactflow';
import type { DungeonRoom, DungeonCorridor } from '../../../../api/dungeons';

// Room types
export type RoomType = 'battle' | 'boss' | 'treasure' | 'trap' | 'event' | 'rest' | 'merchant' | 'fork' | 'teleport' | 'deadend';

// Data stored in React Flow nodes
export interface RoomNodeData {
  room: DungeonRoom;
  isNew: boolean;        // true for rooms not yet saved to server
  isDirty: boolean;      // true for rooms with unsaved changes
  onSelect: (room: DungeonRoom) => void;
}

// Data stored in React Flow edges
export interface CorridorEdgeData {
  corridor: DungeonCorridor;
  isNew: boolean;
  isDirty: boolean;
}

// React Flow typed aliases
export type RoomFlowNode = Node<RoomNodeData>;
export type CorridorFlowEdge = Edge<CorridorEdgeData>;
