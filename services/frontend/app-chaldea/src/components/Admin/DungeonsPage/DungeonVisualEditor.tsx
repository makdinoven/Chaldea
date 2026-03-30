import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  ConnectionMode,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  type Connection,
  type NodeChange,
  type EdgeChange,
  type Node,
  type Edge,
} from 'reactflow';
import 'reactflow/dist/style.css';
import toast from 'react-hot-toast';

import type { DungeonRoom, DungeonCorridor } from '../../../api/dungeons';
import { validateDungeon } from '../../../api/dungeons';
import type { RoomNodeData, RoomFlowNode } from './editor/types';
import { GRID_SIZE, ROOM_TYPE_LABELS } from './editor/constants';
import RoomNode from './editor/RoomNode';
import RoomPalette from './editor/RoomPalette';
import PropertyPanel from './editor/PropertyPanel';
import EditorToolbar from './editor/EditorToolbar';
import { autoLayoutRooms } from './editor/autoLayout';
import useEditorSave from './editor/useEditorSave';

interface DungeonVisualEditorProps {
  dungeonId: number;
  rooms: DungeonRoom[];
  corridors: DungeonCorridor[];
  onUpdate: () => void;
}

const nodeTypes = { room: RoomNode };

const snapToGrid = (value: number): number => Math.round(value / GRID_SIZE) * GRID_SIZE;

// --- Conversion helpers ---

const roomToNode = (
  room: DungeonRoom,
  serverRoomIds: Set<number>,
  dirtyRoomIds: Set<number>,
  onSelect: (room: DungeonRoom) => void,
): RoomFlowNode => ({
  id: String(room.id),
  type: 'room',
  position: { x: room.position_x ?? 0, y: room.position_y ?? 0 },
  data: {
    room,
    isNew: !serverRoomIds.has(room.id),
    isDirty: dirtyRoomIds.has(room.id),
    onSelect,
  },
});

const corridorToEdge = (
  corridor: DungeonCorridor,
  sourceHandle?: string,
  targetHandle?: string,
): Edge => ({
  id: String(corridor.id),
  source: String(corridor.from_room_id),
  target: String(corridor.to_room_id),
  sourceHandle,
  targetHandle,
  type: 'smoothstep',
  animated: corridor.id < 0,
  label: `${corridor.stamina_cost} ⚡`,
  style: { stroke: corridor.is_bidirectional ? '#60a5fa' : '#f59e0b', strokeWidth: 2 },
  labelStyle: { fill: '#d4d4d8', fontSize: 10 },
  labelBgStyle: { fill: '#1e1e2e', fillOpacity: 0.85 },
  data: { corridor },
});

/** Extract DungeonCorridor from an edge's data */
const corridorFromEdge = (edge: Edge): DungeonCorridor | null =>
  (edge.data as { corridor?: DungeonCorridor } | undefined)?.corridor ?? null;

// --- Inner editor (needs ReactFlowProvider above) ---

const EditorInner = ({ dungeonId, rooms: serverRooms, corridors: serverCorridors, onUpdate }: DungeonVisualEditorProps) => {
  const { fitView, zoomIn, zoomOut, screenToFlowPosition } = useReactFlow();

  // Temp ID counter
  const tempIdRef = useRef(-1);
  const nextTempId = () => {
    const id = tempIdRef.current;
    tempIdRef.current -= 1;
    return id;
  };

  // Room domain state
  const [currentRooms, setCurrentRooms] = useState<DungeonRoom[]>([]);

  // Selection state
  const [selectedRoom, setSelectedRoom] = useState<DungeonRoom | null>(null);
  const [selectedCorridor, setSelectedCorridor] = useState<DungeonCorridor | null>(null);

  // Dirty tracking
  const [dirtyRoomIds, setDirtyRoomIds] = useState<Set<number>>(new Set());
  const [isDirty, setIsDirty] = useState(false);

  // Server IDs for "isNew" detection
  const serverRoomIds = useMemo(() => new Set(serverRooms.map((r) => r.id)), [serverRooms]);

  // React Flow state — edges are source of truth for corridors
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState([] as Node[]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState([] as Edge[]);

  // Derive currentCorridors from rfEdges (for save hook and property panel)
  const currentCorridors = useMemo(
    () => rfEdges.map(corridorFromEdge).filter((c): c is DungeonCorridor => c !== null),
    [rfEdges],
  );

  // --- Initialize from server data ---
  useEffect(() => {
    const needsLayout = serverRooms.some((r) => r.position_x == null || r.position_y == null);
    let layoutRooms = [...serverRooms];

    if (needsLayout) {
      const positions = autoLayoutRooms(serverRooms, serverCorridors);
      layoutRooms = serverRooms.map((room) => {
        const pos = positions.find((p) => p.room_id === room.id);
        if (pos && (room.position_x == null || room.position_y == null)) {
          return { ...room, position_x: pos.position_x, position_y: pos.position_y };
        }
        return room;
      });
    }

    setCurrentRooms(layoutRooms);
    setDirtyRoomIds(new Set());
    setIsDirty(needsLayout);
    setSelectedRoom(null);
    setSelectedCorridor(null);
    tempIdRef.current = -1;

    // Build initial edges — use handle positions from server data, auto-assign if missing
    const roomMap = new Map(layoutRooms.map((r) => [r.id, r]));
    const initialEdges = serverCorridors.map((c) => {
      let srcH = c.source_handle ?? undefined;
      let tgtH = c.target_handle ?? undefined;

      // Auto-assign handles based on relative room positions if missing
      if (!srcH || !tgtH) {
        const fromRoom = roomMap.get(c.from_room_id);
        const toRoom = roomMap.get(c.to_room_id);
        if (fromRoom && toRoom) {
          const dx = (toRoom.position_x ?? 0) - (fromRoom.position_x ?? 0);
          const dy = (toRoom.position_y ?? 0) - (fromRoom.position_y ?? 0);
          if (Math.abs(dx) > Math.abs(dy)) {
            srcH = srcH ?? (dx > 0 ? 'r-2' : 'l-2');
            tgtH = tgtH ?? (dx > 0 ? 'l-2' : 'r-2');
          } else {
            srcH = srcH ?? (dy > 0 ? 'b-2' : 't-2');
            tgtH = tgtH ?? (dy > 0 ? 't-2' : 'b-2');
          }
        }
      }
      return corridorToEdge(c, srcH, tgtH);
    });
    setRfEdges(initialEdges);

    // Mark dirty if any corridor needs handle auto-assignment (so save will persist them)
    const needsHandleSave = serverCorridors.some((c) => !c.source_handle || !c.target_handle);
    if (needsHandleSave) setIsDirty(true);
  }, [serverRooms, serverCorridors, setRfEdges]);

  // --- Sync room nodes from domain state ---
  const onSelectRoom = useCallback((room: DungeonRoom) => {
    setSelectedRoom(room);
    setSelectedCorridor(null);
  }, []);

  const nodes: RoomFlowNode[] = useMemo(
    () => currentRooms.map((r) => roomToNode(r, serverRoomIds, dirtyRoomIds, onSelectRoom)),
    [currentRooms, serverRoomIds, dirtyRoomIds, onSelectRoom],
  );

  useEffect(() => {
    setRfNodes(nodes);
  }, [nodes, setRfNodes]);

  // --- Save hook ---
  const { save, isSaving } = useEditorSave({
    dungeonId,
    serverRooms,
    serverCorridors,
    currentRooms,
    currentCorridors,
    onSaveComplete: () => {
      setIsDirty(false);
      onUpdate();
    },
  });

  // --- Handlers ---

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      onNodesChange(changes);

      for (const change of changes) {
        if (change.type === 'position' && change.position) {
          const roomId = Number(change.id);
          const snappedX = snapToGrid(change.position.x);
          const snappedY = snapToGrid(change.position.y);
          setCurrentRooms((prev) =>
            prev.map((r) => (r.id === roomId ? { ...r, position_x: snappedX, position_y: snappedY } : r)),
          );
          setDirtyRoomIds((prev) => new Set(prev).add(roomId));
          setIsDirty(true);
        }

        if (change.type === 'select' && change.selected) {
          const roomId = Number(change.id);
          const room = currentRooms.find((r) => r.id === roomId);
          if (room) {
            setSelectedRoom(room);
            setSelectedCorridor(null);
          }
        } else if (change.type === 'select' && !change.selected) {
          const roomId = Number(change.id);
          if (selectedRoom?.id === roomId) setSelectedRoom(null);
        }

        if (change.type === 'remove') {
          const roomId = Number(change.id);
          setCurrentRooms((prev) => prev.filter((r) => r.id !== roomId));
          // Remove connected edges
          setRfEdges((prev) =>
            prev.filter((e) => Number(e.source) !== roomId && Number(e.target) !== roomId),
          );
          setIsDirty(true);
          if (selectedRoom?.id === roomId) setSelectedRoom(null);
        }
      }
    },
    [onNodesChange, currentRooms, selectedRoom, setRfEdges],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      onEdgesChange(changes);

      for (const change of changes) {
        if (change.type === 'select' && change.selected) {
          const edge = rfEdges.find((e) => e.id === change.id);
          const corridor = edge ? corridorFromEdge(edge) : null;
          if (corridor) {
            setSelectedCorridor(corridor);
            setSelectedRoom(null);
          }
        } else if (change.type === 'select' && !change.selected) {
          const corridorId = Number(change.id);
          if (selectedCorridor?.id === corridorId) setSelectedCorridor(null);
        }

        if (change.type === 'remove') {
          setIsDirty(true);
          const corridorId = Number(change.id);
          if (selectedCorridor?.id === corridorId) setSelectedCorridor(null);
        }
      }
    },
    [onEdgesChange, rfEdges, selectedCorridor],
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;

      const fromRoomId = Number(connection.source);
      const toRoomId = Number(connection.target);

      // Check for duplicate
      const exists = rfEdges.some(
        (e) => Number(e.source) === fromRoomId && Number(e.target) === toRoomId,
      );
      if (exists) {
        toast.error('Коридор между этими комнатами уже существует');
        return;
      }

      const corridorId = nextTempId();

      const newCorridor: DungeonCorridor = {
        id: corridorId,
        dungeon_id: dungeonId,
        from_room_id: fromRoomId,
        to_room_id: toRoomId,
        stamina_cost: 5,
        is_bidirectional: true,
        random_battle_chance: 0,
        random_battle_mob_ids: null,
        trap_chance: 0,
        trap_config: null,
        description: null,
        source_handle: connection.sourceHandle ?? null,
        target_handle: connection.targetHandle ?? null,
      };

      // Build the edge with the user's chosen handles
      const newEdge: Edge = {
        id: String(corridorId),
        source: connection.source,
        target: connection.target,
        sourceHandle: connection.sourceHandle ?? undefined,
        targetHandle: connection.targetHandle ?? undefined,
        type: 'smoothstep',
        animated: true,
        label: '5 ⚡',
        style: { stroke: '#60a5fa', strokeWidth: 2 },
        labelStyle: { fill: '#d4d4d8', fontSize: 10 },
        labelBgStyle: { fill: '#1e1e2e', fillOpacity: 0.85 },
        data: { corridor: newCorridor },
      };

      // Use React Flow's addEdge to properly add the edge
      setRfEdges((prev) => addEdge(newEdge, prev));
      setIsDirty(true);
    },
    [rfEdges, dungeonId, setRfEdges],
  );

  // --- Drag & Drop from palette ---

  const handleDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const roomType = event.dataTransfer.getData('application/reactflow');
      if (!roomType) return;

      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const snappedX = snapToGrid(position.x);
      const snappedY = snapToGrid(position.y);
      const label = ROOM_TYPE_LABELS[roomType] || roomType;

      const newRoom: DungeonRoom = {
        id: nextTempId(),
        dungeon_id: dungeonId,
        room_type: roomType as DungeonRoom['room_type'],
        name: label,
        description: '',
        image_url: null,
        sort_order: currentRooms.length,
        is_entrance: false,
        is_boss_room: roomType === 'boss',
        is_mana_core_room: false,
        room_config: {},
        position_x: snappedX,
        position_y: snappedY,
      };

      setCurrentRooms((prev) => [...prev, newRoom]);
      setIsDirty(true);
      setSelectedRoom(newRoom);
      setSelectedCorridor(null);
    },
    [screenToFlowPosition, dungeonId, currentRooms.length],
  );

  // --- Property panel callbacks ---

  const handleRoomChange = useCallback((updatedRoom: DungeonRoom) => {
    setCurrentRooms((prev) => prev.map((r) => (r.id === updatedRoom.id ? updatedRoom : r)));
    setDirtyRoomIds((prev) => new Set(prev).add(updatedRoom.id));
    setSelectedRoom(updatedRoom);
    setIsDirty(true);
  }, []);

  const handleCorridorChange = useCallback(
    (updatedCorridor: DungeonCorridor) => {
      // Update the corridor data inside the edge
      setRfEdges((prev) =>
        prev.map((e) => {
          if (e.id === String(updatedCorridor.id)) {
            return {
              ...e,
              label: `${updatedCorridor.stamina_cost} ⚡`,
              style: { stroke: updatedCorridor.is_bidirectional ? '#60a5fa' : '#f59e0b', strokeWidth: 2 },
              data: { ...e.data, corridor: updatedCorridor },
            };
          }
          return e;
        }),
      );
      setSelectedCorridor(updatedCorridor);
      setIsDirty(true);
    },
    [setRfEdges],
  );

  const handleDeleteRoom = useCallback(
    (roomId: number) => {
      setCurrentRooms((prev) => prev.filter((r) => r.id !== roomId));
      setRfEdges((prev) =>
        prev.filter((e) => Number(e.source) !== roomId && Number(e.target) !== roomId),
      );
      setIsDirty(true);
      if (selectedRoom?.id === roomId) setSelectedRoom(null);
    },
    [selectedRoom, setRfEdges],
  );

  const handleDeleteCorridor = useCallback(
    (corridorId: number) => {
      setRfEdges((prev) => prev.filter((e) => e.id !== String(corridorId)));
      setIsDirty(true);
      if (selectedCorridor?.id === corridorId) setSelectedCorridor(null);
    },
    [selectedCorridor, setRfEdges],
  );

  // --- Toolbar callbacks ---

  const handleValidate = useCallback(async () => {
    try {
      const result = await validateDungeon(dungeonId);
      if (result.valid) {
        toast.success('Валидация пройдена успешно');
      } else {
        result.errors.forEach((err) => toast.error(`Ошибка: ${err}`));
        result.warnings.forEach((warn) => toast(warn, { icon: '⚠️' }));
      }
    } catch {
      toast.error('Не удалось выполнить валидацию');
    }
  }, [dungeonId]);

  const handleAutoLayout = useCallback(() => {
    const positions = autoLayoutRooms(currentRooms, currentCorridors);
    setCurrentRooms((prev) =>
      prev.map((room) => {
        const pos = positions.find((p) => p.room_id === room.id);
        if (pos) return { ...room, position_x: pos.position_x, position_y: pos.position_y };
        return room;
      }),
    );
    setIsDirty(true);
    setTimeout(() => fitView({ duration: 300 }), 50);
  }, [currentRooms, currentCorridors, fitView]);

  const handleFitView = useCallback(() => fitView({ duration: 300 }), [fitView]);
  const handleZoomIn = useCallback(() => zoomIn({ duration: 200 }), [zoomIn]);
  const handleZoomOut = useCallback(() => zoomOut({ duration: 200 }), [zoomOut]);

  return (
    <div className="flex flex-col h-[calc(100vh-200px)]">
      <EditorToolbar
        isDirty={isDirty}
        isSaving={isSaving}
        onSave={save}
        onValidate={handleValidate}
        onAutoLayout={handleAutoLayout}
        onFitView={handleFitView}
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
      />

      <div className="flex flex-1 overflow-hidden gap-2 mt-2">
        {/* Left: Room palette */}
        <div className="w-44 shrink-0">
          <RoomPalette />
        </div>

        {/* Center: React Flow canvas */}
        <div className="flex-1 rounded-lg overflow-hidden border border-white/10">
          <ReactFlow
            nodes={rfNodes}
            edges={rfEdges}
            nodeTypes={nodeTypes}
            onNodesChange={handleNodesChange}
            onEdgesChange={handleEdgesChange}
            onConnect={handleConnect}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            snapToGrid={true}
            snapGrid={[GRID_SIZE, GRID_SIZE]}
            connectionMode={ConnectionMode.Loose}
            fitView
            deleteKeyCode="Delete"
            className="bg-[#0d0d1a]"
          >
            <Background gap={GRID_SIZE} color="rgba(255,255,255,0.04)" />
            <Controls
              showInteractive={false}
              className="!bg-[#1e1e2e] !border-white/10 !shadow-lg [&>button]:!bg-[#1e1e2e] [&>button]:!border-white/10 [&>button]:!fill-white/60 [&>button:hover]:!fill-white"
            />
            <MiniMap
              nodeColor={() => '#60a5fa'}
              maskColor="rgba(0,0,0,0.7)"
              className="!bg-[#1e1e2e] !border-white/10"
            />
          </ReactFlow>
        </div>

        {/* Right: Property panel */}
        <div className="w-72 shrink-0">
          <PropertyPanel
            selectedRoom={selectedRoom}
            selectedCorridor={selectedCorridor}
            rooms={currentRooms}
            onRoomChange={handleRoomChange}
            onCorridorChange={handleCorridorChange}
            onDeleteRoom={handleDeleteRoom}
            onDeleteCorridor={handleDeleteCorridor}
          />
        </div>
      </div>
    </div>
  );
};

// --- Outer wrapper with ReactFlowProvider + mobile guard ---

const DungeonVisualEditor = (props: DungeonVisualEditorProps) => {
  return (
    <>
      {/* Mobile message */}
      <div className="lg:hidden flex items-center justify-center py-20">
        <p className="text-white/60 text-center text-sm px-4">
          Редактор доступен только на десктопе.
          <br />
          Пожалуйста, откройте эту страницу на устройстве с шириной экрана от 1024px.
        </p>
      </div>

      {/* Desktop editor */}
      <div className="hidden lg:block">
        <ReactFlowProvider>
          <EditorInner {...props} />
        </ReactFlowProvider>
      </div>
    </>
  );
};

export default DungeonVisualEditor;
