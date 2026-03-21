import { useEffect, useState } from 'react';
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
import { autoLayoutRings } from './utils/ringLayout';
import ClassTreeCanvas from './ClassTreeCanvas';
import TreeNodeInspector from './TreeNodeInspector';
import TreeToolbar from './TreeToolbar';
import {
  CLASS_OPTIONS,
  TREE_TYPE_OPTIONS,
  type ClassSkillTreeRead,
  type ClassSkillTreeCreate,
} from './types';
import { Plus, Trash2, ChevronRight, Search } from 'react-feather';

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

  const editor = useClassTreeEditor(selectedFullTree);

  useEffect(() => {
    dispatch(fetchClassTrees());
  }, [dispatch]);

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
    } catch {
      toast.error('Ошибка при создании дерева');
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

  const handleAutoLayout = () => {
    const laid = autoLayoutRings(editor.nodes);
    editor.setNodes(laid);
    editor.setIsDirty(true);
  };

  // Find parent tree options for subclass creation
  const parentTreeOptions = treeList.filter((t) => t.tree_type === 'class' && t.class_id === newTree.class_id);

  return (
    <div className="w-full h-[calc(100vh-80px)] flex flex-col">
      {/* Page title */}
      <h1 className="gold-text text-2xl sm:text-3xl font-medium uppercase tracking-wider px-4 py-3 flex-shrink-0">
        Деревья классов
      </h1>

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
                    <input
                      type="text"
                      placeholder="Название подкласса"
                      value={newTree.subclass_name ?? ''}
                      onChange={(e) => setNewTree({ ...newTree, subclass_name: e.target.value || null })}
                      className="input-underline w-full text-sm"
                    />
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
            {/* Toolbar */}
            <TreeToolbar
              treeName={editor.treeName}
              treeDescription={editor.treeDescription}
              onTreeNameChange={editor.setTreeName}
              onTreeDescriptionChange={editor.setTreeDescription}
              onSave={handleSave}
              onAddNode={(ring) => editor.addNode(ring)}
              onAutoLayout={handleAutoLayout}
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
            <div className="flex-1 min-h-0">
              {selectedFullTree ? (
                <ClassTreeCanvas
                  nodes={editor.nodes}
                  edges={editor.edges}
                  onNodesChange={editor.onNodesChange}
                  onEdgesChange={editor.onEdgesChange}
                  onConnect={editor.onConnect}
                  onNodeClick={(id) => editor.setSelectedNodeId(id)}
                />
              ) : (
                <div className="flex items-center justify-center h-full">
                  <p className="text-white/30 text-lg">
                    Выберите дерево из списка слева или создайте новое
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Right — Node Inspector */}
          {editor.selectedNode && (
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
