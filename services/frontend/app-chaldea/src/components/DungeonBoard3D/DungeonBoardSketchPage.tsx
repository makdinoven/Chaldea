import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useClientPrefs } from '../../utils/clientPrefs';
import { isWebGLAvailable } from '../pages/BattlePage/Arena3D/webgl';
import { SKETCH_DUNGEON, SKETCH_PARTY, type BoardRoomType } from './boardTypes';
import { DUNGEON_THEMES, THEME_INFO, type DungeonTheme } from './dungeonThemes';
import type { DiceThrow } from './DungeonBoardScene';
import ChallengeModal from '../DungeonPage/minigames/ChallengeModal';
import {
  makeSketchChallenge,
  settleSketch,
  stepSketch,
  type SketchSecret,
} from '../DungeonPage/minigames/sketchChallenges';
import type { ChallengeKind, ChallengeStart } from '../../api/dungeons';

/** The class challenges to try here, offline. */
const SKETCH_CHALLENGES: { kind: ChallengeKind; label: string }[] = [
  { kind: 'lockpick', label: 'Замок' },
  { kind: 'mechanism', label: 'Механизм' },
  { kind: 'illusion', label: 'Иллюзия' },
  { kind: 'rubble', label: 'Завал' },
  { kind: 'shield', label: 'Щит' },
  { kind: 'gate', label: 'Решётка' },
  { kind: 'seal', label: 'Печать' },
  { kind: 'search', label: 'Обыск' },
];

const DungeonBoardScene = lazy(() => import('./DungeonBoardScene'));

/*
  A sketch of «Данжи 2.0» on made-up data, to judge the look before the real
  dungeon is moved onto the table. Nothing here talks to the server.
*/

const ROOM_HINT: Record<BoardRoomType, string> = {
  entrance: 'Отсюда группа спускается в подземелье.',
  battle: 'Здесь начнётся бой — в настоящем данже стол перейдёт в арену.',
  boss: 'Хозяин подземелья. После победы — сундук и зачистка.',
  treasure: 'Сундук с добычей ляжет в общий инвентарь группы.',
  trap: 'Ловушка: проверка характеристики лучшего в группе.',
  event: 'Событие с выбором — как в нынешних данжах.',
  rest: 'Привал: лечение и воскрешение за золото.',
  merchant: 'Торговец подземелья.',
  teleport: 'Переносит группу в другую комнату.',
  fork: 'Развилка — несколько путей дальше.',
  deadend: 'Тупик.',
};

/** Rooms that hold something to fight or take: they get a wax seal once dealt with. */
const CLEARABLE = new Set<BoardRoomType>(['battle', 'boss', 'treasure', 'trap', 'event', 'rest']);
/** A fight is won at once; a chest, a rest or an event is used up after a look at it as it was. */
const CLEAR_DELAY_MS = { fight: 900, other: 4000 };

const DICE_SETTLE_MS = 1200;
const TELEPORT_DELAY_MS = 1100;
const ZOOM_MIN = 0.6;
const ZOOM_MAX = 5;
/** Camera distance multiplier that fits the whole sketch dungeon on screen. */
const OVERVIEW_ZOOM = 4.4;

/** Rune circles that carry the party to each other. */
const TELEPORT_PAIRS: Record<number, number> = { 14: 20, 20: 14 };
const SAFE_ROLL = 7;

const roll = () => 1 + Math.floor(Math.random() * 6);

const DungeonBoardSketchPage = () => {
  const { graphics } = useClientPrefs();
  const webgl = useMemo(() => isWebGLAvailable(), []);
  const [theme, setTheme] = useState<DungeonTheme>('stone');
  const dungeon = useMemo(() => ({ ...SKETCH_DUNGEON, theme }), [theme]);
  const roomById = useMemo(() => new Map(dungeon.rooms.map((r) => [r.id, r])), [dungeon]);

  const [current, setCurrent] = useState(dungeon.entranceId);
  const [revealed, setRevealed] = useState(() => new Set([dungeon.entranceId]));
  const [cleared, setCleared] = useState(() => new Set<number>());
  const [dice, setDice] = useState<DiceThrow | null>(null);
  // A class challenge tried here, and what the server would have kept to itself.
  const [tryout, setTryout] = useState<ChallengeStart | null>(null);
  const [games3D, setGames3D] = useState(true);
  const tryoutSecret = useRef<SketchSecret | null>(null);
  const startTryout = (kind: ChallengeKind) => {
    const { start, secret } = makeSketchChallenge(kind);
    tryoutSecret.current = secret;
    setTryout(start);
  };
  const [message, setMessage] = useState<string | null>('Нажмите на светящуюся плитку рядом с группой, чтобы пойти.');
  const busy = useRef(false);
  const [zoom, setZoom] = useState(1);
  const [overview, setOverview] = useState(false);

  const reachable = useMemo(() => {
    const set = new Set<number>();
    dungeon.corridors.forEach((c) => {
      if (c.from === current) set.add(c.to);
      if (c.to === current) set.add(c.from);
    });
    return set;
  }, [dungeon, current]);

  const arrive = useCallback(
    (roomId: number) => {
      setCurrent(roomId);
      setRevealed((prev) => new Set(prev).add(roomId));
      const room = roomById.get(roomId);
      if (room && CLEARABLE.has(room.type)) {
        // In the sketch every room is won by walking in; the real game waits for the battle, the chest, the choice.
        const fight = room.type === 'battle' || room.type === 'boss';
        setTimeout(() => setCleared((prev) => new Set(prev).add(roomId)), fight ? CLEAR_DELAY_MS.fight : CLEAR_DELAY_MS.other);
      }
      setMessage(room ? `${room.name}. ${ROOM_HINT[room.type]}` : null);
      setOverview(false);
      const pair = TELEPORT_PAIRS[roomId];
      if (pair !== undefined) {
        busy.current = true;
        setTimeout(() => {
          setCurrent(pair);
          setRevealed((prev) => new Set(prev).add(pair));
          const target = roomById.get(pair);
          setMessage(`Руны вспыхнули — группу перенесло в «${target?.name ?? '?'}».`);
          busy.current = false;
        }, TELEPORT_DELAY_MS);
      }
    },
    [roomById],
  );

  const handleTileClick = useCallback(
    (roomId: number) => {
      if (busy.current || !reachable.has(roomId)) return;
      const corridor = dungeon.corridors.find(
        (c) => (c.from === current && c.to === roomId) || (c.to === current && c.from === roomId),
      );
      if (!corridor?.risky) {
        arrive(roomId);
        return;
      }
      // A risky way: the gods throw the dice before the party sets out.
      busy.current = true;
      const values: [number, number] = [roll(), roll()];
      setDice({ values, at: performance.now() });
      setMessage('Боги бросают кости…');
      setTimeout(() => {
        const total = values[0] + values[1];
        setMessage(
          total >= SAFE_ROLL
            ? `Выпало ${total} — группа прошла тихо.`
            : `Выпало ${total} — засада в коридоре! (в настоящем данже начнётся бой)`,
        );
        arrive(roomId);
        busy.current = false;
      }, DICE_SETTLE_MS);
    },
    [arrive, current, dungeon, reachable],
  );

  const restart = () => {
    setCurrent(dungeon.entranceId);
    setRevealed(new Set([dungeon.entranceId]));
    setCleared(new Set());
    setDice(null);
    setOverview(false);
    setZoom(1);
    setMessage('Начали заново.');
  };

  const showWholeDungeon = () => {
    setRevealed(new Set(dungeon.rooms.map((r) => r.id)));
    setOverview(true);
    setZoom(OVERVIEW_ZOOM);
    setMessage('Всё подземелье собрано. Колёсико мыши — приблизить и отдалить.');
  };

  const backToParty = () => {
    setOverview(false);
    setZoom(1);
  };

  const here = roomById.get(current);

  // Nothing to scroll to under a full-screen table.
  useEffect(() => {
    const root = document.documentElement;
    const previous = root.style.overflow;
    root.style.overflow = 'hidden';
    return () => {
      root.style.overflow = previous;
    };
  }, []);

  return (
    // The whole screen under the site header: the header stays on top of the
    // table, the footer and page scroll are out of the way.
    <div
      className="fixed inset-0 z-0 bg-black"
      onWheel={(e) => setZoom((z) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z * (e.deltaY > 0 ? 1.12 : 1 / 1.12))))}
    >
      {webgl ? (
        <Suspense
          fallback={
            <div className="flex h-full items-center justify-center">
              <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
            </div>
          }
        >
          <DungeonBoardScene
            dungeon={dungeon}
            party={SKETCH_PARTY}
            currentRoomId={current}
            revealed={revealed}
            cleared={cleared}
            reachable={reachable}
            dice={dice}
            lowGraphics={graphics === 'low'}
            zoom={zoom}
            overview={overview}
            onTileClick={handleTileClick}
          />
        </Suspense>
      ) : (
        <div className="flex h-full items-center justify-center p-6 text-center text-white/60 text-sm">
          Устройство не поддерживает 3D (нет WebGL) — здесь будет обычная 2D-карта.
        </div>
      )}

      {/* What is happening, over the table */}
      <div className="pointer-events-none absolute left-3 right-3 bottom-3 sm:left-5 sm:right-auto sm:bottom-5 sm:max-w-md flex flex-col gap-2">
        <div className="bg-black/70 backdrop-blur-sm rounded-card px-4 py-3">
          <p className="gold-text text-base sm:text-lg uppercase">{dungeon.name}</p>
          {here && <p className="text-white text-sm">{here.name}</p>}
          {message && <p className="text-white/75 text-sm mt-1">{message}</p>}
        </div>
      </div>

      <div className="absolute right-3 bottom-3 sm:right-5 sm:bottom-5 hidden sm:flex flex-col items-end gap-2">
        <div className="pointer-events-none bg-black/60 rounded-card px-3 py-2 text-xs text-white/75 flex flex-col gap-1">
          {SKETCH_PARTY.map((m) => (
            <span key={m.id} className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: m.color }} />
              {m.name}
              {m.leader && <span className="text-gold">· лидер</span>}
            </span>
          ))}
        </div>
        <div className="bg-black/60 rounded-card px-3 py-2 text-xs flex gap-3">
          {overview ? (
            <button type="button" onClick={backToParty} className="site-link">
              К группе
            </button>
          ) : (
            <button type="button" onClick={showWholeDungeon} className="site-link">
              Показать всё подземелье
            </button>
          )}
          <button type="button" onClick={restart} className="site-link">
            Начать заново
          </button>
          <button type="button" onClick={() => setGames3D((v) => !v)} className="site-link">
            Игры: {games3D ? '3D' : '2D'}
          </button>
          {SKETCH_CHALLENGES.map((c) => (
            <button key={c.kind} type="button" onClick={() => startTryout(c.kind)} className="site-link">
              {c.label}
            </button>
          ))}
          <Link to="/admin/dungeons" className="site-link">
            К подземельям
          </Link>
        </div>
        <label className="bg-black/60 rounded-card px-3 py-2 text-xs flex items-center gap-2">
          <span className="text-white/60">Оформление:</span>
          <select
            value={theme}
            onChange={(e) => setTheme(e.target.value as DungeonTheme)}
            className="bg-transparent text-white outline-none"
          >
            {DUNGEON_THEMES.map((t) => (
              <option key={t} value={t} className="bg-site-bg">
                {THEME_INFO[t].name}
              </option>
            ))}
          </select>
        </label>
        <p className="pointer-events-none text-white/40 text-[11px]">Набросок на тестовых данных — сервер не участвует.</p>
      </div>
      <ChallengeModal
        challenge={tryout}
        onFinish={async (presses, ended) => (tryout ? settleSketch(tryout, presses, ended) : null)}
        onStep={async (move) => (tryout && tryoutSecret.current ? stepSketch(tryout, tryoutSecret.current, move) : null)}
        onClose={() => setTryout(null)}
        use3D={games3D}
      />
    </div>
  );
};

export default DungeonBoardSketchPage;
