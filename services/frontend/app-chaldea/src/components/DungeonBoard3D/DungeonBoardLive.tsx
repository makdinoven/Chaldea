import { lazy, Suspense, useMemo, useState, type ReactNode, type WheelEvent, type CSSProperties } from 'react';
import { buildDioramaLayout } from './dioramaLayout';
import ErrorBoundary from '../ui/ErrorBoundary';
import { setClientPrefs } from '../../utils/clientPrefs';
import type { BoardDungeon, BoardMember } from './boardTypes';
import type { CorridorScene, DiceThrow, FloorSpan } from './DungeonBoardScene';
import type { BoardMark } from './PartyMarks';
import type { DungeonStability } from './DungeonDoors';

const DungeonBoardScene = lazy(() => import('./DungeonBoardScene'));

/** The table failed to load or draw: the 2D map always works. */
const SceneFailed = () => (
  <div className="flex h-full flex-col items-center justify-center gap-4 p-6 text-center">
    <p className="text-white/70 text-sm">Не удалось показать 3D-стол на этом устройстве.</p>
    <button type="button" className="btn-blue text-sm px-6 py-2" onClick={() => setClientPrefs({ dungeonView: '2d' })}>
      Открыть 2D-карту
    </button>
  </div>
);

const ZOOM_MIN = 0.6;
const ZOOM_MAX = 9;
const ZOOM_STEP = 1.12;
const BUTTON_ZOOM_STEP = 1.3;

interface DungeonBoardLiveProps {
  dungeon: BoardDungeon;
  party: BoardMember[];
  currentRoomId: number;
  revealed: Set<number>;
  cleared: Set<number>;
  reachable: Set<number>;
  dice: DiceThrow | null;
  /** The party halfway down a corridor (an ambush, a trap). */
  corridor?: CorridorScene | null;
  /** The whole floor's span: the rock is laid under all of it. */
  span?: FloorSpan | null;
  lowGraphics: boolean;
  stability?: DungeonStability;
  /** The floor shown on the table. */
  floor?: number;
  onPartyArrived?: (roomId: number) => void;
  onRoomHover?: (hover: { roomId: number; x: number; y: number } | null) => void;
  onTileClick: (roomId: number) => void;
  /** Where the zoom buttons and the party's colours sit over the board. */
  controlsClassName?: string;
  /** Inline position for the controls (e.g. kept above a phone's bottom sheet). */
  controlsStyle?: CSSProperties;
  /** The party's flags and marks on the board. */
  marks?: BoardMark[];
  /** More buttons beside the zoom ones (the party's marks). */
  extraControls?: ReactNode;
}

const clampZoom = (z: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));

/**
 * The live run on the table of fates: the scene (loaded on demand) filling its
 * box, with wheel and button zoom and a look at everything found so far.
 */
const DungeonBoardLive = ({
  dungeon,
  party,
  currentRoomId,
  revealed,
  cleared,
  reachable,
  dice,
  corridor,
  span,
  lowGraphics,
  stability,
  floor,
  onPartyArrived,
  onRoomHover,
  onTileClick,
  controlsClassName = '',
  controlsStyle,
  marks,
  extraControls,
}: DungeonBoardLiveProps) => {
  const [zoom, setZoom] = useState(1);
  const [overview, setOverview] = useState(false);
  const layout = useMemo(() => buildDioramaLayout(dungeon, { fixedOrigin: true }), [dungeon]);
  // Far enough back to take in everything found so far.
  const overviewZoom = clampZoom(Math.max(1.5, layout.width * 0.17, layout.depth * 0.26));

  const handleWheel = (e: WheelEvent) => setZoom((z) => clampZoom(z * (e.deltaY > 0 ? ZOOM_STEP : 1 / ZOOM_STEP)));

  const showAll = () => {
    setOverview(true);
    setZoom(overviewZoom);
  };
  const backToParty = () => {
    setOverview(false);
    setZoom(1);
  };
  const handleTileClick = (roomId: number) => {
    // Setting off from the whole-map view: the camera goes back to follow the party.
    if (overview && reachable.has(roomId)) backToParty();
    onTileClick(roomId);
  };

  return (
    <>
      <div className="absolute inset-0" onWheel={handleWheel}>
        <ErrorBoundary fallback={<SceneFailed />}>
        <Suspense
          fallback={
            <div className="flex h-full items-center justify-center">
              <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
            </div>
          }
        >
          <DungeonBoardScene
            dungeon={dungeon}
            party={party}
            currentRoomId={currentRoomId}
            revealed={revealed}
            cleared={cleared}
            reachable={reachable}
            dice={dice}
            corridor={corridor}
            span={span}
            lowGraphics={lowGraphics}
            stability={stability}
            floor={floor}
            onPartyArrived={onPartyArrived}
            onRoomHover={onRoomHover}
            zoom={zoom}
            overview={overview}
            fixedOrigin
            marks={marks}
            onTileClick={handleTileClick}
          />
        </Suspense>
        </ErrorBoundary>
      </div>

      <div className={`flex flex-col gap-2 ${controlsClassName}`} style={controlsStyle}>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setZoom((z) => clampZoom(z / BUTTON_ZOOM_STEP))}
            className="w-9 h-9 flex items-center justify-center rounded-full bg-black/60 backdrop-blur-sm text-white/80 hover:text-site-blue transition-colors duration-200 ease-site text-lg"
            aria-label="Приблизить"
          >
            +
          </button>
          <button
            type="button"
            onClick={() => setZoom((z) => clampZoom(z * BUTTON_ZOOM_STEP))}
            className="w-9 h-9 flex items-center justify-center rounded-full bg-black/60 backdrop-blur-sm text-white/80 hover:text-site-blue transition-colors duration-200 ease-site text-lg"
            aria-label="Отдалить"
          >
            −
          </button>
          <button
            type="button"
            onClick={overview ? backToParty : showAll}
            className="h-9 px-3 rounded-full bg-black/60 backdrop-blur-sm text-xs text-white/80 hover:text-site-blue transition-colors duration-200 ease-site whitespace-nowrap"
          >
            {overview ? 'К группе' : 'Вся карта'}
          </button>
        </div>
        {extraControls}
      </div>
    </>
  );
};

export default DungeonBoardLive;
