import { useRef, type MutableRefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';
import { createSoftSpotTexture } from '../../pages/BattlePage/Arena3D/textures';
import { noRaycast, useDisposable, type BookFrame, type BookProgress } from './bookParts';
import { pageBow } from './pageBlock';
import type { SpreadModel, SpreadNode } from './spreadLayout';

/*
  What lies over the inked tree: a slow pulse on the nodes that can be taken
  now, and a label on whichever node the pointer rests on. The path walked is
  left to its gold ink — no halo over it. Only shown while the book lies fully
  open.
*/

/** Labels are DOM laid over the canvas; kept under the page's own overlays (header z-10, panel z-20). */
const HTML_Z_RANGE: [number, number] = [9, 0];

/* DB class ids: 1=Warrior, 2=Rogue, 3=Mage */
const CLASS_GLOW: Record<number, string> = {
  1: '#ff7a5c',
  2: '#4fe0a0',
  3: '#6aa8ff',
};
const GOLD_GLOW = '#ffd47a';

const STATE_TEXT: Record<SpreadNode['state'], string> = {
  chosen: 'Изучено',
  available: 'Можно изучить',
  locked: '',
  blocked: 'Выбрана другая ветка',
  unreachable: 'Путь сюда перекрыт',
};

/** Where a node lies on the open book, in the book's own frame. */
export const nodeWorldPosition = (n: SpreadNode, frame: BookFrame): [number, number, number] => [
  n.u * frame.pageWidth,
  frame.hingeY + pageBow(Math.abs(n.u)) + 0.03,
  frame.pageDepth / 2 - n.v * frame.pageDepth,
];

interface SpreadOverlayProps {
  spread: SpreadModel;
  frame: BookFrame;
  progress: MutableRefObject<BookProgress>;
  hoveredId: number | null;
}

const SpreadOverlay = ({ spread, frame, progress, hoveredId }: SpreadOverlayProps) => {
  const glow = useDisposable(createSoftSpotTexture, []);
  const group = useRef<THREE.Group>(null);
  const pulses = useRef<(THREE.SpriteMaterial | null)[]>([]);
  const classGlow = CLASS_GLOW[spread.classId] ?? GOLD_GLOW;
  const lit = spread.foreign ? [] : spread.nodes.filter((n) => n.state === 'available');
  const hovered = hoveredId === null ? null : spread.nodes.find((n) => n.id === hoveredId) ?? null;

  useFrame(({ clock }) => {
    if (group.current) group.current.visible = progress.current.cover > 0.97;
    const t = clock.elapsedTime;
    pulses.current.forEach((m, i) => {
      if (m) m.opacity = 0.25 + 0.3 * (0.5 + 0.5 * Math.sin(t * 2.2 + i * 0.9));
    });
  });

  const stateText = (n: SpreadNode) =>
    spread.foreign ? 'Книга другого класса' : n.state === 'locked' ? `Требуется уровень ${n.node.level_ring}` : STATE_TEXT[n.state];

  return (
    <group ref={group} visible={false}>
      {lit.map((n, i) => {
        const size = n.large ? 0.75 : 0.55;
        return (
          <sprite raycast={noRaycast} key={n.id} position={nodeWorldPosition(n, frame)} scale={[size, size, 1]}>
            <spriteMaterial
              ref={(m) => {
                pulses.current[i] = m;
              }}
              map={glow}
              color={classGlow}
              opacity={0.3}
              transparent
              depthWrite={false}
              blending={THREE.AdditiveBlending}
              toneMapped={false}
            />
          </sprite>
        );
      })}

      {hovered && (
        <group position={nodeWorldPosition(hovered, frame)}>
          <Html position={[0, 0.35, 0]} center zIndexRange={HTML_Z_RANGE} style={{ pointerEvents: 'none' }}>
            <div className="whitespace-nowrap rounded-lg bg-black/75 backdrop-blur-sm px-3 py-1.5 text-center shadow-card">
              <div className="gold-text text-xs font-medium uppercase">{hovered.node.name}</div>
              <div className="text-[10px] text-white/55">
                {stateText(hovered)}
                {(hovered.node.skills?.length ?? 0) > 0 && <span> &middot; навыков: {hovered.node.skills.length}</span>}
              </div>
            </div>
          </Html>
        </group>
      )}
    </group>
  );
};

export default SpreadOverlay;
