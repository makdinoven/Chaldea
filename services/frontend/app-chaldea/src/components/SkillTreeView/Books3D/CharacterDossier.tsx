import { useEffect, useMemo, useState } from 'react';
import type { ThreeEvent } from '@react-three/fiber';
import * as THREE from 'three';
import type { PassportData } from '../../CommonComponents/CharacterPassport/types';
import { usableImageSrc } from '../../CommonComponents/CharacterPassport/passportText';
import { toSameOriginMedia } from '../../pages/BattlePage/Arena3D/sameOriginMedia';
import { useDisposable } from './bookParts';
import {
  DOSSIER_PX,
  DOSSIER_SEAL_AT,
  createDossierTexture,
  createSealFaceTexture,
  loadDossierFonts,
} from './dossierTexture';

/*
  The player's passport, a sheet of paper on the table beside their own book —
  half under it, as papers are that a book was set down on. Opening the book
  lays its front board over it. Touched while the book is shut, it is taken up
  to be read (the camera leans in over it; see BookTableScene).
*/

/** Size of the sheet on the table, world units: the passport's proportions. */
export const DOSSIER_SIZE = { width: 1.55, depth: (1.55 * DOSSIER_PX.h) / DOSSIER_PX.w } as const;
/** How high the sheet's far corner lifts where it won't lie flat. */
const CURL = 0.03;
const SEAL = { radius: 0.11, height: 0.025 } as const;

/**
 * The portrait, from a same-origin address so it can be drawn into the sheet:
 * the avatar if there is a usable one, else the subrace's picture, else none.
 */
const loadPortrait = async (data: PassportData): Promise<HTMLImageElement | null> => {
  for (const raw of [data.avatarUrl, data.subraceImage]) {
    const src = usableImageSrc(raw);
    // Only the bucket is mirrored same-origin; a site-relative path already is.
    const sameOrigin = src?.startsWith('/') && !src.startsWith('//') ? src : toSameOriginMedia(src);
    if (!sameOrigin) continue;
    try {
      const img = new Image();
      img.src = sameOrigin;
      await img.decode();
      return img;
    } catch {
      // Try the next picture.
    }
  }
  return null;
};

interface CharacterDossierProps {
  data: PassportData;
  currentGameYear: number | null;
  position: [number, number, number];
  yaw: number;
  /** Touched: take it up to read, or put it back down. */
  onToggle: () => void;
}

const CharacterDossier = ({ data, currentGameYear, position, yaw, onToggle }: CharacterDossierProps) => {
  const [texture, setTexture] = useState<THREE.Texture | null>(null);
  useEffect(() => {
    let cancelled = false;
    let made: THREE.Texture | null = null;
    Promise.all([loadPortrait(data), loadDossierFonts()]).then(([picture]) => {
      if (cancelled) return;
      made = createDossierTexture(data, currentGameYear, picture);
      setTexture(made);
    });
    return () => {
      cancelled = true;
      made?.dispose();
    };
  }, [data, currentGameYear]);

  const sheet = useDisposable(() => {
    const { width, depth } = DOSSIER_SIZE;
    const g = new THREE.PlaneGeometry(width, depth, 12, 16);
    g.rotateX(-Math.PI / 2);
    const pos = g.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      // The far left corner lifts a little; the rest lies just off the table.
      const u = 1 - (pos.getX(i) / width + 0.5);
      const v = 1 - (pos.getZ(i) / depth + 0.5);
      const lift = Math.max(0, (u - 0.7) / 0.3) * Math.max(0, (v - 0.75) / 0.25);
      pos.setY(i, 0.004 + lift * lift * CURL);
    }
    g.computeVertexNormals();
    return g;
  }, []);
  const sealFace = useDisposable(createSealFaceTexture, []);
  const seal = useDisposable(() => {
    // A blob of wax, not a coin: its rim pushed out unevenly.
    const g = new THREE.CylinderGeometry(SEAL.radius, SEAL.radius * 1.08, SEAL.height, 28, 1);
    const pos = g.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const z = pos.getZ(i);
      const a = Math.atan2(z, x);
      const k = 1 + Math.sin(a * 5) * 0.05 + Math.sin(a * 3 + 1) * 0.04;
      pos.setX(i, x * k);
      pos.setZ(i, z * k);
    }
    g.computeVertexNormals();
    return g;
  }, []);
  const sealMaterials = useMemo(
    () => [
      new THREE.MeshStandardMaterial({ color: '#6e1212', roughness: 0.45 }),
      new THREE.MeshStandardMaterial({ map: sealFace, roughness: 0.4 }),
      new THREE.MeshStandardMaterial({ color: '#6e1212', roughness: 0.45 }),
    ],
    [sealFace],
  );
  useEffect(() => () => sealMaterials.forEach((m) => m.dispose()), [sealMaterials]);

  if (!texture) return null;
  const sealX = (DOSSIER_SEAL_AT.x / DOSSIER_PX.w - 0.5) * DOSSIER_SIZE.width;
  const sealZ = (DOSSIER_SEAL_AT.y / DOSSIER_PX.h - 0.5) * DOSSIER_SIZE.depth;

  return (
    <group
      position={position}
      rotation={[0, yaw, 0]}
      onClick={(e: ThreeEvent<MouseEvent>) => {
        e.stopPropagation();
        if (e.delta <= 8) onToggle();
      }}
      onPointerOver={(e: ThreeEvent<PointerEvent>) => {
        e.stopPropagation();
        document.body.style.cursor = 'pointer';
      }}
      onPointerOut={() => {
        document.body.style.cursor = '';
      }}
    >
      <mesh geometry={sheet} receiveShadow>
        {/* Toned down: under the candles a white sheet outshone the open pages. */}
        <meshStandardMaterial map={texture} color="#ddd3c0" roughness={0.9} side={THREE.DoubleSide} />
      </mesh>
      <mesh geometry={seal} material={sealMaterials} position={[sealX, 0.004 + SEAL.height / 2, sealZ]} rotation={[0, 0.4, 0]} castShadow />
    </group>
  );
};

export default CharacterDossier;
