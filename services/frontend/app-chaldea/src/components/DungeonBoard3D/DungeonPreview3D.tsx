import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'react-feather';
import { useClientPrefs } from '../../utils/clientPrefs';
import { isWebGLAvailable } from '../pages/BattlePage/Arena3D/webgl';
import { buildDioramaLayout } from './dioramaLayout';
import type { BoardDungeon } from './boardTypes';

const DungeonBoardScene = lazy(() => import('./DungeonBoardScene'));

const ZOOM_MIN = 0.6;
const ZOOM_MAX = 9;
const NO_ROOMS = new Set<number>();

/**
 * The admin's look at a dungeon as the 3D miniature: every room built, seen
 * from above, straight from the editor as it stands (saved or not), with the
 * miniature's own warnings — rooms overlapping, corridors through rooms.
 */
const DungeonPreview3D = ({ dungeon, onClose }: { dungeon: BoardDungeon; onClose: () => void }) => {
  const { graphics } = useClientPrefs();
  const webgl = useMemo(() => isWebGLAvailable(), []);
  const layout = useMemo(() => buildDioramaLayout(dungeon), [dungeon]);
  const allRooms = useMemo(() => new Set(dungeon.rooms.map((r) => r.id)), [dungeon]);
  // Far enough back to take in the whole dungeon at once.
  const fitZoom = Math.min(ZOOM_MAX, Math.max(1, layout.width * 0.17, layout.depth * 0.26));
  const [zoom, setZoom] = useState(fitZoom);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    const root = document.documentElement;
    const previous = root.style.overflow;
    root.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      root.style.overflow = previous;
    };
  }, [onClose]);

  // Portaled to <body> so it covers the site header too.
  return createPortal(
    <div
      className="fixed inset-0 z-[70] bg-black"
      role="dialog"
      aria-label="3D-вид подземелья"
      onWheel={(e) => setZoom((z) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z * (e.deltaY > 0 ? 1.12 : 1 / 1.12))))}
    >
      {dungeon.rooms.length === 0 ? (
        <div className="flex h-full items-center justify-center text-white/60 text-sm">В подземелье пока нет комнат.</div>
      ) : webgl ? (
        <Suspense
          fallback={
            <div className="flex h-full items-center justify-center">
              <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
            </div>
          }
        >
          <DungeonBoardScene
            dungeon={dungeon}
            party={[]}
            currentRoomId={dungeon.entranceId}
            revealed={allRooms}
            cleared={NO_ROOMS}
            reachable={NO_ROOMS}
            dice={null}
            lowGraphics={graphics === 'low'}
            zoom={zoom}
            overview
            onTileClick={() => {}}
          />
        </Suspense>
      ) : (
        <div className="flex h-full items-center justify-center p-6 text-center text-white/60 text-sm">
          Устройство не поддерживает 3D (нет WebGL).
        </div>
      )}

      <div className="absolute top-4 left-4 right-16 flex flex-col gap-2 pointer-events-none">
        <div className="bg-black/70 backdrop-blur-sm rounded-card px-4 py-3 w-fit max-w-full">
          <p className="gold-text text-lg uppercase">{dungeon.name}</p>
          <p className="text-white/60 text-xs">
            Так подземелье выглядит на столе, когда все комнаты открыты. Колёсико мыши — приблизить и отдалить, Esc — закрыть.
          </p>
        </div>
        {layout.warnings.length > 0 && (
          <div className="bg-black/75 backdrop-blur-sm rounded-card px-4 py-3 max-w-xl">
            <p className="text-site-red text-sm mb-1">Что поправить на схеме:</p>
            <ul className="text-white/80 text-xs flex flex-col gap-1 list-disc pl-4">
              {layout.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <button
        type="button"
        onClick={onClose}
        className="absolute top-4 right-4 w-10 h-10 flex items-center justify-center rounded-full bg-black/60 text-white/70 hover:text-white transition-colors duration-200 ease-site"
        aria-label="Закрыть 3D-вид"
      >
        <X size={20} />
      </button>
    </div>,
    document.body,
  );
};

export default DungeonPreview3D;
