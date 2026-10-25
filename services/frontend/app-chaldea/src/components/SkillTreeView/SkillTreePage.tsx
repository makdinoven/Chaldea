import { lazy, Suspense, useEffect, useCallback, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import axios from 'axios';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchClassTree,
  fetchTreeProgress,
  fetchSubclassTrees,
} from '../../redux/actions/playerTreeActions';
import {
  setSelectedNodeId,
  clearPlayerTree,
} from '../../redux/slices/playerTreeSlice';
import useMediaQuery from '../../hooks/useMediaQuery';
import PlayerTreeCanvas, { type TreeView } from './PlayerTreeCanvas';
import { HeaderToggle, useFullscreenPage } from '../CommonComponents/Fullscreen/fullscreen';
import NodeDetailPanel from './NodeDetailPanel';
import useNodePage from './useNodePage';
import useSkillPage from './useSkillPage';
import useCharacterDossier from './useCharacterDossier';
import type { ShelfBook } from './Books3D/BookTableScene';
import type {
  FullClassTreeResponse,
  CharacterTreeProgressResponse,
} from './types';
import { ArrowLeft } from 'react-feather';
import { isWebGLAvailable } from '../pages/BattlePage/Arena3D/webgl';

// three.js is heavy and only the books need it, so it loads on demand.
const BookTableScene = lazy(() => import('./Books3D/BookTableScene'));

type TreeViewMode = 'wheel' | 'books';

/** Where the player's choice of view is remembered, per browser. */
const VIEW_MODE_KEY = 'skillTree.viewMode';

/** Screens at least this wide count as a computer: the same line the page draws for the whole wheel. */
const WIDE_SCREEN_QUERY = '(min-width: 768px)';

/**
 * The player's own choice if they have made one; otherwise the books on a
 * computer and the wheel on a phone.
 */
const readViewMode = (): TreeViewMode => {
  let saved: string | null = null;
  try {
    saved = localStorage.getItem(VIEW_MODE_KEY);
  } catch {
    // Nothing remembered; fall through to the default for this screen.
  }
  if (saved === 'books' || saved === 'wheel') return saved;
  return window.matchMedia(WIDE_SCREEN_QUERY).matches ? 'books' : 'wheel';
};

/** DB class ids, in the order they are laid out around the combined wheel. */
const CLASS_IDS = [1, 2, 3] as const;

const CLASS_LABELS: Record<number, string> = {
  1: 'Воин',
  2: 'Плут',
  3: 'Маг',
};

/** Accent per class, matching the node colours in PlayerNodeComponent. */
const CLASS_ACCENTS: Record<number, string> = {
  1: '#f87171',
  2: '#34d399',
  3: '#38bdf8',
};

const SkillTreePage = () => {
  const dispatch = useAppDispatch();
  const user = useAppSelector((state) => state.user);
  const character = user.character;
  const authInitialized = user.authInitialized;
  const characterId = character?.id ?? null;
  const classId = (character as Record<string, unknown>)?.id_class as number | undefined;

  // The combined wheel needs room to breathe; on a phone it would be unreadable,
  // so small screens keep the one-tree-at-a-time view plus a class switcher.
  const isWideScreen = useMediaQuery(WIDE_SCREEN_QUERY);

  const { tree: classTree, progress: classProgress, selectedNodeId, loading, error, subclassTrees } = useAppSelector(
    (state) => state.playerTree
  );

  // Other classes' trees — reference only, never choosable.
  const [otherTrees, setOtherTrees] = useState<FullClassTreeResponse[]>([]);
  // Which class the narrow-screen view is showing.
  const [browsedClassId, setBrowsedClassId] = useState<number | null>(null);

  // Subclass tree state
  const [subclassTree, setSubclassTree] = useState<FullClassTreeResponse | null>(null);
  const [subclassProgress, setSubclassProgress] = useState<CharacterTreeProgressResponse | null>(null);
  const [viewingSubclass, setViewingSubclass] = useState(false);
  const [subclassLoading, setSubclassLoading] = useState(false);

  // In the books, the chosen subclass is a later chapter of the class's book:
  // its tree and the player's progress in it, loaded as soon as one is chosen
  // so its ribbon is there to follow; and whether the book lies open at it.
  const [bookChapter, setBookChapter] = useState<{
    tree: FullClassTreeResponse;
    progress: CharacterTreeProgressResponse | null;
  } | null>(null);
  const [atChapter, setAtChapter] = useState(false);

  // The 3D books are a prototype next to the 2D wheel, and need WebGL. A
  // subclass opens there as its own slim book; on the wheel, as a wheel.
  const webglAvailable = useMemo(() => isWebGLAvailable(), []);
  const [viewMode, setViewMode] = useState<TreeViewMode>(readViewMode);
  const showsBooks = webglAvailable && viewMode === 'books';
  const booksLoading = (
    <div className="flex h-full items-center justify-center">
      <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
    </div>
  );
  // The player's passport, laid on the table beside their book.
  const dossier = useCharacterDossier(characterId, showsBooks);
  const handleViewMode = useCallback((mode: TreeViewMode) => {
    setViewMode(mode);
    try {
      localStorage.setItem(VIEW_MODE_KEY, mode);
    } catch {
      // Not remembered across visits; the switch itself still works.
    }
  }, []);

  // Load class tree on mount
  useEffect(() => {
    if (!classId) return;
    dispatch(fetchClassTree(classId));
    setBrowsedClassId(classId);
    return () => {
      dispatch(clearPlayerTree());
    };
  }, [dispatch, classId]);

  // Load the other classes' trees for reference. A class without a tree yet
  // simply drops out — that is not an error worth showing the player.
  useEffect(() => {
    if (!classId) return;
    let cancelled = false;
    const ids = CLASS_IDS.filter((id) => id !== classId);
    Promise.all(
      ids.map((id) =>
        axios
          .get<FullClassTreeResponse>(`/skills/class_trees/by_class/${id}`)
          .then((res) => res.data)
          .catch(() => null),
      ),
    ).then((results) => {
      if (cancelled) return;
      setOtherTrees(results.filter((t): t is FullClassTreeResponse => t !== null));
    });
    return () => {
      cancelled = true;
    };
  }, [classId]);

  // Load progress + subclass trees after class tree loaded
  useEffect(() => {
    if (!classTree || !characterId) return;
    dispatch(fetchTreeProgress({ treeId: classTree.id, characterId }));
    dispatch(fetchSubclassTrees(classTree.id));
  }, [dispatch, classTree?.id, characterId]);

  useEffect(() => {
    if (error) toast.error(error);
  }, [error]);

  /** Every class tree we have, ordered by class id so sectors stay stable. */
  const allTrees = useMemo(() => {
    // Right after switching characters the store can still hold the previous
    // character's class tree while the others are already the new set; never
    // let one class appear twice.
    const trees = classTree
      ? [classTree, ...otherTrees.filter((t) => t.class_id !== classTree.class_id)]
      : otherTrees;
    return [...trees].sort((a, b) => a.class_id - b.class_id);
  }, [classTree, otherTrees]);

  const views: TreeView[] = useMemo(() => {
    if (viewingSubclass && subclassTree) {
      return [{ tree: subclassTree, progress: subclassProgress, readOnly: false }];
    }
    const asView = (tree: FullClassTreeResponse): TreeView => ({
      tree,
      progress: tree.class_id === classId ? classProgress : null,
      readOnly: tree.class_id !== classId,
    });
    if (isWideScreen) return allTrees.map(asView);
    const browsed = allTrees.find((t) => t.class_id === browsedClassId) ?? allTrees[0];
    return browsed ? [asView(browsed)] : [];
  }, [
    viewingSubclass,
    subclassTree,
    subclassProgress,
    isWideScreen,
    allTrees,
    browsedClassId,
    classId,
    classProgress,
  ]);

  // The books always hold every class's tree, whatever the screen size; only
  // the player's own carries progress.
  const shelf = useMemo(
    () =>
      allTrees.map((tree) => ({
        classId: tree.class_id,
        title: CLASS_LABELS[tree.class_id] ?? tree.name,
        own: tree.class_id === classId,
        tree,
        progress: tree.class_id === classId ? classProgress : null,
      })),
    [allTrees, classId, classProgress],
  );

  const handleNodeClick = useCallback(
    (nodeId: number) => {
      dispatch(setSelectedNodeId(nodeId));
    },
    [dispatch]
  );

  const handleClosePanel = useCallback(() => {
    dispatch(setSelectedNodeId(null));
  }, [dispatch]);

  const refreshChapterProgress = useCallback(
    (treeId: number) => {
      if (!characterId) return;
      axios
        .get<CharacterTreeProgressResponse>(`/skills/class_trees/${treeId}/progress/${characterId}`)
        .then((res) => setBookChapter((ch) => (ch && ch.tree.id === treeId ? { ...ch, progress: res.data } : ch)))
        .catch(() => toast.error('Ошибка обновления прогресса подкласса'));
    },
    [characterId],
  );

  const handleRefreshProgress = useCallback(() => {
    if (showsBooks) {
      // A choice in either chapter can change what the other shows.
      if (classTree && characterId) dispatch(fetchTreeProgress({ treeId: classTree.id, characterId }));
      if (bookChapter) refreshChapterProgress(bookChapter.tree.id);
      return;
    }
    if (viewingSubclass && subclassTree && characterId) {
      setSubclassLoading(true);
      axios
        .get(`/skills/class_trees/${subclassTree.id}/progress/${characterId}`)
        .then((res) => setSubclassProgress(res.data))
        .catch(() => toast.error('Ошибка обновления прогресса подкласса'))
        .finally(() => setSubclassLoading(false));
    } else if (classTree && characterId) {
      dispatch(fetchTreeProgress({ treeId: classTree.id, characterId }));
    }
  }, [dispatch, showsBooks, bookChapter, refreshChapterProgress, viewingSubclass, subclassTree, classTree, characterId]);

  const handleNavigateToSubclass = useCallback(
    async (subclassNodeId: number) => {
      if (showsBooks && bookChapter) {
        setAtChapter(true);
        dispatch(setSelectedNodeId(null));
        return;
      }
      if (!classTree || !characterId || subclassTrees.length === 0) {
        toast.error('Деревья подклассов ещё не созданы');
        return;
      }
      const chosenNode = classTree.nodes.find((n) => n.id === subclassNodeId);
      const subclassKey = chosenNode?.subclass_key ?? null;
      if (!subclassKey) {
        toast.error('У этого узла не задан подкласс');
        return;
      }
      // Deterministic link: node.subclass_key === tree.subclass_key. No name guessing.
      const matchedTree = subclassTrees.find((st) => st.subclass_key === subclassKey);
      if (!matchedTree) {
        toast.error('Дерево этого подкласса ещё не создано');
        return;
      }
      setSubclassLoading(true);
      try {
        const [treeRes, progressRes] = await Promise.all([
          axios.get(`/skills/admin/class_trees/${matchedTree.id}/full`),
          axios.get(`/skills/class_trees/${matchedTree.id}/progress/${characterId}`).catch(() => ({ data: null })),
        ]);
        setSubclassTree(treeRes.data);
        setSubclassProgress(progressRes.data);
        setViewingSubclass(true);
        dispatch(setSelectedNodeId(null));
      } catch {
        toast.error('Ошибка загрузки дерева подкласса');
      } finally {
        setSubclassLoading(false);
      }
    },
    [showsBooks, bookChapter, classTree, subclassTrees, characterId, dispatch]
  );

  const handleBackToClassTree = useCallback(() => {
    setViewingSubclass(false);
    setSubclassTree(null);
    setSubclassProgress(null);
    dispatch(setSelectedNodeId(null));
  }, [dispatch]);

  const handleBrowseClass = useCallback(
    (id: number) => {
      setBrowsedClassId(id);
      dispatch(setSelectedNodeId(null));
    },
    [dispatch]
  );

  // In the books, the opened node is written onto the left-hand page of its book.
  // The subclass chosen on the class's tree, if its own tree exists yet.
  const chosenSubclassTreeId = useMemo(() => {
    if (!classTree || !classProgress) return null;
    const chosen = new Set(classProgress.chosen_nodes.map((c) => c.node_id));
    const key = classTree.nodes.find((n) => n.node_type === 'subclass_choice' && chosen.has(n.id))?.subclass_key;
    return key ? subclassTrees.find((st) => st.subclass_key === key)?.id ?? null : null;
  }, [classTree, classProgress, subclassTrees]);

  useEffect(() => {
    if (!showsBooks || chosenSubclassTreeId === null || !characterId) {
      setBookChapter(null);
      setAtChapter(false);
      return;
    }
    let cancelled = false;
    Promise.all([
      axios.get<FullClassTreeResponse>(`/skills/admin/class_trees/${chosenSubclassTreeId}/full`),
      axios
        .get<CharacterTreeProgressResponse>(`/skills/class_trees/${chosenSubclassTreeId}/progress/${characterId}`)
        .catch(() => ({ data: null })),
    ])
      .then(([treeRes, progressRes]) => {
        if (!cancelled) setBookChapter({ tree: treeRes.data, progress: progressRes.data });
      })
      .catch(() => {
        if (!cancelled) toast.error('Ошибка загрузки дерева подкласса');
      });
    return () => {
      cancelled = true;
    };
  }, [showsBooks, chosenSubclassTreeId, characterId]);

  // Every book, the player's own carrying its subclass chapter once there is one.
  const bookShelf = useMemo(
    (): ShelfBook[] =>
      shelf.map((b) => {
        if (!b.own || !bookChapter) return b;
        const title = bookChapter.tree.subclass_name ?? bookChapter.tree.name;
        return {
          ...b,
          chapter: {
            title,
            tree: bookChapter.tree,
            progress: bookChapter.progress,
            intro: [
              bookChapter.tree.description ||
                `Здесь путь ${title} продолжается с того места, где кончилось древо класса.`,
            ],
          },
        };
      }),
    [shelf, bookChapter],
  );

  const bookNode = useMemo(() => {
    if (!showsBooks || selectedNodeId === null) return null;
    const trees = bookShelf.flatMap((b) => [
      { tree: b.tree, progress: b.progress, own: b.own },
      ...(b.chapter ? [{ tree: b.chapter.tree, progress: b.chapter.progress, own: true }] : []),
    ]);
    for (const book of trees) {
      const node = book.tree.nodes.find((n) => n.id === selectedNodeId);
      if (node) return { node, book };
    }
    return null;
  }, [showsBooks, selectedNodeId, bookShelf]);
  // Upgrading a skill from its node's page turns the book to the skill's own spread.
  const [skillPageId, setSkillPageId] = useState<number | null>(null);
  const closeSkillPage = useCallback(() => setSkillPageId(null), []);
  const skillPage = useSkillPage({
    skillId: showsBooks ? skillPageId : null,
    characterId,
    onBack: closeSkillPage,
    onRefresh: handleRefreshProgress,
  });
  /** Leaving a book, or shutting it, puts away whatever was open in it, and its place in it. */
  const handleLeaveBook = useCallback(() => {
    setSkillPageId(null);
    setAtChapter(false);
    handleClosePanel();
  }, [handleClosePanel]);
  /** The chapter ribbon: turn to the subclass chapter, or back to the class's. */
  const handleToggleChapter = useCallback(() => {
    setSkillPageId(null);
    handleClosePanel();
    setAtChapter((v) => !v);
  }, [handleClosePanel]);
  const handleLeaveSubclass = useCallback(() => {
    setSkillPageId(null);
    handleBackToClassTree();
  }, [handleBackToClassTree]);

  const nodePage = useNodePage({
    node: bookNode?.node ?? null,
    tree: bookNode?.book.tree ?? null,
    progress: bookNode?.book.progress ?? null,
    readOnly: bookNode ? !bookNode.book.own : true,
    characterId,
    onClose: handleClosePanel,
    onRefresh: handleRefreshProgress,
    onNavigateToSubclass:
      bookNode?.book.own && bookNode.node.node_type === 'subclass_choice' ? handleNavigateToSubclass : undefined,
    onUpgradeSkill: setSkillPageId,
  });

  // The 3D books take the whole screen under the site header — once they are on the table.
  const booksOnTable =
    showsBooks && authInitialized && user.status !== 'loading' && !!user.id && !!characterId && !!classId && views.length > 0;
  const { top: headerTop, headerHidden, toggleHeader } = useFullscreenPage(booksOnTable);

  // Auth loading
  if (!authInitialized || user.status === 'loading') {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Not logged in
  if (!user.id) {
    return (
      <div className="flex flex-col items-center justify-center py-32">
        <h2 className="gold-text text-3xl font-medium uppercase mb-4">Навыки</h2>
        <p className="text-white/50 text-lg">Войдите в аккаунт, чтобы просматривать навыки.</p>
      </div>
    );
  }

  // No character
  if (!characterId || !classId) {
    return (
      <div className="flex flex-col items-center justify-center py-32">
        <h2 className="gold-text text-3xl font-medium uppercase mb-4">Навыки</h2>
        <p className="text-white/50 text-lg">Создайте персонажа, чтобы открыть дерево навыков.</p>
      </div>
    );
  }

  // Loading tree
  if ((loading || subclassLoading) && views.length === 0) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // No tree
  if (!loading && views.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-32">
        <h2 className="gold-text text-3xl font-medium uppercase mb-4">Навыки</h2>
        <p className="text-white/50 text-lg">Дерево навыков в разработке</p>
      </div>
    );
  }

  if (views.length === 0) return null;

  const selectable: TreeView[] = showsBooks
    ? shelf.map((b) => ({ tree: b.tree, progress: b.progress, readOnly: !b.own }))
    : views;
  const selected = selectedNodeId
    ? selectable
        .map((view) => {
          const node = view.tree.nodes.find((n) => n.id === selectedNodeId);
          return node ? { node, view } : null;
        })
        .find((hit) => hit !== null) ?? null
    : null;

  const showsWholeWheel = isWideScreen && !viewingSubclass && views.length > 1;
  // The books lie on a table, so they want a wide frame rather than a round one.
  const roundFrame = showsWholeWheel && !showsBooks;
  const headerTree = viewingSubclass ? subclassTree : views[0]?.tree ?? null;

  return (
    // On a phone the books take the full width: the page's container padding is given back to them.
    <div className={`w-full py-4 ${showsBooks ? '' : 'px-2 md:px-6'}`}>
      <div className="w-full">
        {/* Class switcher — narrow screens only, where one tree is shown at a time */}
        {!viewingSubclass && !isWideScreen && !showsBooks && (
          <div className="flex gap-2 mb-3">
            {allTrees.map((t) => {
              const active = t.class_id === (browsedClassId ?? classId);
              const own = t.class_id === classId;
              return (
                <button
                  key={t.class_id}
                  onClick={() => handleBrowseClass(t.class_id)}
                  className={`flex-1 rounded-card px-3 py-2 text-sm font-medium uppercase tracking-wide transition-colors duration-200 ${
                    active ? 'text-white' : 'text-white/40 hover:text-white/70'
                  }`}
                  style={{
                    background: active ? `${CLASS_ACCENTS[t.class_id]}22` : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${active ? `${CLASS_ACCENTS[t.class_id]}66` : 'transparent'}`,
                  }}
                >
                  {CLASS_LABELS[t.class_id] ?? t.name}
                  {!own && <span className="block text-[9px] normal-case text-white/40">просмотр</span>}
                </button>
              );
            })}
          </div>
        )}

        {/*
          The wheel gets a round frame instead of the usual panel: a circle of
          content inside a square box left obvious dead corners. The frame is a
          square that never exceeds 80vh, so the circle stays a circle, and the
          canvas is clipped to it while the overlays below sit outside the clip.
        */}
        {showsBooks && (
          <>
            {/* The whole screen is the books' room: no page showing round the site header. */}
            <div className="fixed inset-0 z-0 bg-[#12121e]" />
            <HeaderToggle top={headerTop} hidden={headerHidden} onToggle={toggleHeader} />
          </>
        )}
        <div
          className={
            showsBooks
              ? 'fixed inset-x-0 bottom-0 z-0'
              : `relative ${roundFrame ? 'w-full max-w-[80vh] aspect-square mx-auto' : 'w-full h-[65vh] md:h-[80vh]'}`
          }
          style={showsBooks ? { top: headerTop } : undefined}
        >
          <div
            className={`absolute inset-0 overflow-hidden bg-[#12121e] ${
              showsBooks ? '' : roundFrame ? 'rounded-full' : 'rounded-card'
            }`}
          >
            {showsBooks ? (
              <Suspense fallback={booksLoading}>
                {/* The table is laid only once the player's own book is on it,
                    so the view opens on their class rather than on whichever
                    book happened to arrive first. */}
                {!bookShelf.some((b) => b.own) ? booksLoading : (
                <BookTableScene
                  books={bookShelf}
                  initialClassId={classId}
                  onNodeClick={handleNodeClick}
                  nodePage={nodePage.model}
                  onNodeAction={nodePage.onAction}
                  skillPage={skillPage.model}
                  onSkillAction={skillPage.onAction}
                  onLeaveBook={handleLeaveBook}
                  atChapter={atChapter}
                  onToggleChapter={handleToggleChapter}
                  passport={dossier.passport}
                  currentGameYear={dossier.currentGameYear}
                />
                )}
              </Suspense>
            ) : (
              <PlayerTreeCanvas views={views} onNodeClick={handleNodeClick} />
            )}
          </div>

          {/* View switch: flat wheel or the 3D books */}
          {webglAvailable && (
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-10 flex rounded-lg bg-black/50 backdrop-blur-sm p-1 gap-1">
              {(
                [
                  ['wheel', 'Схема'],
                  ['books', 'Книги'],
                ] as const
              ).map(([mode, label]) => (
                <button
                  key={mode}
                  onClick={() => handleViewMode(mode)}
                  className={`rounded-md px-3 py-1.5 text-xs uppercase tracking-wide transition-colors duration-200 ${
                    viewMode === mode ? 'bg-white/10 text-gold' : 'text-white/50 hover:text-white'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          )}

          {/* Header */}
          <div className="absolute top-3 left-4 z-10 flex items-center gap-3">
            {/* The books have their own way back, at the foot of the table */}
            {viewingSubclass && !showsBooks && (
              <button
                onClick={handleLeaveSubclass}
                className="flex items-center gap-1.5 bg-black/50 backdrop-blur-sm rounded-lg px-3 py-1.5 text-white/70 hover:text-white transition-colors duration-200 text-sm"
              >
                <ArrowLeft size={14} />
                Назад
              </button>
            )}
            <div className="bg-black/40 backdrop-blur-sm rounded-lg px-3 py-1.5">
              <h3 className="gold-text text-sm font-medium uppercase">
                {showsWholeWheel ? 'Древо навыков' : headerTree?.name}
                {viewingSubclass && headerTree?.subclass_name && (
                  <span className="text-white/40 ml-1.5 font-normal normal-case text-xs">
                    — {headerTree.subclass_name}
                  </span>
                )}
              </h3>
              {classProgress && (
                <p className="text-white/40 text-[10px] mt-0.5">
                  Уровень {classProgress.character_level} &middot; Опыт: {classProgress.active_experience}
                </p>
              )}
            </div>
          </div>

          {/* Sector legend — only meaningful when all three classes are on screen */}
          {showsWholeWheel && !showsBooks && (
            <div className="absolute top-3 right-4 z-10 bg-black/40 backdrop-blur-sm rounded-lg px-3 py-2 flex flex-col gap-1">
              {views.map((view) => (
                <div key={view.tree.class_id} className="flex items-center gap-2">
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{
                      background: CLASS_ACCENTS[view.tree.class_id] ?? '#fff',
                      opacity: view.readOnly ? 0.4 : 1,
                    }}
                  />
                  <span className={`text-[10px] uppercase tracking-wide ${view.readOnly ? 'text-white/35' : 'text-white'}`}>
                    {CLASS_LABELS[view.tree.class_id] ?? view.tree.name}
                  </span>
                  {!view.readOnly && (
                    <span className="text-gold text-[9px] normal-case">ваш класс</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Windows opened from a node's page in a book */}
          {showsBooks && nodePage.modals}

          {/* Node detail modal — the books write a node's page into the book instead */}
          <AnimatePresence>
            {selected && !showsBooks && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                /*
                  No wash behind the panel: this layer is a square, the wheel's
                  frame is a circle, and a darkened square around a round tree
                  is all you could see of it. It stays only to catch a click
                  outside the panel and close it.
                */
                className="absolute inset-0 z-20 flex items-center justify-center"
                onClick={handleClosePanel}
              >
                <motion.div
                  initial={{ opacity: 0, scale: 0.9, y: 20 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.9, y: 20 }}
                  transition={{ duration: 0.25, ease: 'easeOut' }}
                  className="w-[90%] max-w-[420px] max-h-[70vh] overflow-y-auto gold-scrollbar"
                  onClick={(e) => e.stopPropagation()}
                >
                  <NodeDetailPanel
                    node={selected.node}
                    tree={selected.view.tree}
                    progress={selected.view.progress}
                    characterId={characterId}
                    readOnly={selected.view.readOnly}
                    onClose={handleClosePanel}
                    onRefresh={handleRefreshProgress}
                    onNavigateToSubclass={
                      !selected.view.readOnly && selected.node.node_type === 'subclass_choice'
                        ? handleNavigateToSubclass
                        : undefined
                    }
                  />
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
};

export default SkillTreePage;
