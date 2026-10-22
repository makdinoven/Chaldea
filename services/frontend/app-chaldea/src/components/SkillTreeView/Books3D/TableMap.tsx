import { useEffect, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import * as THREE from 'three';
import { toSameOriginMedia } from '../../pages/BattlePage/Arena3D/sameOriginMedia';
import { noRaycast, useDisposable } from './bookParts';
import { createMapBackTexture, createWorldMapTexture, type MapMarks } from './worldMap';

/*
  The chart unrolled along the table under all the books — the world's own map,
  the one on the world page — its long ends still rolled up, its near and far
  edges lifting a little where the sheet won't lie flat.
*/

/** Depth of the sheet, from the far edge to the near, world units. */
export const MAP_DEPTH = 10;
const ROLL_RADIUS = 0.22;
/** How high the near and far edges lift, and over what share of the half-depth. */
const CURL = { height: 0.1, from: 0.86 } as const;
/** Darkens the parchment under candlelight, so the pages stay the brightest thing on the table. */
const TINT = '#b39d7e';

/**
 * The world's map, as the world page shows it: the first area's picture,
 * fetched through the same-origin mirror so it can be drawn into a texture.
 * Null until it arrives, and for good if there is none to show.
 */
const useWorldMapPicture = () => {
  const [picture, setPicture] = useState<HTMLImageElement | null>(null);
  useEffect(() => {
    let cancelled = false;
    axios
      .get<{ map_image_url: string | null }[]>('/locations/areas/list')
      .then(async (res) => {
        const src = toSameOriginMedia(res.data[0]?.map_image_url);
        if (!src) return;
        const img = new Image();
        img.src = src;
        await img.decode();
        if (!cancelled) setPicture(img);
      })
      .catch(() => {
        if (!cancelled) toast.error('Не удалось загрузить карту мира для стола');
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return picture;
};

interface TableMapProps {
  width: number;
  /** Where its centre lies along the table's depth. */
  centerZ: number;
  /** What stands on it, in map coordinates; keep it stable, the sheet is redrawn when it changes. */
  marks: MapMarks;
}

const TableMap = ({ width, centerZ, marks }: TableMapProps) => {
  const picture = useWorldMapPicture();
  const texture = useDisposable(() => createWorldMapTexture(width, MAP_DEPTH, marks, picture), [width, marks, picture]);
  const back = useDisposable(createMapBackTexture, []);
  const geometry = useDisposable(() => {
    const g = new THREE.PlaneGeometry(width, MAP_DEPTH, 1, 30);
    g.rotateX(-Math.PI / 2);
    const pos = g.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const n = Math.abs(pos.getZ(i)) / (MAP_DEPTH / 2);
      if (n > CURL.from) pos.setY(i, ((n - CURL.from) / (1 - CURL.from)) ** 2 * CURL.height);
    }
    g.computeVertexNormals();
    return g;
  }, [width]);

  return (
    <group position={[0, 0, centerZ]}>
      <mesh geometry={geometry} raycast={noRaycast}>
        <meshStandardMaterial map={texture} color={TINT} roughness={0.92} metalness={0} />
      </mesh>
      {[-1, 1].map((side) => (
        <mesh
          key={side}
          raycast={noRaycast}
          position={[side * (width / 2 + ROLL_RADIUS * 0.6), ROLL_RADIUS, 0]}
          rotation={[Math.PI / 2, 0, 0]}
        >
          <cylinderGeometry args={[ROLL_RADIUS, ROLL_RADIUS, MAP_DEPTH * 0.98, 24]} />
          <meshStandardMaterial map={back} color={TINT} roughness={0.9} />
        </mesh>
      ))}
    </group>
  );
};

export default TableMap;
