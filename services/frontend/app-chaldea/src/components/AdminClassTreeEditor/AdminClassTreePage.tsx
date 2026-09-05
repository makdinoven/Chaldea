import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchClassTrees,
  fetchFullClassTree,
  saveFullClassTree,
  createClassTree,
  deleteClassTree,
} from '../../redux/actions/classTreeAdminActions';
import { clearSelectedTree } from '../../redux/slices/classTreeAdminSlice';
import { useClassTreeEditor } from './hooks/useClassTreeEditor';
import { useCombinedTreeEditor } from './hooks/useCombinedTreeEditor';
import { autoLayoutRings, autoAlignRows } from './utils/ringLayout';
import ClassTreeCanvas from './ClassTreeCanvas';
import CombinedTreeCanvas from './CombinedTreeCanvas';
import WheelToolbar, { type WheelToolbarTree } from './WheelToolbar';
import WheelLayoutPanel from './WheelLayoutPanel';
import {
  DEFAULT_WHEEL_LAYOUT,
  type WheelLayoutConfig,
} from '../SkillTreeView/utils/combineTrees';
import TreeNodeInspector from './TreeNodeInspector';
import TreeToolbar from './TreeToolbar';
import type { FullClassTreeResponse } from './types';
import {
  CLASS_OPTIONS,
  TREE_TYPE_OPTIONS,
  type ClassSkillTreeRead,
  type ClassSkillTreeCreate,
  type Subclass,
} from './types';
import { Plus, Trash2, ChevronRight, Search } from 'react-feather';

/** Accent per class, matching the node colours in the player wheel. */
const CLASS_ACCENTS: Record<number, string> = {
  1: '#f87171',
  2: '#34d399',
  3: '#38bdf8',
};

type EditorMode = 'wheel' | 'single';

/**
 * Tuning the wheel's shape is a per-author experiment, so it lives in this
 * browser only. Players get DEFAULT_WHEEL_LAYOUT until numbers are committed.
 */
const WHEEL_LAYOUT_STORAGE_KEY = 'chaldea.admin.wheelLayout';

const readStoredLayout = (): WheelLayoutConfig => {
  try {
    const raw = localStorage.getItem(WHEEL_LAYOUT_STORAGE_KEY);
    if (!raw) return DEFAULT_WHEEL_LAYOUT;
    return { ...DEFAULT_WHEEL_LAYOUT, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_WHEEL_LAYOUT;
  }
};

const AdminClassTreePage = () => {
  const dispatch = useAppDispatch();
  const { treeList, selectedFullTree, status, updateStatus } = useAppSelector(
    (state) => state.classTreeAdmin
  );

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [newTree, setNewTree] = useState<ClassSkillTreeCreate>({
    class_id: 1,
    name: '',
    tree_type: 'class',
    parent_tree_id: null,
    subclass_name: null,
  });

  const [allSubclasses, setAllSubclasses] = useState<Subclass[]>([]);

  // Combined wheel: every class tree at once, laid out as the players see it.
  const [mode, setMode] = useState<EditorMode>('wheel');
  const [wheelTrees, setWheelTrees] = useState<FullClassTreeResponse[]>([]);
  const [wheelLoading, setWheelLoading] = useState(false);
  const [wheelSaving, setWheelSaving] = useState(false);

  const [wheelLayout, setWheelLayout] = useState<WheelLayoutConfig>(readStoredLayout);

  useEffect(() => {
    try {
      localStorage.setItem(WHEEL_LAYOUT_STORAGE_KEY, JSON.stringify(wheelLayout));
    } catch {
      // A browser with site data blocked just loses the tuning between visits.
    }
  }, [wheelLayout]);

  const editor = useClassTreeEditor(selectedFullTree);
  const wheel = useCombinedTreeEditor(wheelTrees, wheelLayout);

  useEffect(() => {
    dispatch(fetchClassTrees());
  }, [dispatch]);

  /** Class trees only — subclass trees are not part of the wheel. */
  const classTreeIds = useMemo(
    () =>
      treeList
        .filter((t) => t.tree_type === 'class')
        .sort((a, b) => a.class_id - b.class_id)
        .map((t) => t.id),
    [treeList],
  );

  const loadWheelTrees = useCallback(async () => {
    if (classTreeIds.length === 0) {
      setWheelTrees([]);
      return;
    }
    setWheelLoading(true);
    try {
      const results = await Promise.all(
        classTreeIds.map((id) =>
          axios
            .get<FullClassTreeResponse>(`/skills/admin/class_trees/${id}/full`)
            .then((res) => res.data),
        ),
      );
      setWheelTrees(results);
    } catch {
      toast.error('Не удалось загрузить деревья классов');
    } finally {
      setWheelLoading(false);
    }
  }, [classTreeIds]);

  useEffect(() => {
    if (mode === 'wheel') loadWheelTrees();
  }, [mode, loadWheelTrees]);

  // Hardcoded subclass registry (skills-service) — drives node + create-form dropdowns.
  useEffect(() => {
    axios
      .get<Subclass[]>('/skills/subclasses')
      .then((res) => setAllSubclasses(res.data))
      .catch(() => toast.error('Не удалось загрузить список подклассов'));
  }, []);

  const inspectorSubclasses = allSubclasses.filter(
    (s) => s.class_id === selectedFullTree?.class_id
  );
  const createFormSubclasses = allSubclasses.filter((s) => s.class_id === newTree.class_id);

  // Group trees by class
  const groupedTrees = CLASS_OPTIONS.reduce(
    (acc, cls) => {
      const classTrees = treeList.filter(
        (t) =>
          t.class_id === cls.value &&
          t.name.toLowerCase().includes(searchQuery.toLowerCase())
      );
      if (classTrees.length > 0) {
        acc.push({ classId: cls.value, className: cls.label, trees: classTrees });
      }
      return acc;
    },
    [] as { classId: number; className: string; trees: ClassSkillTreeRead[] }[]
  );

  const handleSelectTree = (treeId: number) => {
    setMode('single');
    dispatch(clearSelectedTree());
    dispatch(fetchFullClassTree(treeId));
  };

  const handleCreateTree = async () => {
    if (!newTree.name.trim()) {
      toast.error('Введите название дерева');
      return;
    }
    try {
      await dispatch(createClassTree(newTree)).unwrap();
      dispatch(fetchClassTrees());
      setShowCreateForm(false);
      setNewTree({ class_id: 1, name: '', tree_type: 'class', parent_tree_id: null, subclass_name: null });
      toast.success('Дерево создано');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Ошибка при создании дерева');
    }
  };

  const handleDeleteTree = async () => {
    if (!selectedFullTree) return;
    if (!window.confirm(`Удалить дерево "${selectedFullTree.name}"? Все узлы и связи будут удалены.`)) return;
    try {
      await dispatch(deleteClassTree(selectedFullTree.id)).unwrap();
      dispatch(clearSelectedTree());
      toast.success('Дерево удалено');
    } catch {
      toast.error('Ошибка при удалении дерева');
    }
  };

  const handleSave = async () => {
    const payload = editor.getApiPayload();
    if (!payload || !selectedFullTree) return;
    try {
      const result = await dispatch(
        saveFullClassTree({ treeId: selectedFullTree.id, data: payload })
      ).unwrap();
      if (result.temp_id_map && Object.keys(result.temp_id_map).length > 0) {
        editor.applyTempIdMap(result.temp_id_map);
      }
      editor.setIsDirty(false);
      dispatch(fetchFullClassTree(selectedFullTree.id));
      toast.success('Дерево сохранено');
    } catch {
      toast.error('Ошибка при сохранении дерева');
    }
  };

  const handleWheelSave = async () => {
    const payloads = wheel.getDirtyPayloads();
    if (payloads.length === 0) return;
    setWheelSaving(true);
    try {
      for (const { treeId, payload } of payloads) {
        await dispatch(saveFullClassTree({ treeId, data: payload })).unwrap();
      }
      wheel.clearDirty();
      // Re-read so temporary node ids are replaced by the real ones.
      await loadWheelTrees();
      toast.success(
        payloads.length === 1 ? 'Дерево сохранено' : `Сохранено деревьев: ${payloads.length}`,
      );
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Ошибка при сохранении деревьев');
    } finally {
      setWheelSaving(false);
    }
  };

  const wheelToolbarTrees: WheelToolbarTree[] = wheelTrees.map((tree) => ({
    treeId: tree.id,
    classId: tree.class_id,
    label: CLASS_OPTIONS.find((c) => c.value === tree.class_id)?.label ?? tree.name,
    accent: CLASS_ACCENTS[tree.class_id] ?? '#f0d95c',
    dirty: wheel.dirtyTreeIds.has(tree.id),
  }));

  const wheelInspectorSubclasses = allSubclasses.filter(
    (s) => s.class_id === (wheel.selectedNode?.data?.classId as number | undefined),
  );

  const handleAutoLayout = () => {
    const laid = autoLayoutRings(editor.nodes);
    editor.setNodes(laid);
    editor.setIsDirty(true);
  };

  const handleAlignRows = () => {
    const aligned = autoAlignRows(editor.nodes, editor.edges);
    editor.setNodes(aligned);
    editor.setIsDirty(true);
  };

  // Find parent tree options for subclass creation
  const parentTreeOptions = treeList.filter((t) => t.tree_type === 'class' && t.class_id === newTree.class_id);

  return (
    <div className="w-full h-[calc(100vh-80px)] flex flex-col">
      {/* Page title + view switch */}
      <div className="px-4 py-3 flex-shrink-0 flex flex-wrap items-center gap-4">
        <h1 className="gold-text text-2xl sm:text-3xl font-medium uppercase tracking-wider">
          Деревья классов
        </h1>
        <div className="flex gap-1 rounded-card bg-white/[0.04] p-1">
          {([
            ['wheel', 'Общий вид'],
            ['single', 'Отдельное дерево'],
          ] as const).map(([value, label]) => (
            <button
              key={value}
              onClick={() => setMode(value)}
              className={`px-3 py-1.5 rounded-card text-xs font-medium uppercase tracking-wide transition-colors duration-200 ${
                mode === value ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {mode === 'wheel' && (
          <span className="text-white/35 text-xs">
            Так дерево увидят игроки. Подклассы правятся в отдельном виде.
          </span>
        )}
      </div>

      <div className="flex-1 flex min-h-0">
        {/* Left Sidebar — Tree List */}
        <div
          className={`
            ${sidebarOpen ? 'w-[260px]' : 'w-0'}
            flex-shrink-0 transition-all duration-200 overflow-hidden
            md:w-[260px] bg-black/40 backdrop-blur-sm border-r border-white/10
            flex flex-col
          `}
        >
          <div className="p-3 flex-shrink-0 space-y-2">
            {/* Mobile toggle */}
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="md:hidden text-white/50 hover:text-white"
            >
              <ChevronRight size={16} />
            </button>

            {/* Search */}
            <div className="relative">
              <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-white/30" />
              <input
                type="text"
                placeholder="Поиск деревьев..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="input-underline w-full text-sm pl-7"
              />
            </div>

            {/* Create button */}
            <button
              onClick={() => setShowCreateForm(!showCreateForm)}
              className="btn-blue w-full flex items-center justify-center gap-1.5 text-sm !py-1.5"
            >
              <Plus size={14} />
              Создать дерево
            </button>

            {/* Create form */}
            {showCreateForm && (
              <div className="space-y-2 p-2 bg-white/5 rounded-card">
                <input
                  type="text"
                  placeholder="Название дерева"
                  value={newTree.name}
                  onChange={(e) => setNewTree({ ...newTree, name: e.target.value })}
                  className="input-underline w-full text-sm"
                />
                <select
                  value={newTree.class_id}
                  onChange={(e) => setNewTree({ ...newTree, class_id: Number(e.target.value) })}
                  className="input-underline w-full text-sm bg-transparent"
                >
                  {CLASS_OPTIONS.map((c) => (
                    <option key={c.value} value={c.value} className="bg-site-dark">
                      {c.label}
                    </option>
                  ))}
                </select>
                <select
                  value={newTree.tree_type ?? 'class'}
                  onChange={(e) => setNewTree({ ...newTree, tree_type: e.target.value })}
                  className="input-underline w-full text-sm bg-transparent"
                >
                  {TREE_TYPE_OPTIONS.map((t) => (
                    <option key={t.value} value={t.value} className="bg-site-dark">
                      {t.label}
                    </option>
                  ))}
                </select>

                {newTree.tree_type === 'subclass' && (
                  <>
                    <select
                      value={newTree.parent_tree_id ?? ''}
                      onChange={(e) =>
                        setNewTree({ ...newTree, parent_tree_id: e.target.value ? Number(e.target.value) : null })
                      }
                      className="input-underline w-full text-sm bg-transparent"
                    >
                      <option value="" className="bg-site-dark">Родительское дерево...</option>
                      {parentTreeOptions.map((pt) => (
                        <option key={pt.id} value={pt.id} className="bg-site-dark">
                          {pt.name}
                        </option>
                      ))}
                    </select>
                    <select
                      value={newTree.subclass_key ?? ''}
                      onChange={(e) => {
                        const sub = createFormSubclasses.find((s) => s.key === e.target.value);
                        setNewTree({
                          ...newTree,
                          subclass_key: e.target.value || null,
                          subclass_name: sub?.name ?? null,
                        });
                      }}
                      className="input-underline w-full text-sm bg-transparent"
                    >
                      <option value="" className="bg-site-dark">Подкласс...</option>
                      {createFormSubclasses.map((s) => (
                        <option key={s.key} value={s.key} className="bg-site-dark">
                          {s.name}
                        </option>
                      ))}
                    </select>
                  </>
                )}

                <div className="flex gap-2">
                  <button onClick={handleCreateTree} className="btn-blue flex-1 text-sm !py-1">
                    Создать
                  </button>
                  <button
                    onClick={() => setShowCreateForm(false)}
                    className="btn-line flex-1 text-sm !py-1"
                  >
                    Отмена
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Tree list */}
          <div className="flex-1 overflow-y-auto gold-scrollbar px-3 pb-3">
            {status === 'loading' && treeList.length === 0 && (
              <p className="text-white/40 text-sm text-center py-4">Загрузка...</p>
            )}

            {groupedTrees.map((group) => (
              <div key={group.classId} className="mb-3">
                <h4 className="text-white/50 text-xs font-medium uppercase tracking-wider mb-1.5 px-1">
                  {group.className}
                </h4>
                {group.trees.map((tree) => {
                  const isSelected = selectedFullTree?.id === tree.id;
                  const isSubclass = tree.tree_type === 'subclass';
                  return (
                    <button
                      key={tree.id}
                      onClick={() => handleSelectTree(tree.id)}
                      className={`
                        w-full text-left p-2 rounded-card mb-1 transition-colors duration-200 ease-site
                        ${isSubclass ? 'pl-5' : ''}
                        ${isSelected ? 'bg-white/10 text-white' : 'text-white/70 hover:bg-white/[0.07] hover:text-white'}
                      `}
                    >
                      <span className="text-sm block truncate">{tree.name}</span>
                      {isSubclass && tree.subclass_name && (
                        <span className="text-xs text-white/40 block truncate">
                          Подкласс: {tree.subclass_name}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            ))}

            {groupedTrees.length === 0 && status !== 'loading' && (
              <p className="text-white/30 text-sm text-center py-4 italic">
                Нет деревьев
              </p>
            )}
          </div>
        </div>

        {/* Center + Right Panels */}
        <div className="flex-1 flex flex-col md:flex-row min-w-0">
          {/* Center — Canvas */}
          <div className="flex-1 flex flex-col min-w-0 min-h-0">
            {mode === 'wheel' ? (
              <>
                <WheelToolbar
                  trees={wheelToolbarTrees}
                  onAddNode={wheel.addNode}
                  onSave={handleWheelSave}
                  onReload={loadWheelTrees}
                  isSaving={wheelSaving}
                  isDirty={wheel.isDirty}
                />
                <WheelLayoutPanel config={wheelLayout} onChange={setWheelLayout} />
                <div className="flex-1 min-h-0 relative z-0">
                  {wheelLoading && wheelTrees.length === 0 ? (
                    <div className="flex items-center justify-center h-full">
                      <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
                    </div>
                  ) : wheelTrees.length === 0 ? (
                    <div className="flex items-center justify-center h-full">
                      <p className="text-white/30 text-lg text-center px-6">
                        Нет ни одного дерева класса. Создайте его в списке слева.
                      </p>
                    </div>
                  ) : (
                    <CombinedTreeCanvas
                      nodes={wheel.nodes}
                      edges={wheel.edges}
                      onNodeClick={wheel.setSelectedNodeId}
                      onEdgeDelete={wheel.removeEdge}
                      onConnectNodes={wheel.connectNodes}
                    />
                  )}
                </div>
              </>
            ) : (
            <>
            {/* Toolbar */}
            <TreeToolbar
              treeName={editor.treeName}
              treeDescription={editor.treeDescription}
              onTreeNameChange={editor.setTreeName}
              onTreeDescriptionChange={editor.setTreeDescription}
              onSave={handleSave}
              onAddNode={(ring) => editor.addNode(ring)}
              onAutoLayout={handleAutoLayout}
              onAlignRows={handleAlignRows}
              isSaving={updateStatus === 'loading'}
              isDirty={editor.isDirty}
              hasTree={!!selectedFullTree}
            />

            {/* Delete tree button */}
            {selectedFullTree && (
              <div className="px-3 py-1 flex-shrink-0">
                <button
                  onClick={handleDeleteTree}
                  className="flex items-center gap-1 text-site-red/70 hover:text-site-red text-xs transition-colors"
                >
                  <Trash2 size={12} />
                  Удалить дерево
                </button>
              </div>
            )}

            {/* Canvas */}
            <div className="flex-1 min-h-0 relative z-0">
              {selectedFullTree ? (
                <ClassTreeCanvas
                  nodes={editor.nodes}
                  edges={editor.edges}
                  onNodesChange={editor.onNodesChange}
                  onEdgesChange={editor.onEdgesChange}
                  onConnect={editor.onConnect}
                  onNodeClick={(id) => editor.setSelectedNodeId(id)}
                  onEdgeDelete={(id) => editor.removeEdge(id)}
                />
              ) : (
                <div className="flex items-center justify-center h-full">
                  <p className="text-white/30 text-lg">
                    Выберите дерево из списка слева или создайте новое
                  </p>
                </div>
              )}
            </div>
            </>
            )}
          </div>

          {/* Right — Node Inspector (wheel) */}
          {mode === 'wheel' && wheel.selectedNode && (
            <div
              className="
                w-full md:w-[300px] flex-shrink-0
                bg-black/40 backdrop-blur-sm border-l border-white/10
                p-4 overflow-y-auto gold-scrollbar
                max-h-[40vh] md:max-h-none
              "
            >
              <TreeNodeInspector
                node={wheel.selectedNode}
                subclasses={wheelInspectorSubclasses}
                onUpdateField={wheel.updateNodeData}
                onRemoveNode={wheel.removeNode}
                onAddSkill={wheel.addSkillToNode}
                onRemoveSkill={wheel.removeSkillFromNode}
                onClose={() => wheel.setSelectedNodeId(null)}
              />
            </div>
          )}

          {/* Right — Node Inspector (single tree) */}
          {mode === 'single' && editor.selectedNode && (
            <div
              className={`
                w-full md:w-[300px] flex-shrink-0
                bg-black/40 backdrop-blur-sm border-l border-white/10
                p-4 overflow-y-auto gold-scrollbar
                max-h-[40vh] md:max-h-none
              `}
            >
              <TreeNodeInspector
                node={editor.selectedNode}
                subclasses={inspectorSubclasses}
                onUpdateField={editor.updateNodeData}
                onRemoveNode={editor.removeNode}
                onAddSkill={editor.addSkillToNode}
                onRemoveSkill={editor.removeSkillFromNode}
                onClose={() => editor.setSelectedNodeId(null)}
              />
            </div>
          )}
        </div>
      </div>

      {/* Mobile sidebar toggle */}
      {!sidebarOpen && (
        <button
          onClick={() => setSidebarOpen(true)}
          className="fixed left-2 top-24 z-40 md:hidden bg-site-bg rounded-full p-2 shadow-card border border-white/10 text-white"
        >
          <ChevronRight size={16} />
        </button>
      )}
    </div>
  );
};

export default AdminClassTreePage;
