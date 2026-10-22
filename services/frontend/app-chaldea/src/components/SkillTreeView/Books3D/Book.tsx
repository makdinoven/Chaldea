import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useFrame, type ThreeEvent } from '@react-three/fiber';
import * as THREE from 'three';
import {
  BINDINGS,
  DEFAULT_BINDING,
  STOCKS,
  PAGE_ASPECT,
  createChapterPageTexture,
  createCoverTexture,
  createLeatherTexture,
  createPageEdgeTexture,
  createTitlePageTexture,
} from './bookTextures';
import { createPageBlockGeometry, pageBow } from './pageBlock';
import { RevealMaterial, inkClock, type QuillStroke } from './quillStroke';
import { DEFAULT_FORM, FORMS, MAX_OVERHANG, PAGE_WIDTH, frameOf, useMetalEnv, type BookProgress } from './bookParts';
import { DRESSINGS } from './dressings';
import {
  CLASS_INK,
  PAGE_H as PAGE_PX_H,
  PAGE_W as PAGE_PX_W,
  createIntroInkCanvas,
  createLeftPaperCanvas,
  createLeafCanvas,
  INTRO_BACK_REGION,
  createRightPaperCanvas,
  createTreePageTexture,
  nodeRadiusPx,
  SPREAD_PX,
} from './spreadTextures';
import SpreadOverlay from './SpreadOverlay';
import type { SpreadModel, SpreadNode } from './spreadLayout';
import { LeftPageWriter } from './leftPage';
import { loadPicture, loadPictures, regionAt } from './nodePageInk';
import { actionKey, type NodePageAction, type NodePageModel } from './nodePageModel';
import { SkillSpread } from './skillSpread';
import { skillRegionAt } from './skillPageInk';
import { skillActionKey, type SkillPageAction, type SkillPageModel } from './skillPageModel';
import PageLeaf from './PageLeaf';
import ChapterRibbon from './ChapterRibbon';

/*
  One book on the table. Built with its spine along z at x = 0 and lying closed
  to the right of it; opening swings the front cover and the top half of the
  pages over the spine onto the left, so an open book is a spread centred on
  its spine.

  The frame — boards, pages, spine — is common to every book; its proportions
  and everything fitted to it come from the class (see FORMS and DRESSINGS).
*/

const PAGE_DEPTH = PAGE_WIDTH * PAGE_ASPECT;

/** How long a book takes to open or close, seconds. */
const OPEN_SECONDS = 1.4;
/** How far a shut book rises under the pointer. */
const HOVER_LIFT = 0.12;
/** Share of the opening spent undoing the fastening before the cover lifts. */
const FASTENING_SHARE = 0.28;

/** Widest an open book gets, for framing the camera. */
export const OPEN_WIDTH = (PAGE_WIDTH + MAX_OVERHANG) * 2;
export const OPEN_DEPTH = PAGE_DEPTH + MAX_OVERHANG * 2;

/** How strongly the leather's grain stands out under the light. */
const LEATHER_RELIEF = 2;

/** Gilt page edges: the paper texture under a gold sheen. */
const GILT = { color: '#e0b860', metalness: 0.75, roughness: 0.32 } as const;

/** How long a leaf takes to turn over, seconds. */
const LEAF_SECONDS = 1.1;
/** Leaves that riffle over between the class's chapter and the subclass's, and how long it takes. */
const RIFFLE_LEAVES = 4;
const RIFFLE_SECONDS = 1.7;
/** How far behind the one before it each leaf of the riffle sets off, as a share of the riffle. */
const RIFFLE_STAGGER = 0.12;
/** Height between leaves lying on one another in the riffle. */
const RIFFLE_STACK = 0.004;

/** A canvas made into a page texture. */
const pageTexture = (canvas: HTMLCanvasElement) => {
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
};

/** Extra reach round a medallion that still counts as pointing at it, in canvas pixels. */
const NODE_HIT_SLACK_PX = 14;

const easeInOut = (t: number) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

interface BookProps {
  classId: number;
  title: string;
  /** Spine position on the table when the book is open. */
  position: [number, number, number];
  /** Resting turn on the table while closed, radians. */
  restYaw: number;
  open: boolean;
  onSelect: () => void;
  /** The class tree to ink across the open spread; without it the book shows its title pages. */
  spread?: SpreadModel | null;
  onNodeClick?: (nodeId: number) => void;
  /** The opened node's page, inked onto the left-hand page in place of the book's introduction. */
  nodePage?: NodePageModel | null;
  /** A control on the node's page was used. */
  onNodeAction?: (action: NodePageAction) => void;
  /** A skill's spread: a leaf turns over to it, with its card on the left and its perks on the right. */
  skillPage?: SkillPageModel | null;
  onSkillAction?: (action: SkillPageAction) => void;
  /**
   * The subclass chapter, once the player has chosen a subclass: further on in
   * the same book, with its own tree and opening words. A ribbon marks it.
   */
  chapter?: { spread: SpreadModel; title: string; intro: string[] } | null;
  /** The book lies open at the subclass chapter rather than the class's. */
  atChapter?: boolean;
  /** The ribbon was touched: turn to the chapter, or back from it. */
  onToggleChapter?: () => void;
  /** A node was just taken on the open spread: the quill comes to write it. */
  onInk?: (stroke: QuillStroke) => void;
}

/** The node taken between two pictures of the same tree, if one was. */
const newlyTaken = (before: SpreadModel | null, after: SpreadModel | null) => {
  if (!before || !after) return null;
  const was = new Map(before.nodes.map((n) => [n.id, n.state]));
  return after.nodes.find((n) => n.state === 'chosen' && was.has(n.id) && was.get(n.id) !== 'chosen') ?? null;
};

const Book = ({
  classId,
  title,
  position,
  restYaw,
  open,
  onSelect,
  spread = null,
  onNodeClick,
  nodePage = null,
  onNodeAction,
  skillPage = null,
  onSkillAction,
  chapter = null,
  atChapter = false,
  onToggleChapter,
  onInk,
}: BookProps) => {
  const binding = BINDINGS[classId] ?? DEFAULT_BINDING;
  const form = FORMS[classId] ?? DEFAULT_FORM;
  const dressing = DRESSINGS[classId] ?? {};
  // The chapter shows only when there is one to show.
  const inChapter = atChapter && chapter !== null;
  const frame = useMemo(() => frameOf(form, PAGE_DEPTH), [form]);
  const { cover, halfBlock, boardWidth, boardDepth, hingeY, closedHeight } = frame;

  const textures = useMemo(
    () => ({
      cover: createCoverTexture(binding, title),
      leather: createLeatherTexture(binding),
      edge: createPageEdgeTexture(binding.sigil),
    }),
    [binding, title],
  );
  useEffect(() => () => Object.values(textures).forEach((t) => t.dispose()), [textures]);

  // The tree page is redrawn whenever the tree or the player's progress in it changes.
  const rightPage = useMemo(
    () => (spread ? createTreePageTexture(spread, binding, title) : createChapterPageTexture(binding)),
    [spread, binding, title],
  );

  // The left page carries the book's introduction, and a node's page when one
  // is opened, as layers of ink on its paper (see LeftPageWriter). It only
  // depends on which book this is, so progress changes don't restart its ink.
  const spreadClassId = spread?.classId ?? null;
  const spreadForeign = spread?.foreign ?? false;
  const leftPage = useMemo(() => {
    if (spreadClassId === null) {
      const texture = createTitlePageTexture(binding, title);
      const material = new THREE.MeshStandardMaterial({ map: texture, roughness: 0.92 });
      return {
        writer: null,
        material,
        dispose: () => {
          texture.dispose();
          material.dispose();
        },
      };
    }
    const stock = STOCKS[binding.sigil];
    const writer = new LeftPageWriter(
      createLeftPaperCanvas(binding),
      createIntroInkCanvas(binding, title, spreadClassId, spreadForeign),
      stock,
      CLASS_INK[spreadClassId] ?? stock.ink,
    );
    return { writer, material: writer.material, dispose: () => writer.dispose() };
  }, [binding, title, spreadClassId, spreadForeign]);
  useEffect(() => () => leftPage.dispose(), [leftPage]);

  // The subclass chapter: its tree page, and its own left page with its
  // opening words — kept apart from the class's, so each holds its writing.
  const chapterTitle = chapter?.title ?? null;
  const chapterIntro = chapter?.intro.join('\n') ?? null;
  const chapterRight = useMemo(
    () => (chapter ? createTreePageTexture(chapter.spread, binding, chapter.title) : null),
    [chapter, binding],
  );

  // The tree pages own their pictures: a new one comes in at once, or, when
  // the player has just taken a node, from under the quill's nib outward.
  const treePages = useMemo(
    () => ({ cls: new RevealMaterial(PAGE_DEPTH / PAGE_WIDTH), chapter: new RevealMaterial(PAGE_DEPTH / PAGE_WIDTH) }),
    [],
  );
  useEffect(() => () => {
    treePages.cls.dispose();
    treePages.chapter.dispose();
  }, [treePages]);
  const shownTrees = useRef<{ cls: SpreadModel | null; chapter: SpreadModel | null }>({ cls: null, chapter: null });
  /** Sends the quill to a node just taken on the page in view, and says where the ink spreads from. */
  const strokeFor = (node: SpreadNode | null) => {
    if (!node || !open) return undefined;
    const at = inkClock();
    onInk?.({
      point: [
        position[0] + node.u * PAGE_WIDTH,
        position[1] + cover + halfBlock + pageBow(node.u),
        position[2] + (0.5 - node.v) * PAGE_DEPTH,
      ],
      at,
    });
    return { center: [node.u, node.v] as [number, number], at };
  };
  useLayoutEffect(() => {
    const taken = inChapter ? null : newlyTaken(shownTrees.current.cls, spread);
    shownTrees.current.cls = spread;
    treePages.cls.show(rightPage, strokeFor(taken));
    // Only a new picture of the page brings the quill.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rightPage, treePages]);
  useLayoutEffect(() => {
    if (!chapterRight || !chapter) return;
    const taken = inChapter ? newlyTaken(shownTrees.current.chapter, chapter.spread) : null;
    shownTrees.current.chapter = chapter.spread;
    treePages.chapter.show(chapterRight, strokeFor(taken));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapterRight, treePages]);
  const chapterLeft = useMemo(() => {
    if (chapterTitle === null || spreadClassId === null) return null;
    const stock = STOCKS[binding.sigil];
    const paperCanvas = createLeftPaperCanvas(binding);
    const intro = createIntroInkCanvas(
      binding,
      chapterTitle,
      spreadClassId,
      false,
      chapterIntro?.split('\n'),
      '← К главе класса',
    );
    const writer = new LeftPageWriter(paperCanvas, intro, stock, CLASS_INK[spreadClassId] ?? stock.ink);
    // The chapter's first page as the last leaf of the riffle carries it over.
    const still = document.createElement('canvas');
    still.width = paperCanvas.width;
    still.height = paperCanvas.height;
    const ctx = still.getContext('2d');
    ctx?.drawImage(paperCanvas, 0, 0);
    ctx?.drawImage(intro, 0, 0);
    const opening = pageTexture(still);
    return {
      writer,
      opening,
      dispose: () => {
        writer.dispose();
        opening.dispose();
      },
    };
  }, [binding, spreadClassId, chapterTitle, chapterIntro]);
  useEffect(() => () => chapterLeft?.dispose(), [chapterLeft]);

  // The leaves riffled past between the chapters, each side with its own faded, unreadable notes.
  const riffleLeaves = useMemo(
    () =>
      Array.from({ length: RIFFLE_LEAVES }, (_, i) => ({
        front: pageTexture(createLeafCanvas(binding, 'right', i * 2)),
        back: pageTexture(createLeafCanvas(binding, 'left', i * 2 + 1)),
      })),
    [binding],
  );
  useEffect(
    () => () =>
      riffleLeaves.forEach((l) => {
        l.front.dispose();
        l.back.dispose();
      }),
    [riffleLeaves],
  );

  const materials = useMemo(() => {
    // The leather's own grain and creases raise it a little, so light runs over it unevenly instead of sliding off.
    const leather = new THREE.MeshStandardMaterial({
      map: textures.leather,
      bumpMap: textures.leather,
      bumpScale: LEATHER_RELIEF,
      roughness: 0.82,
      metalness: 0.02,
    });
    const edge = form.gilded
      ? new THREE.MeshStandardMaterial({ map: textures.edge, ...GILT })
      : new THREE.MeshStandardMaterial({ map: textures.edge, roughness: 0.9 });
    const coverFace = new THREE.MeshStandardMaterial({
      map: textures.cover,
      bumpMap: textures.cover,
      bumpScale: LEATHER_RELIEF,
      roughness: 0.8,
      metalness: 0.04,
    });
    // Box faces: +x, -x, +y, -y, +z, -z
    const frontCover = [leather, leather, coverFace, leather, leather, leather];
    return { leather, edge, coverFace, frontCover };
  }, [textures, form.gilded]);
  // Gilt edges are metal, and catch the same reflections as the fittings.
  useMetalEnv(materials.edge);
  useEffect(
    () => () => {
      for (const m of [materials.leather, materials.edge, materials.coverFace]) m.dispose();
    },
    [materials],
  );

  // A skill's spread, written on its own pair of pages; a leaf turns over to it.
  const skillSpread = useMemo(() => {
    if (spreadClassId === null) return null;
    const stock = STOCKS[binding.sigil];
    return new SkillSpread(
      createLeftPaperCanvas(binding),
      createRightPaperCanvas(binding),
      stock,
      CLASS_INK[spreadClassId] ?? stock.ink,
    );
  }, [binding, spreadClassId]);
  useEffect(() => () => skillSpread?.dispose(), [skillSpread]);

  // Each half of the pages: the page itself, then the paper edges. Either
  // half's page is swapped for the skill's as the leaf turns (see below).
  const pageMaterials = useMemo(() => {
    const right = treePages.cls.material;
    const chapterRightMat = treePages.chapter.material;
    const skillLeft = new THREE.MeshStandardMaterial({ map: skillSpread?.leftTexture ?? null, roughness: 0.92 });
    const skillRight = new THREE.MeshStandardMaterial({ map: skillSpread?.rightTexture ?? null, roughness: 0.92 });
    return {
      right,
      chapterRightMat,
      skillLeft,
      skillRight,
      rightPages: [right, materials.edge],
      leftPages: [leftPage.material, materials.edge],
      chapterRightPages: [chapterRightMat, materials.edge],
      chapterLeftPages: [chapterLeft?.writer.material ?? leftPage.material, materials.edge],
      skillLeftPages: [skillLeft, materials.edge],
      skillRightPages: [skillRight, materials.edge],
    };
  }, [treePages, leftPage, chapterLeft, skillSpread, materials.edge]);
  useEffect(() => () => {
    pageMaterials.skillLeft.dispose();
    pageMaterials.skillRight.dispose();
  }, [pageMaterials]);

  // The skill's pages are rewritten whenever what they say, or the control
  // under the pointer, changes. Closing the skill keeps the last writing, so
  // the leaf still carries it as it turns back.
  const [hoveredSkillControl, setHoveredSkillControl] = useState<string | null>(null);
  const shownSkill = open ? skillPage : null;
  useEffect(() => {
    if (!skillSpread || !shownSkill) return;
    skillSpread.write(shownSkill, hoveredSkillControl);
    loadPicture(shownSkill.image, () => skillSpread.write(shownSkill, hoveredSkillControl));
  }, [skillSpread, shownSkill, hoveredSkillControl]);

  /** How far over the leaf is, 0..1 linear in time; the leaf eases its own motion. */
  const leaf = useRef(0);
  /**
   * How far the book has riffled from the class's chapter (0) to the
   * subclass's (1), and where each leaf of the riffle is: its own turn, and
   * how high it lies on the others.
   */
  const riffle = useRef(0);
  const riffling = useRef(false);
  const riffleTurns = useMemo(() => Array.from({ length: RIFFLE_LEAVES }, () => ({ current: 0 })), []);
  const riffleStacks = useMemo(
    () => Array.from({ length: RIFFLE_LEAVES }, (_, i) => ({ current: (RIFFLE_LEAVES - 1 - i) * RIFFLE_STACK })),
    [],
  );
  const rightMesh = useRef<THREE.Mesh>(null);
  const leftMesh = useRef<THREE.Mesh>(null);
  const treeLight = useRef<THREE.Group>(null);
  useFrame((_, delta) => {
    // The pages under the leaf are chosen on the value the leaf itself drew
    // with this frame, and only then is the turn moved on. The leaf, a child,
    // runs its frame before this one; swapping on the new value instead left
    // one frame with the page changed and the leaf not yet (or no longer)
    // over it — a flash of the wrong page.
    //
    // Under a lifted leaf the right page is already the one being turned to;
    // the left page becomes it only once the last leaf has landed on it. The
    // same rule holds for the riffle between chapters and for a skill's leaf.
    const c = riffle.current;
    const baseRight = c > 0 ? pageMaterials.chapterRightPages : pageMaterials.rightPages;
    const baseLeft = c >= 1 ? pageMaterials.chapterLeftPages : pageMaterials.leftPages;
    const right = leaf.current > 0 ? pageMaterials.skillRightPages : baseRight;
    const left = leaf.current >= 1 ? pageMaterials.skillLeftPages : baseLeft;
    if (rightMesh.current && rightMesh.current.material !== right) rightMesh.current.material = right;
    if (leftMesh.current && leftMesh.current.material !== left) leftMesh.current.material = left;
    // The tree's marks belong to the tree page in view, and to none while pages turn.
    // Nor while fresh ink is still spreading over it: they would light up ahead of it.
    if (treeLight.current)
      treeLight.current.visible =
        leaf.current === 0 && (c === 0 || c === 1) && !treePages.cls.revealing && !treePages.chapter.revealing;

    if (open) {
      const target = shownSkill ? 1 : 0;
      leaf.current = THREE.MathUtils.clamp(leaf.current + ((target ? 1 : -1) * delta) / LEAF_SECONDS, 0, 1);
      riffle.current = THREE.MathUtils.clamp(riffle.current + ((inChapter ? 1 : -1) * delta) / RIFFLE_SECONDS, 0, 1);
    } else if (openness.current === 0) {
      // Shut: back to the start of the book, out of sight.
      leaf.current = 0;
      riffle.current = 0;
    } else {
      // Shutting: no page turns while the cover comes down. Whatever is in the
      // air drops to the nearer side at once, and the pages hold still until
      // the book is shut — turning them back under a closing cover left them
      // hanging in the air outside it.
      leaf.current = Math.round(leaf.current);
      riffle.current = Math.round(riffle.current);
    }

    // The riffle: each leaf sets off a little after the one before it. Going
    // forward the top leaf on the right is the first; coming back, the top
    // leaf on the left — the same order run backwards.
    const r = riffle.current;
    riffling.current = r > 0 && r < 1;
    const span = 1 - (RIFFLE_LEAVES - 1) * RIFFLE_STAGGER;
    for (let i = 0; i < RIFFLE_LEAVES; i++) {
      const turn = THREE.MathUtils.clamp((r - i * RIFFLE_STAGGER) / span, 0, 1);
      riffleTurns[i].current = turn;
      riffleStacks[i].current = THREE.MathUtils.lerp(RIFFLE_LEAVES - 1 - i, i, turn) * RIFFLE_STACK;
    }
  });

  // The node's page is rewritten whenever what it says, or the control under
  // the pointer, changes; skill pictures arriving later redraw it too.
  const [hoveredControl, setHoveredControl] = useState<string | null>(null);
  const shownPage = open ? nodePage : null;
  // The node's page is written in whichever chapter the book is open at; the
  // other chapter's left page goes back to its opening words.
  const activeWriter = inChapter ? chapterLeft?.writer ?? null : leftPage.writer;
  useEffect(() => {
    const idle = inChapter ? leftPage.writer : chapterLeft?.writer;
    idle?.setNode(null, null);
    if (!activeWriter) return;
    activeWriter.setNode(shownPage, hoveredControl);
    if (shownPage) loadPictures(shownPage, () => activeWriter.setNode(shownPage, hoveredControl));
  }, [leftPage, chapterLeft, activeWriter, inChapter, shownPage, hoveredControl]);
  useFrame((_, delta) => {
    leftPage.writer?.update(delta);
    chapterLeft?.writer.update(delta);
    treePages.cls.update();
    treePages.chapter.update();
  });

  // The two halves of the pages. The left one is the half that turns over on
  // the spine, so its page is drawn on what is its underside while shut.
  const blocks = useMemo(() => {
    const shape = { width: PAGE_WIDTH, depth: PAGE_DEPTH, height: halfBlock };
    return {
      right: createPageBlockGeometry({ ...shape, mirrored: false }),
      left: createPageBlockGeometry({ ...shape, mirrored: true }),
    };
  }, [halfBlock]);
  useEffect(
    () => () => {
      blocks.right.geometry.dispose();
      blocks.left.geometry.dispose();
    },
    [blocks],
  );

  const root = useRef<THREE.Group>(null);
  const hinge = useRef<THREE.Group>(null);
  const spine = useRef<THREE.Group>(null);
  const openness = useRef(0);
  const hovered = useRef(false);
  const lift = useRef(0);
  const progress = useRef<BookProgress>({ fastening: 0, cover: 0 });
  const [hoveredNode, setHoveredNode] = useState<SpreadNode | null>(null);


  useFrame((_, delta) => {
    const k = (openness.current = THREE.MathUtils.clamp(
      openness.current + ((open ? 1 : -1) * delta) / OPEN_SECONDS,
      0,
      1,
    ));
    const fastening = easeInOut(Math.min(1, k / FASTENING_SHARE));
    const coverK = easeInOut(THREE.MathUtils.clamp((k - FASTENING_SHARE) / (1 - FASTENING_SHARE), 0, 1));
    progress.current.fastening = fastening;
    progress.current.cover = coverK;

    if (hinge.current) hinge.current.rotation.z = coverK * Math.PI;
    // The spine folds away under the gutter; once the book lies open it would
    // only poke out past the pages, so it is put away.
    if (spine.current) {
      spine.current.rotation.z = (coverK * Math.PI) / 2;
      spine.current.visible = coverK < 0.5;
    }
    // The pages bow as the book falls open, and flatten again as it shuts.
    const bend = coverK * coverK;
    blocks.right.setBend(bend);
    blocks.left.setBend(bend);

    const g = root.current;
    if (g) {
      // A closed book is slid left by half its width so it still sits on its
      // spot; open, the spread is centred on the spine. Closed books also lie
      // a little askew, as books left on a table do.
      g.position.x = position[0] - (PAGE_WIDTH / 2) * (1 - coverK);
      // A shut book rises a little under the pointer, inviting a click.
      lift.current = THREE.MathUtils.damp(lift.current, hovered.current && !open ? HOVER_LIFT : 0, 8, delta);
      g.position.y = position[1] + lift.current;
      g.rotation.y = restYaw * (1 - coverK);
    }
  });

  const handleClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    if (e.delta > 8) return;
    onSelect();
  };
  const handleOver = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    hovered.current = true;
    if (!open) document.body.style.cursor = 'pointer';
  };
  const handleOut = () => {
    hovered.current = false;
    document.body.style.cursor = '';
  };

  /**
   * The node under the pointer on the open spread, if any. The page face is
   * group 0 of each half; its UVs run gutter -> fore-edge on the right page and
   * fore-edge -> gutter on the left, tail -> head up the page.
   */
  /** The tree on the page in view: the class's, the chapter's, or none while pages turn. */
  const spreadInView = () =>
    riffle.current === 0 ? spread : riffle.current === 1 && chapter ? chapter.spread : null;

  const nodeAt = (e: ThreeEvent<PointerEvent | MouseEvent>, side: 'left' | 'right'): SpreadNode | null => {
    const spread = spreadInView();
    if (!spread || !open || progress.current.cover < 0.98) return null;
    if (e.face?.materialIndex !== 0 || !e.uv) return null;
    const u = side === 'right' ? e.uv.x : e.uv.x - 1;
    const v = e.uv.y;
    let best: SpreadNode | null = null;
    let bestDistance = Infinity;
    for (const n of spread.nodes) {
      const d = Math.hypot((u - n.u) * SPREAD_PX.u, (v - n.v) * SPREAD_PX.v);
      if (d < nodeRadiusPx(n) + NODE_HIT_SLACK_PX && d < bestDistance) {
        best = n;
        bestDistance = d;
      }
    }
    return best;
  };
  // Same rule as the wheel: another class's nodes open read-only.
  const clickable = (n: SpreadNode) => spreadInView()?.foreign || n.state === 'available' || n.state === 'chosen';

  /** The control on the node's page under the pointer, if the page is written and the pointer is on it. */
  const controlAt = (e: ThreeEvent<PointerEvent | MouseEvent>, side: 'left' | 'right') => {
    const writer = activeWriter;
    const settled = riffle.current === 0 || riffle.current === 1;
    if (side !== 'left' || !settled || !writer?.readable || e.face?.materialIndex !== 0 || !e.uv) return null;
    // The left page's UVs run fore-edge -> gutter, tail -> head; the canvas runs left -> right, head -> tail.
    return regionAt(writer.regions, e.uv.x * PAGE_PX_W, (1 - e.uv.y) * PAGE_PX_H);
  };

  /** The control on the skill's spread under the pointer, once the leaf has turned. */
  const skillControlAt = (e: ThreeEvent<PointerEvent | MouseEvent>, side: 'left' | 'right') => {
    if (!skillSpread || leaf.current < 1 || e.face?.materialIndex !== 0 || !e.uv) return null;
    // Both pages' canvases run fore-edge/gutter left -> right as their UVs do, head -> tail downward.
    const regions = side === 'left' ? skillSpread.leftRegions : skillSpread.rightRegions;
    return skillRegionAt(regions, e.uv.x * PAGE_PX_W, (1 - e.uv.y) * PAGE_PX_H);
  };

  /** The way back to the class's chapter, written on the subclass chapter's first page while nothing covers it. */
  const backLinkAt = (e: ThreeEvent<PointerEvent | MouseEvent>, side: 'left' | 'right') => {
    if (side !== 'left' || !inChapter || riffle.current !== 1 || leaf.current !== 0 || shownPage) return false;
    if (e.face?.materialIndex !== 0 || !e.uv) return false;
    const x = e.uv.x * PAGE_PX_W;
    const y = (1 - e.uv.y) * PAGE_PX_H;
    const r = INTRO_BACK_REGION;
    return x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h;
  };

  const pageHandlers = (side: 'left' | 'right') => ({
    onPointerMove: (e: ThreeEvent<PointerEvent>) => {
      if (!open) return;
      if (backLinkAt(e, side)) {
        document.body.style.cursor = 'pointer';
        return;
      }
      if (leaf.current > 0) {
        const control = skillControlAt(e, side);
        const key = control ? skillActionKey(control.action) : null;
        if (key !== hoveredSkillControl) setHoveredSkillControl(key);
        document.body.style.cursor = control ? 'pointer' : '';
        return;
      }
      if (side === 'left') {
        const control = controlAt(e, side);
        const key = control ? actionKey(control.action) : null;
        if (key !== hoveredControl) setHoveredControl(key);
        document.body.style.cursor = control ? 'pointer' : '';
        return;
      }
      const n = nodeAt(e, side);
      if (n?.id !== hoveredNode?.id) setHoveredNode(n);
      document.body.style.cursor = n && clickable(n) ? 'pointer' : '';
    },
    onPointerLeave: () => {
      if (hoveredNode) setHoveredNode(null);
      if (side === 'left' && hoveredControl) setHoveredControl(null);
      if (hoveredSkillControl) setHoveredSkillControl(null);
    },
    onClick: (e: ThreeEvent<MouseEvent>) => {
      if (!open) return;
      // An open book's pages answer for themselves; the book is already chosen.
      e.stopPropagation();
      if (e.delta > 8) return;
      if (backLinkAt(e, side)) {
        onToggleChapter?.();
        return;
      }
      if (leaf.current > 0) {
        const control = skillControlAt(e, side);
        if (control) onSkillAction?.(control.action);
        return;
      }
      if (side === 'left') {
        const control = controlAt(e, side);
        if (control) onNodeAction?.(control.action);
        return;
      }
      const n = nodeAt(e, side);
      if (n && clickable(n)) onNodeClick?.(n.id);
    },
  });

  // Nothing stays highlighted on a book that has been shut, or on a page turned away.
  useEffect(() => {
    if (!open) setHoveredNode(null);
  }, [open]);
  useEffect(() => {
    if (!shownSkill) setHoveredSkillControl(null);
  }, [shownSkill]);

  const dressingProps = { frame, binding, progress, leather: materials.leather };
  const { Cover, Spine, Fastening, Extras } = dressing;

  return (
    <group ref={root} position={position} onClick={handleClick} onPointerOver={handleOver} onPointerOut={handleOut}>
      {/* Back board */}
      <mesh position={[boardWidth / 2, cover / 2, 0]} material={materials.leather} castShadow receiveShadow>
        <boxGeometry args={[boardWidth, cover, boardDepth]} />
      </mesh>

      {/* Lower half of the pages, the right-hand page on top */}
      <mesh
        ref={rightMesh}
        position={[0, cover, 0]}
        geometry={blocks.right.geometry}
        material={pageMaterials.rightPages}
        castShadow
        receiveShadow
        {...pageHandlers('right')}
      />

      {/* Spine: stands up the side when closed, folds under the gutter when open */}
      <group ref={spine} position={[0, hingeY, 0]}>
        <mesh position={[-cover / 2, 0, 0]} material={materials.leather}>
          <boxGeometry args={[cover, closedHeight, boardDepth]} />
        </mesh>
        {Spine && <Spine {...dressingProps} />}
      </group>

      {/* Front board and the upper half of the pages, turning on the spine */}
      <group ref={hinge} position={[0, hingeY, 0]}>
        {/* Mirrored top to bottom, so its page faces down while shut and up once turned */}
        <mesh
          ref={leftMesh}
          position={[0, halfBlock, 0]}
          scale={[1, -1, 1]}
          geometry={blocks.left.geometry}
          material={pageMaterials.leftPages}
          castShadow
          receiveShadow
          {...pageHandlers('left')}
        />
        <mesh position={[boardWidth / 2, halfBlock + cover / 2, 0]} material={materials.frontCover} castShadow>
          <boxGeometry args={[boardWidth, cover, boardDepth]} />
        </mesh>
        {Cover && (
          <group position={[0, halfBlock + cover, 0]}>
            <Cover {...dressingProps} />
          </group>
        )}
      </group>

      {Fastening && <Fastening {...dressingProps} />}
      {Extras && <Extras {...dressingProps} />}
      {spread && (
        <group ref={treeLight}>
          <SpreadOverlay
            key={inChapter ? 'chapter' : 'class'}
            spread={inChapter && chapter ? chapter.spread : spread}
            frame={frame}
            progress={progress}
            hoveredId={hoveredNode?.id ?? null}
          />
        </group>
      )}
      {chapter && chapterLeft && (
        <>
          <ChapterRibbon
            frame={frame}
            colour={CLASS_INK[classId] ?? '#7a1a12'}
            label={chapter.title}
            onToggle={() => onToggleChapter?.()}
          />
          {riffleTurns.map((turn, i) => (
            <PageLeaf
              key={i}
              width={PAGE_WIDTH}
              depth={PAGE_DEPTH}
              hingeY={hingeY}
              turn={turn}
              shown={riffling}
              stack={riffleStacks[i]}
              // The first leaf carries the class's tree away, the last brings
              // the chapter's opening page; between them, old notes.
              front={i === 0 ? rightPage : riffleLeaves[i].front}
              back={i === RIFFLE_LEAVES - 1 ? chapterLeft.opening : riffleLeaves[i].back}
            />
          ))}
        </>
      )}
      {skillSpread && (
        <PageLeaf
          width={PAGE_WIDTH}
          depth={PAGE_DEPTH}
          hingeY={hingeY}
          turn={leaf}
          front={inChapter && chapterRight ? chapterRight : rightPage}
          back={skillSpread.leftTexture}
        />
      )}
    </group>
  );
};

export default Book;
