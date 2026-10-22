import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Sparkles } from '@react-three/drei';
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { ChevronLeft, ChevronRight } from 'react-feather';
import { createFlameTexture, createSoftSpotTexture, createTableWoodTexture } from '../../pages/BattlePage/Arena3D/textures';
import Book, { OPEN_DEPTH, OPEN_WIDTH } from './Book';
import ClassCandle from './ClassCandle';
import ClassProps from './ClassProps';
import CharacterDossier, { DOSSIER_SIZE } from './CharacterDossier';
import type { PassportData } from '../../CommonComponents/CharacterPassport/types';
import Inkwell from './Inkwell';
import TableMap from './TableMap';
import type { MapMarks } from './worldMap';
import type { QuillStroke } from './quillStroke';
import { MetalEnvContext, noRaycast } from './bookParts';
import { buildSpread } from './spreadLayout';
import type { NodePageAction, NodePageModel } from './nodePageModel';
import type { SkillPageAction, SkillPageModel } from './skillPageModel';
import type { CharacterTreeProgressResponse, FullClassTreeResponse } from '../types';

/*
  The skill tree as three books lying on the table of fates, one per class.
  The player's own book is opened on arrival; the camera slides along the table
  to the others, which open for reading only.
*/

export interface ShelfBook {
  classId: number;
  title: string;
  /** The player's own class: the only book whose path can be chosen. */
  own: boolean;
  tree: FullClassTreeResponse;
  progress: CharacterTreeProgressResponse | null;
  /** The subclass the player chose, bound in as a later chapter of this book. */
  chapter?: {
    title: string;
    tree: FullClassTreeResponse;
    progress: CharacterTreeProgressResponse | null;
    /** Its opening words: the subclass tree's own description. */
    intro: string[];
  } | null;
}

interface BookTableSceneProps {
  books: ShelfBook[];
  /** Book laid in front of the player on arrival. */
  initialClassId: number;
  onNodeClick: (nodeId: number) => void;
  /** The opened node's page, for the book in front of the player. */
  nodePage: NodePageModel | null;
  onNodeAction: (action: NodePageAction) => void;
  /** The skill being upgraded, whose spread the book turns to. */
  skillPage: SkillPageModel | null;
  onSkillAction: (action: SkillPageAction) => void;
  /** The player moved to another book or shut this one: whatever node was open goes with it. */
  onLeaveBook: () => void;
  /** The player's book lies open at its subclass chapter. */
  atChapter: boolean;
  /** The chapter ribbon was touched: turn to the subclass chapter, or back. */
  onToggleChapter: () => void;
  /** The player's Скиталец passport, laid beside their own book once it has loaded. */
  passport?: PassportData | null;
  /** In-game year, for the passport's «в строю N лет». */
  currentGameYear?: number | null;
}

/**
 * Distance between neighbouring books along the table. Wide enough that the
 * next book's candles, and the straps and flaps a book lays out on the table
 * as it opens, never reach the open spread.
 */
const BOOK_SPACING = 11;
/** Each closed book lies a little askew; these keep it from looking arranged. */
const REST_YAWS = [0.12, -0.07, 0.09];

const CAMERA_FOV = 38;
/**
 * The camera has three poses, eased between:
 * - at the table, while the book lies shut: higher, further back and more
 *   tilted, taking in the book and its candles whole;
 * - the open book: down close on the spread, the candles left out of shot
 *   and only their light on the pages;
 * - reading a node's page: leaning in over the book.
 */
const TABLE_POLAR = 0.68;
const TABLE_FILL = 0.95;
/** Camera tilt over an open book, radians: high enough that the pages read without much foreshortening. */
const CAMERA_POLAR = 0.42;
/**
 * Tilt while a node's page is open: the camera leans in over the book to read,
 * nearly straight down, so the page lies square to the screen and its flat
 * overlay sits on it exactly (see Book's node page).
 */
const READING_POLAR = 0.06;
/** Looking down to read, the spread fills nearly the whole frame. */
const READING_FILL = 0.95;
/** Share of the frame the open spread may fill. */
const FRAME_FILL = 0.97;
/** Air around the spread taken into the framing, world units. */
const SPREAD_MARGIN = 0.05;
/** How quickly the camera settles on a new book; higher is snappier. */
const CAMERA_DAMPING = 3.2;
/** How far the view leans after the pointer, radians. */
const PARALLAX = { theta: 0.06, phi: 0.03 } as const;

/** A swipe must cover this many pixels, within this many milliseconds. */
const SWIPE_PX = 60;
const SWIPE_MS = 700;

const BACKGROUND = '#07060a';
/** Room kept in shot beyond the head of an open book, for the chapter ribbon trailing from it. */
const RIBBON_ROOM = 1.2;
/**
 * Where each book's candles stand, from its spine: off the far left corner of
 * the open spread, out of shot once the book is open, in shot at the table.
 */
const CANDLE_SPOT = { x: -OPEN_WIDTH / 2 - 0.9, z: -OPEN_DEPTH / 2 - 0.9 } as const;
/** Where each book's inkwell stands, from its spine: off the far right corner, matching the candles. */
const INKWELL_SPOT = { x: OPEN_WIDTH / 2 + 0.75, z: -OPEN_DEPTH / 2 - 0.5 } as const;
/** The map's one compass rose: in the near left corner of the table, beside the first book, from its spine. */
const ROSE_SPOT = { x: -OPEN_WIDTH / 2 - 1.1, z: 1.4 } as const;
/** How far the map reaches past the outermost books, each side. */
const MAP_OVERHANG = 5.5;
/** Where the map's centre lies along the table's depth: drawn back, so most of it shows behind the books. */
const MAP_CENTER_Z = -1.5;
/**
 * Where the player's passport lies, from their book's spine: off to the left,
 * half under where the shut book sits, so the front board comes down over it
 * when the book is opened.
 */
const DOSSIER_SPOT = { x: -2.55, z: 0.5, yaw: 0.1 } as const;
/** Reading the passport: looking nearly straight down, the sheet filling most of the frame. */
const PAPER_POLAR = 0.05;
const PAPER_FILL = 0.9;
/** Room kept clear under the sheet for the buttons over the bottom of the canvas, world units. */
const PAPER_HUD_ROOM = 0.55;
const PAPER_POINTS = [
  [-1, -1],
  [1, -1],
  [-1, 1],
  [1, 1],
].map(
  ([sx, sz]) =>
    new THREE.Vector3((sx * DOSSIER_SIZE.width) / 2, 0, (sz * DOSSIER_SIZE.depth) / 2 + (sz > 0 ? PAPER_HUD_ROOM : 0)),
);
/** Height the tallest flame reaches, for framing the table view. */
const CANDLE_TOP = 1.7;

/**
 * Camera distance and aim that fit an open spread into the canvas. Found by
 * projecting the spread's corners: under a tilt the near edge looms larger
 * than the far one, so the aim is slid along the table until the spread sits
 * as centred as it can, then the camera pulled in as close as that allows.
 */
/** What each pose has to keep in shot, around the focused book's spine. */
const SPREAD_POINTS = (() => {
  const halfW = OPEN_WIDTH / 2 + SPREAD_MARGIN;
  const halfD = OPEN_DEPTH / 2 + SPREAD_MARGIN;
  return [
    [-halfW, 0, -halfD - RIBBON_ROOM],
    [halfW, 0, -halfD - RIBBON_ROOM],
    [-halfW, 0, halfD],
    [halfW, 0, halfD],
  ].map(([x, y, z]) => new THREE.Vector3(x, y, z));
})();
/**
 * Below this canvas width-to-height — a phone held upright — the open book is
 * read a page at a time, and the table is framed close round the shut book.
 */
const NARROW_ASPECT = 0.9;
/**
 * One page of the open spread, centred on itself: what a narrow screen frames
 * instead of the spread. A little of the chapter ribbon is kept in at the head,
 * and room at the foot for the one button left over the page.
 */
const PAGE_POINTS = (() => {
  const halfW = OPEN_WIDTH / 4 + SPREAD_MARGIN;
  const halfD = OPEN_DEPTH / 2 + SPREAD_MARGIN;
  const ribbon = 0.45;
  const button = 0.5;
  return [
    [-halfW, 0, -halfD - ribbon],
    [halfW, 0, -halfD - ribbon],
    [-halfW, 0, halfD + button],
    [halfW, 0, halfD + button],
  ].map(([x, y, z]) => new THREE.Vector3(x, y, z));
})();
/** How far the middle of either page lies from the spine. */
const PAGE_CENTRE_X = OPEN_WIDTH / 4;
/** The table round a shut book on a narrow screen: the book and what lies nearest it, the rest let go. */
const TABLE_POINTS_NARROW = [
  [-2.4, 0, -3.4],
  [2.4, 0, -3.4],
  [-2.4, 0, 2.6],
  [2.4, 0, 2.6],
].map(([x, y, z]) => new THREE.Vector3(x, y, z));
/**
 * What reading a page frames: the spread alone — the chapter ribbon at its
 * head is not wanted while a page is read — with room at its foot for the one
 * button left over the book. Every pixel counts here: on a smaller screen the
 * writing on the pages is only just large enough to read.
 */
const READING_POINTS = (() => {
  const halfW = OPEN_WIDTH / 2 + SPREAD_MARGIN;
  const halfD = OPEN_DEPTH / 2 + SPREAD_MARGIN;
  const button = 0.4;
  return [
    [-halfW, 0, -halfD],
    [halfW, 0, -halfD],
    [-halfW, 0, halfD + button],
    [halfW, 0, halfD + button],
  ].map(([x, y, z]) => new THREE.Vector3(x, y, z));
})();
/** The table view: the candles and their flames, mirrored to the right so the book stays centred. */
const TABLE_POINTS = (() => {
  const halfW = -CANDLE_SPOT.x + 1;
  const back = CANDLE_SPOT.z - 0.9;
  const front = OPEN_DEPTH / 2 + 0.3;
  return [
    [-halfW, 0, back],
    [halfW, 0, back],
    [-halfW, CANDLE_TOP, CANDLE_SPOT.z],
    [halfW, CANDLE_TOP, CANDLE_SPOT.z],
    [-halfW, 0, front],
    [halfW, 0, front],
  ].map(([x, y, z]) => new THREE.Vector3(x, y, z));
})();

/**
 * Camera distance and aim that fit a set of points into the canvas. Found by
 * projecting them: under a tilt what is near looms larger than what is far, so
 * the aim is slid along the table until they sit as centred as they can, then
 * the camera pulled in as close as that allows.
 */
const fitView = (aspect: number, polar: number, points: THREE.Vector3[], fill: number) => {
  const depth = Math.max(...points.map((p) => Math.abs(p.z)));
  const probe = new THREE.PerspectiveCamera(CAMERA_FOV, aspect, 0.1, 500);
  const point = new THREE.Vector3();
  const target = new THREE.Vector3();
  /** How far the points reach from the frame centre, and how lopsided they sit, in NDC. */
  const measure = (distance: number, aimZ: number) => {
    target.set(0, 0, aimZ);
    probe.position.setFromSpherical(new THREE.Spherical(distance, polar, 0)).add(target);
    probe.lookAt(target);
    probe.updateMatrixWorld();
    let worst = 0;
    let top = -Infinity;
    let bottom = Infinity;
    for (const p of points) {
      point.copy(p).project(probe);
      if (point.z < -1 || point.z > 1) return { reach: Infinity, offset: 0 };
      worst = Math.max(worst, Math.abs(point.x), Math.abs(point.y));
      top = Math.max(top, point.y);
      bottom = Math.min(bottom, point.y);
    }
    return { reach: worst, offset: Math.abs(top + bottom) };
  };
  let best = { distance: Infinity, aimZ: 0, offset: Infinity };
  for (let i = -16; i <= 16; i++) {
    const aimZ = (i / 16) * depth * 0.5;
    let distance = 1;
    while (measure(distance, aimZ).reach > fill && distance < 200) distance *= 1.01;
    const { offset } = measure(distance, aimZ);
    if (offset < best.offset) best = { distance, aimZ, offset };
  }
  return best;
};

/** Glides the camera to the focused book and lets it lean a little after the pointer. */
interface CameraRigProps {
  focusX: number;
  /** The focused book lies open: come down close on the spread, and stop leaning after the pointer. */
  open: boolean;
  /** A node's page is open: lean in over the book to read it. */
  reading: boolean;
  /** Where the passport lies, if there is one on the table. */
  paper: { x: number; z: number } | null;
  /** The passport has been taken up to read: look down onto it. */
  readingPaper: boolean;
  /** On a narrow screen, the one page of the open book in view; null frames the whole spread. */
  page: 'left' | 'right' | null;
  narrow: boolean;
}

const CameraRig = ({ focusX, open, reading, paper, readingPaper, page, narrow }: CameraRigProps) => {
  const { camera, size, pointer, scene } = useThree();
  const aspect = size.width / Math.max(1, size.height);
  const tableFit = useMemo(
    () => fitView(aspect, TABLE_POLAR, narrow ? TABLE_POINTS_NARROW : TABLE_POINTS, TABLE_FILL),
    [aspect, narrow],
  );
  const openFit = useMemo(
    () => fitView(aspect, CAMERA_POLAR, narrow ? PAGE_POINTS : SPREAD_POINTS, FRAME_FILL),
    [aspect, narrow],
  );
  const readingFit = useMemo(
    () => fitView(aspect, READING_POLAR, narrow ? PAGE_POINTS : READING_POINTS, READING_FILL),
    [aspect, narrow],
  );
  /** How far the view has slid off the spine toward the page in view, eased. */
  const pageShift = useRef(0);
  const paperFit = useMemo(() => fitView(aspect, PAPER_POLAR, PAPER_POINTS, PAPER_FILL), [aspect]);
  // Kept after the passport is put down, so the camera has somewhere to come back from.
  const lastPaper = useRef(paper);
  if (paper) lastPaper.current = paper;
  const aim = useRef(new THREE.Vector3(focusX, 0, 0));
  const lean = useRef({ theta: 0, phi: 0 });
  /** 0 at the table, 1 over the open book; and 0 over the open book, 1 leaning in to read. */
  const pose = useRef({ open: 0, read: 0, paper: 0 });
  const placed = useRef(false);

  useEffect(() => {
    scene.fog = new THREE.Fog(BACKGROUND, tableFit.distance * 1.4, tableFit.distance * 3.2);
  }, [scene, tableFit.distance]);

  useFrame((_, delta) => {
    pose.current.open = THREE.MathUtils.damp(pose.current.open, open ? 1 : 0, CAMERA_DAMPING, delta);
    pose.current.read = THREE.MathUtils.damp(pose.current.read, reading ? 1 : 0, CAMERA_DAMPING, delta);
    pose.current.paper = THREE.MathUtils.damp(pose.current.paper, readingPaper && paper ? 1 : 0, CAMERA_DAMPING, delta);
    const { open: o, read: r } = pose.current;
    const blend = (table: number, opened: number, read: number) =>
      THREE.MathUtils.lerp(THREE.MathUtils.lerp(table, opened, o), read, r);

    const poseZ = blend(tableFit.aimZ, openFit.aimZ, readingFit.aimZ);
    if (!placed.current) {
      aim.current.set(focusX, 0, 0);
      placed.current = true;
    } else {
      // The book in focus is followed smoothly; the pose's own shift is
      // already eased, so it is added on top undamped.
      aim.current.x = THREE.MathUtils.damp(aim.current.x, focusX, CAMERA_DAMPING, delta);
    }
    // A page at a time: slide across to it, more as the book comes open.
    const pageTarget = page === 'left' ? -PAGE_CENTRE_X : page === 'right' ? PAGE_CENTRE_X : 0;
    pageShift.current = THREE.MathUtils.damp(pageShift.current, pageTarget, CAMERA_DAMPING, delta);
    const lookAt = new THREE.Vector3(aim.current.x + pageShift.current * o, 0, aim.current.z + poseZ);
    // An open book holds still: its pages carry real controls, and a view that
    // leans after the pointer slides them out from under it on the way there.
    const leanTheta = open ? 0 : pointer.x * PARALLAX.theta;
    const leanPhi = open ? 0 : -pointer.y * PARALLAX.phi;
    lean.current.theta = THREE.MathUtils.damp(lean.current.theta, leanTheta, 2, delta);
    lean.current.phi = THREE.MathUtils.damp(lean.current.phi, leanPhi, 2, delta);
    camera.position
      .setFromSpherical(
        new THREE.Spherical(
          blend(tableFit.distance, openFit.distance, readingFit.distance),
          blend(TABLE_POLAR, CAMERA_POLAR, READING_POLAR) + lean.current.phi,
          lean.current.theta,
        ),
      )
      .add(lookAt);
    // Over the passport: the same easing, toward a view straight down onto it.
    const p = pose.current.paper;
    const sheet = lastPaper.current;
    if (p > 1e-4 && sheet) {
      const paperLook = new THREE.Vector3(sheet.x, 0, sheet.z).add(
        new THREE.Vector3(0, 0, paperFit.aimZ).applyAxisAngle(THREE.Object3D.DEFAULT_UP, DOSSIER_SPOT.yaw),
      );
      const paperEye = new THREE.Vector3()
        // Turned with the sheet, so its lines run level across the screen.
        .setFromSpherical(new THREE.Spherical(paperFit.distance, PAPER_POLAR, DOSSIER_SPOT.yaw))
        .add(paperLook);
      camera.position.lerp(paperEye, p);
      lookAt.lerp(paperLook, p);
    }
    camera.lookAt(lookAt);
  });

  return null;
};

/**
 * Something for metal to reflect, built locally rather than fetched: without it
 * iron, gold and silver render near black in a scene lit only by candles. Only
 * metal gets it (see MetalEnvContext); everything else stays candlelit.
 */
const MetalEnvironment = ({ children }: { children: ReactNode }) => {
  const { gl } = useThree();
  const [env, setEnv] = useState<THREE.Texture | null>(null);
  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl);
    const texture = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    setEnv(texture);
    return () => {
      texture.dispose();
      pmrem.dispose();
    };
  }, [gl]);
  return <MetalEnvContext.Provider value={env}>{children}</MetalEnvContext.Provider>;
};

/** The old table everything lies on, and the candles that light it. */
interface TableProps {
  span: number;
  classIds: number[];
  /** The book whose quill is writing, and what. */
  writing: { book: number; stroke: QuillStroke } | null;
}

const Table = ({ span, classIds, writing }: TableProps) => {
  const wood = useMemo(() => {
    const tex = createTableWoodTexture();
    tex.repeat.set(4, 2.5);
    return tex;
  }, []);
  const flame = useMemo(createFlameTexture, []);
  const glow = useMemo(createSoftSpotTexture, []);
  useEffect(
    () => () => {
      wood.dispose();
      flame.dispose();
      glow.dispose();
    },
    [wood, flame, glow],
  );

  // Where each book lies along the table, by its spine.
  const bookXs = useMemo(() => {
    const xs: number[] = [];
    for (let x = -span / 2; x <= span / 2 + 0.01; x += BOOK_SPACING) xs.push(x);
    return xs;
  }, [span]);

  // What stands on the map leaves its mark there; map coordinates are from its centre.
  const marks = useMemo<MapMarks>(
    () => ({
      roses: bookXs.length ? [[bookXs[0] + ROSE_SPOT.x, ROSE_SPOT.z - MAP_CENTER_Z]] : [],
      inkSpots: bookXs.map((x) => [x + INKWELL_SPOT.x, INKWELL_SPOT.z - MAP_CENTER_Z]),
      waxSpots: bookXs.map((x) => [x + CANDLE_SPOT.x, CANDLE_SPOT.z - MAP_CENTER_Z]),
    }),
    [bookXs],
  );

  return (
    <group>
      {/* Just under the map, so nothing laid on the table fights with the wood */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]} receiveShadow>
        <planeGeometry args={[span + 60, 40]} />
        <meshStandardMaterial map={wood} roughness={0.85} metalness={0.02} />
      </mesh>
      <TableMap width={span + MAP_OVERHANG * 2} centerZ={MAP_CENTER_Z} marks={marks} />
      {/* Each book's own candles stand off its far left corner, lighting the
          pages from the side without standing over them; its inkwell off the
          far right; and its class's things round about. */}
      {bookXs.map((x, i) => (
        <group key={x}>
          <ClassCandle
            classId={classIds[i]}
            position={[x + CANDLE_SPOT.x, 0, CANDLE_SPOT.z]}
            seed={i + 1}
            flame={flame}
            glow={glow}
          />
          <ClassProps classId={classIds[i]} position={[x, 0, 0]} />
          <Inkwell
            classId={classIds[i]}
            position={[x + INKWELL_SPOT.x, 0, INKWELL_SPOT.z]}
            seed={i + 1}
            stroke={writing?.book === i ? writing.stroke : null}
          />
        </group>
      ))}
    </group>
  );
};

const BookTableScene = ({
  books,
  initialClassId,
  onNodeClick,
  nodePage,
  onNodeAction,
  skillPage,
  onSkillAction,
  onLeaveBook,
  atChapter,
  onToggleChapter,
  passport = null,
  currentGameYear = null,
}: BookTableSceneProps) => {
  const spreads = useMemo(() => books.map((b) => buildSpread(b.tree, b.progress, !b.own)), [books]);
  // Each book's subclass chapter, if it has one; kept stable so its pages aren't redrawn needlessly.
  const chapters = useMemo(
    () =>
      books.map((b) =>
        b.chapter
          ? { spread: buildSpread(b.chapter.tree, b.chapter.progress, false), title: b.chapter.title, intro: b.chapter.intro }
          : null,
      ),
    [books],
  );
  const [focus, setFocus] = useState(() => Math.max(0, books.findIndex((b) => b.classId === initialClassId)));
  // Every book waits on the table shut until the player opens it; moving on
  // to another book closes the one left behind.
  const [opened, setOpened] = useState(false);
  // The passport, taken up off the table to be read.
  const [readingPaper, setReadingPaper] = useState(false);

  // A phone held upright: the open book is read a page at a time.
  const frame = useRef<HTMLDivElement>(null);
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const el = frame.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setNarrow(width / Math.max(1, height) < NARROW_ASPECT);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  /**
   * Which page is in view on a narrow screen. By default it follows what is
   * written: a node's or a skill's page on the left, the tree on the right.
   * The player can turn to the other page; whatever is opened next takes
   * them back to where it is written.
   */
  const [pageChoice, setPageChoice] = useState<'left' | 'right' | null>(null);
  // The quill writing a node just taken in the open book.
  const [writing, setWriting] = useState<{ book: number; stroke: QuillStroke } | null>(null);
  const span = (books.length - 1) * BOOK_SPACING;
  const xOf = useCallback((i: number) => i * BOOK_SPACING - span / 2, [span]);

  const pageContext = !opened
    ? 'shut'
    : skillPage
      ? `skill-${skillPage.skillId}`
      : nodePage
        ? `node-${nodePage.nodeId}`
        : atChapter
          ? 'chapter'
          : 'tree';
  useEffect(() => setPageChoice(null), [pageContext]);
  const page: 'left' | 'right' | null =
    narrow && opened ? pageChoice ?? (skillPage || nodePage ? 'left' : 'right') : null;
  /** A node's or a skill's page is open and the camera leans in to read it. */
  const reading = opened && (nodePage !== null || skillPage !== null);
  /** The HUD gives up its room to the pages: only the close button stays, low down. */
  const compactHud = page !== null || reading;

  // Until the player turns to another book themselves, the one in front of
  // them is their own — even if the shelf filled in after the table was laid.
  const playerMoved = useRef(false);
  useEffect(() => {
    if (playerMoved.current) return;
    const own = books.findIndex((b) => b.classId === initialClassId);
    if (own >= 0) setFocus(own);
  }, [books, initialClassId]);

  const focusOn = useCallback(
    (i: number) => {
      playerMoved.current = true;
      const next = THREE.MathUtils.clamp(i, 0, books.length - 1);
      if (next !== focus) {
        setOpened(false);
        setReadingPaper(false);
        onLeaveBook();
      }
      setFocus(next);
    },
    [books.length, focus, onLeaveBook],
  );
  const go = useCallback((step: number) => focusOn(focus + step), [focusOn, focus]);

  const selectBook = useCallback(
    (i: number) => {
      setReadingPaper(false);
      if (i === focus) setOpened(true);
      else focusOn(i);
    },
    [focus, focusOn],
  );

  // The passport lies by the player's own book.
  const ownIndex = books.findIndex((b) => b.own);
  const paperSpot =
    passport && ownIndex >= 0 ? { x: xOf(ownIndex) + DOSSIER_SPOT.x, z: DOSSIER_SPOT.z } : null;
  const toggleReadingPaper = useCallback(() => {
    if (readingPaper) {
      setReadingPaper(false);
      return;
    }
    // Taken up from wherever it can be reached: the camera comes to its book, which stays shut.
    if (ownIndex >= 0 && ownIndex !== focus) focusOn(ownIndex);
    if (opened) {
      setOpened(false);
      onLeaveBook();
    }
    setReadingPaper(true);
  }, [readingPaper, ownIndex, focus, focusOn, opened, onLeaveBook]);

  // Arrow keys page between books, unless the player is typing somewhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return;
      if (e.key === 'ArrowLeft') go(-1);
      if (e.key === 'ArrowRight') go(1);
      if (e.key === 'Escape') setReadingPaper(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [go]);

  const swipe = useRef<{ x: number; at: number } | null>(null);
  const handlePointerDown = (e: ReactPointerEvent) => {
    swipe.current = { x: e.clientX, at: performance.now() };
  };
  const handlePointerUp = (e: ReactPointerEvent) => {
    const start = swipe.current;
    swipe.current = null;
    if (!start || performance.now() - start.at > SWIPE_MS) return;
    const dx = e.clientX - start.x;
    if (Math.abs(dx) < SWIPE_PX) return;
    // Reading a page at a time, a swipe turns to the other page; otherwise to the next book.
    if (page) setPageChoice(dx < 0 ? 'right' : 'left');
    else go(dx < 0 ? 1 : -1);
  };

  useEffect(() => () => {
    document.body.style.cursor = '';
  }, []);

  const current = books[focus];

  return (
    <div ref={frame} className="relative w-full h-full touch-pan-y" onPointerDown={handlePointerDown} onPointerUp={handlePointerUp}>
      <Canvas dpr={[1, 1.75]} gl={{ antialias: true, powerPreference: 'high-performance' }} camera={{ fov: CAMERA_FOV, near: 0.1, far: 300 }}>
        <color attach="background" args={[BACKGROUND]} />
        <ambientLight intensity={0.28} />
        <hemisphereLight args={['#8090c0', '#1a1008', 0.35]} />
        {/* Cool moonlight from the side, so the candles aren't the only warm-on-dark */}
        <directionalLight position={[-6, 12, 6]} intensity={0.7} color="#c8d2ff" />
        <MetalEnvironment>
          <Table span={span} classIds={books.map((b) => b.classId)} writing={writing} />
          {books.map((book, i) => (
            <Book
              key={book.classId}
              classId={book.classId}
              title={book.title}
              position={[xOf(i), 0, 0]}
              restYaw={REST_YAWS[i % REST_YAWS.length]}
              open={opened && i === focus}
              onSelect={() => selectBook(i)}
              spread={spreads[i]}
              onNodeClick={onNodeClick}
              nodePage={opened && i === focus ? nodePage : null}
              onNodeAction={onNodeAction}
              skillPage={opened && i === focus ? skillPage : null}
              onSkillAction={onSkillAction}
              chapter={chapters[i]}
              atChapter={atChapter && i === focus}
              onToggleChapter={onToggleChapter}
              onInk={(stroke) => {
                setWriting({ book: i, stroke });
                // The quill writes on the tree: turn there to watch it.
                setPageChoice('right');
              }}
            />
          ))}
          {passport && paperSpot && (
            <CharacterDossier
              data={passport}
              currentGameYear={currentGameYear}
              position={[paperSpot.x, 0, paperSpot.z]}
              yaw={DOSSIER_SPOT.yaw}
              onToggle={toggleReadingPaper}
            />
          )}
        </MetalEnvironment>
        <Sparkles raycast={noRaycast} count={70} scale={[span + 12, 4, 10]} position={[0, 2, 0]} size={2.2} speed={0.2} opacity={0.4} color="#e8c48a" />
        <CameraRig
          focusX={xOf(focus)}
          open={opened}
          reading={reading}
          paper={paperSpot}
          readingPaper={readingPaper}
          page={page}
          narrow={narrow}
        />
      </Canvas>

      {/* A page at a time: across to the other page */}
      {page && (
        <button
          onClick={() => setPageChoice(page === 'right' ? 'left' : 'right')}
          aria-label={page === 'right' ? 'Левая страница' : 'Правая страница'}
          className={`absolute top-1/2 -translate-y-1/2 ${
            page === 'right' ? 'left-1.5' : 'right-1.5'
          } z-10 rounded-full bg-black/50 backdrop-blur-sm p-2.5 text-white/70 hover:text-white transition-colors duration-200`}
        >
          {page === 'right' ? <ChevronLeft size={20} /> : <ChevronRight size={20} />}
        </button>
      )}

      {/* Open / close the book in front of the player */}
      <button
        onClick={() => {
          if (readingPaper) {
            setReadingPaper(false);
            return;
          }
          if (opened) onLeaveBook();
          setOpened(!opened);
        }}
        className={`absolute ${
          // Reading, it takes the switcher's place, above the view toggle.
          compactHud ? 'bottom-14' : 'bottom-[6.75rem]'
        } left-1/2 -translate-x-1/2 z-10 whitespace-nowrap rounded-lg bg-black/50 backdrop-blur-sm px-4 py-2 text-xs uppercase tracking-wide transition-colors duration-200 ${
          opened || readingPaper ? 'text-white/50 hover:text-white' : 'text-gold hover:text-white animate-pulse'
        }`}
      >
        {readingPaper ? 'Отложить паспорт' : opened ? 'Закрыть книгу' : 'Открыть книгу'}
      </button>

      {/* Book switcher — put away while a page is read, which needs the room */}
      <div
        className={`absolute bottom-14 left-1/2 -translate-x-1/2 z-10 items-center gap-1 rounded-lg bg-black/50 backdrop-blur-sm p-1 ${
          compactHud ? 'hidden' : 'flex'
        }`}
      >
        <button
          onClick={() => go(-1)}
          disabled={focus === 0}
          aria-label="Предыдущая книга"
          className="p-2 rounded-md text-white/60 hover:text-white disabled:opacity-25 disabled:hover:text-white/60 transition-colors duration-200"
        >
          <ChevronLeft size={16} />
        </button>
        {books.map((book, i) => (
          <button
            key={book.classId}
            onClick={() => focusOn(i)}
            className={`rounded-md px-2.5 sm:px-3 py-1.5 text-xs uppercase tracking-wide transition-colors duration-200 ${
              i === focus ? 'bg-white/10 text-gold' : 'text-white/50 hover:text-white'
            }`}
          >
            {book.title}
            {book.own && <span className="block text-[9px] normal-case text-gold/70 leading-none">ваш класс</span>}
          </button>
        ))}
        <button
          onClick={() => go(1)}
          disabled={focus === books.length - 1}
          aria-label="Следующая книга"
          className="p-2 rounded-md text-white/60 hover:text-white disabled:opacity-25 disabled:hover:text-white/60 transition-colors duration-200"
        >
          <ChevronRight size={16} />
        </button>
      </div>

      {current && !current.own && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 rounded-lg bg-black/50 backdrop-blur-sm px-3 py-1 text-[11px] text-white/60">
          Чужая книга — только для чтения
        </div>
      )}
    </div>
  );
};

export default BookTableScene;
