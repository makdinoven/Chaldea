import { useState } from 'react';
import type { ChallengeStep, SearchParams } from '../../../api/dungeons';
import { playDungeonSound } from '../../../utils/dungeonSounds';
import { CraftStage } from './three/craftKit';
import SearchScene, { SEARCH_CAMERA } from './three/SearchScene';

/*
  Searching a room in 3D (graphics to spare; SearchGame otherwise): lift the
  floor slabs and follow the traces under them to a stash, if there is one.
  Where it lies only the server knows.
*/

interface Search3DGameProps {
  params: SearchParams;
  offClass: boolean;
  onStep: (move: { x: number; y: number }) => Promise<ChallengeStep | null>;
}

const Search3DGame = ({ params, offClass, onStep }: Search3DGameProps) => {
  const [looks, setLooks] = useState<Map<string, number | null>>(new Map());
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const left = params.probes - looks.size;

  const look = async (x: number, y: number) => {
    const key = `${x},${y}`;
    if (busy || over || looks.has(key) || left <= 0) return;
    setBusy(true);
    const step = await onStep({ x, y });
    setBusy(false);
    if (!step) return;
    const found = step.way == null;
    playDungeonSound(found ? 'chest' : 'step');
    setLooks((prev) => new Map(prev).set(key, found ? null : (step.way as number)));
    if (step.result) setOver(true);
  };

  return (
    <div className="flex flex-col items-center gap-3 select-none">
      <p className="text-white/70 text-sm text-center max-w-md">
        Поднимайте плиты пола. Под каждой — следы, которые указывают, куда тянуть дальше. Если в комнате есть тайник,
        следы чаще всего ведут к нему.
      </p>
      {offClass && (
        <p className="text-site-red/90 text-xs text-center max-w-md">
          Обыск — ремесло плута. Попыток у вас меньше, а следы чаще путают.
        </p>
      )}
      <CraftStage
        camera={SEARCH_CAMERA}
        hud={
          <span className="absolute left-3 top-3 text-white/70 text-xs">
            Попыток: <span className="text-white tabular-nums">{left}</span>
          </span>
        }
      >
        <SearchScene params={params} looks={looks} over={over || left <= 0} onLook={(x, y) => void look(x, y)} />
      </CraftStage>
    </div>
  );
};

export default Search3DGame;
