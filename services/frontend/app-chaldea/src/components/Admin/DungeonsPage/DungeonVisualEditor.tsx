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
import { updateDungeon, validateDungeon } from '../../../api/dungeons';
import { DUNGEON_THEMES, THEME_INFO, floorTheme, isTheme, type DungeonTheme } from '../../DungeonBoard3D/dungeonThemes';
import type { RoomNodeData, RoomFlowNode } from './editor/types';
import { ROOM_TYPE_LABELS } from './editor/constants';
import { ROOM_CELL_PX, editorToBoard } from '../../DungeonBoard3D/editorToBoard';
import { buildDioramaLayout } from '../../DungeonBoard3D/dioramaLayout';
import DungeonPreview3D from '../../DungeonBoard3D/DungeonPreview3D';
import RoomNode from './editor/RoomNode';
import RoomPalette from './editor/RoomPalette';
import PropertyPanel from './editor/PropertyPanel';
import EditorToolbar from './editor/EditorToolbar';
import { autoLayoutRooms } from './editor/autoLayout';
import useEditorSave from './editor/useEditorSave';

interface DungeonVisualEditorProps {
  dungeonId: number;
  /** Shown over the 3D preview. */
  dungeonName?: string;
  rooms: DungeonRoom[];
  corridors: DungeonCorridor[];
  onUpdate: () => void;
  /** The dungeon's look and each floor's own (FEAT-176). */
  theme?: string;
  floorThemes?: Record<string, string> | null;
}

const nodeTypes = { room: RoomNode };

/** One grid cell is one room slot on the 3D miniature (see editorToBoard). */
const snapToGrid = (value: number): number => Math.round(value / ROOM_CELL_PX) * ROOM_CELL_PX;

// --- Conversion helpers ---

const floorOf = (room: DungeonRoom | undefined) => room?.floor ?? 1;

const roomToNode = (
  room: DungeonRoom,
  serverRoomIds: Set<number>,
  dirtyRoomIds: Set<number>,
  onSelect: (room: DungeonRoom) => void,
  floor: number,
): RoomFlowNode => ({
  id: String(room.id),
  type: 'room',
  // One floor at a time: the others wait on their own tabs.
  hidden: floorOf(room) !== floor,
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

const EditorInner = ({
  dungeonId,
  dungeonName = 'Подземелье',
  rooms: serverRooms,
  corridors: serverCorridors,
  onUpdate,
  theme,
  floorThemes: savedFloorThemes,
}: DungeonVisualEditorProps) => {
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
  // The floor being edited, and floors added but still empty.
  const [floor, setFloor] = useState(1);
  // Each floor's own look, saved as soon as it is picked (the rest of the editor saves with its button).
  const [floorThemes, setFloorThemes] = useState<Record<string, string>>(savedFloorThemes ?? {});
  const [themeSaving, setThemeSaving] = useState(false);
  const pickFloorTheme = async (value: string) => {
    const next = { ...floorThemes };
    if (value) next[String(floor)] = value;
    else delete next[String(floor)];
    setThemeSaving(true);
    try {
      await updateDungeon(dungeonId, { floor_themes: next });
      setFloorThemes(next);
      toast.success(value ? `Оформление этажа ${floor}: ${THEME_INFO[value as DungeonTheme].name}` : `Этаж ${floor} — как у подземелья`);
    } catch {
      toast.error('Не удалось сохранить оформление этажа');
    } finally {
      setThemeSaving(false);
    }
  };
  const dungeonTheme = isTheme(theme) ? theme : 'stone';
  const [addedFloors, setAddedFloors] = useState(1);
  const floorsCount = Math.max(addedFloors, ...currentRooms.map((r) => floorOf(r)));

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

    // Rooms placed before the editor had room slots move to the nearest slot; saving keeps it.
    let snappedAny = false;
    layoutRooms = layoutRooms.map((room) => {
      const x = snapToGrid(room.position_x ?? 0);
      const y = snapToGrid(room.position_y ?? 0);
      if (x === room.position_x && y === room.position_y) return room;
      snappedAny = true;
      return { ...room, position_x: x, position_y: y };
    });

    setCurrentRooms(layoutRooms);
    setDirtyRoomIds(new Set());
    setIsDirty(needsLayout || snappedAny);
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
    () => currentRooms.map((r) => roomToNode(r, serverRoomIds, dirtyRoomIds, onSelectRoom, floor)),
    [currentRooms, serverRoomIds, dirtyRoomIds, onSelectRoom, floor],
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
        lock_config: null,
        passage_type: 'corridor',
        passage_config: null,
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
        floor,
      };

      setCurrentRooms((prev) => [...prev, newRoom]);
      setIsDirty(true);
      setSelectedRoom(newRoom);
      setSelectedCorridor(null);
    },
    [screenToFlowPosition, dungeonId, currentRooms.length, floor],
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

  /** Stairs, a drop or a lift to a room of another floor: a corridor the canvas never draws. */
  const handleAddCorridor = useCallback(
    (corridor: Omit<DungeonCorridor, 'id'>) => {
      setRfEdges((prev) => [...prev, corridorToEdge({ ...corridor, id: nextTempId() })]);
      setIsDirty(true);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [setRfEdges],
  );

  // Only this floor's corridors are drawn; passages between floors live in the room panel.
  const roomFloors = useMemo(() => new Map(currentRooms.map((r) => [r.id, floorOf(r)])), [currentRooms]);
  const shownEdges = useMemo(
    () =>
      rfEdges.map((e) => {
        const c = corridorFromEdge(e);
        const hidden =
          (c?.passage_type ?? 'corridor') !== 'corridor' ||
          roomFloors.get(Number(e.source)) !== floor ||
          roomFloors.get(Number(e.target)) !== floor;
        return e.hidden === hidden ? e : { ...e, hidden };
      }),
    [rfEdges, roomFloors, floor],
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

  // How the miniature would be built from the editor as it stands, saved or not.
  const board = useMemo(
    () =>
      editorToBoard(
        dungeonName,
        currentRooms.filter((r) => floorOf(r) === floor),
        currentCorridors.filter(
          (c) =>
            (c.passage_type ?? 'corridor') === 'corridor' &&
            roomFloors.get(c.from_room_id) === floor &&
            roomFloors.get(c.to_room_id) === floor,
        ),
        floorTheme(dungeonTheme, floorThemes, floor),
      ),
    [dungeonName, currentRooms, currentCorridors, floor, roomFloors, dungeonTheme, floorThemes],
  );
  const [previewOpen, setPreviewOpen] = useState(false);

  const handleValidate = useCallback(async () => {
    // The miniature's own checks need no server: rooms overlapping, corridors cutting through rooms.
    const layoutWarnings = buildDioramaLayout(board).warnings;
    layoutWarnings.forEach((warn) => toast(warn, { icon: '🧱', duration: 7000 }));
    try {
      const result = await validateDungeon(dungeonId);
      if (result.valid && layoutWarnings.length === 0) {
        toast.success('Валидация пройдена успешно');
      } else {
        result.errors.forEach((err) => toast.error(`Ошибка: ${err}`));
        result.warnings.forEach((warn) => toast(warn, { icon: '⚠️' }));
      }
    } catch {
      toast.error('Не удалось выполнить валидацию');
    }
  }, [dungeonId, board]);

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
        onPreview3D={() => setPreviewOpen(true)}
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

        {/* Center: floor tabs over the React Flow canvas */}
        <div className="flex-1 flex flex-col min-w-0 gap-2">
        <div className="flex items-center gap-1.5 flex-wrap">
          {Array.from({ length: floorsCount }, (_, i) => i + 1).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => {
                setFloor(f);
                setSelectedRoom(null);
                setSelectedCorridor(null);
                setTimeout(() => fitView({ duration: 300 }), 50);
              }}
              className={`text-xs px-3 py-1.5 rounded-card border transition-colors ${
                f === floor ? 'border-gold/60 text-gold bg-gold/10' : 'border-white/15 text-white/60 hover:text-white'
              }`}
            >
              Этаж {f}
              <span className="text-white/30 ml-1">({currentRooms.filter((r) => floorOf(r) === f).length})</span>
            </button>
          ))}
          <button
            type="button"
            onClick={() => {
              setAddedFloors(floorsCount + 1);
              setFloor(floorsCount + 1);
              setSelectedRoom(null);
              setSelectedCorridor(null);
            }}
            className="text-xs px-3 py-1.5 rounded-card border border-dashed border-white/20 text-white/50 hover:text-white transition-colors"
          >
            + Этаж
          </button>
          <label className="ml-auto flex items-center gap-2 text-xs text-white/50">
            Оформление этажа {floor}:
            <select
              value={floorThemes[String(floor)] ?? ''}
              disabled={themeSaving}
              onChange={(e) => void pickFloorTheme(e.target.value)}
              className="bg-transparent border-b border-white/20 text-white py-1 outline-none disabled:opacity-50"
            >
              <option value="" className="bg-site-bg">
                Как у подземелья ({THEME_INFO[dungeonTheme].name})
              </option>
              {DUNGEON_THEMES.map((t) => (
                <option key={t} value={t} className="bg-site-bg">
                  {THEME_INFO[t].name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex-1 rounded-lg overflow-hidden border border-white/10">
          <ReactFlow
            nodes={rfNodes}
            edges={shownEdges}
            nodeTypes={nodeTypes}
            onNodesChange={handleNodesChange}
            onEdgesChange={handleEdgesChange}
            onConnect={handleConnect}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            snapToGrid={true}
            snapGrid={[ROOM_CELL_PX, ROOM_CELL_PX]}
            connectionMode={ConnectionMode.Loose}
            fitView
            deleteKeyCode="Delete"
            className="bg-[#0d0d1a]"
          >
            <Background gap={ROOM_CELL_PX} size={2} color="rgba(255,255,255,0.12)" />
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
        </div>

        {/* Right: Property panel */}
        <div className="w-72 shrink-0">
          <PropertyPanel
            selectedRoom={selectedRoom}
            selectedCorridor={selectedCorridor}
            rooms={currentRooms}
            corridors={currentCorridors}
            floorsCount={floorsCount}
            onAddCorridor={handleAddCorridor}
            onRoomChange={handleRoomChange}
            onCorridorChange={handleCorridorChange}
            onDeleteRoom={handleDeleteRoom}
            onDeleteCorridor={handleDeleteCorridor}
          />
        </div>
      </div>

      {previewOpen && <DungeonPreview3D dungeon={board} onClose={() => setPreviewOpen(false)} />}
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
