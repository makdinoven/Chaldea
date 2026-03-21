import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../api/api';

/* ── Types ── */

interface DialogueOptionForm {
  text: string;
  next_node_index: number | null; // index in nodes array
}

interface DialogueNodeForm {
  npc_text: string;
  is_root: boolean;
  action_type: string;
  options: DialogueOptionForm[];
}

interface DialogueTreeSummary {
  id: number;
  title: string;
  npc_id: number;
  nodes_count: number;
}

interface ApiDialogueOption {
  id: number;
  text: string;
  next_node_id: number | null;
}

interface ApiDialogueNode {
  id: number;
  npc_text: string;
  is_root: boolean;
  is_end: boolean;
  action_type: string | null;
  options: ApiDialogueOption[];
}

interface ApiDialogueTree {
  id: number;
  title: string;
  npc_id: number;
  nodes: ApiDialogueNode[];
}

interface DialogueEditorProps {
  npcId: number;
  npcName: string;
  onClose: () => void;
}

const ACTION_TYPES = [
  { value: '', label: 'Нет действия' },
  { value: 'open_shop', label: 'Открыть магазин' },
  { value: 'give_quest', label: 'Выдать задание' },
  { value: 'heal', label: 'Исцелить' },
  { value: 'teleport', label: 'Телепортировать' },
  { value: 'give_item', label: 'Выдать предмет' },
  { value: 'give_gold', label: 'Выдать золото' },
  { value: 'give_xp', label: 'Выдать опыт' },
  { value: 'start_battle', label: 'Начать бой' },
  { value: 'train_skill', label: 'Обучить навыку' },
];

/* ── Helper: convert API tree to form state ── */
const apiTreeToForm = (tree: ApiDialogueTree): { title: string; nodes: DialogueNodeForm[] } => {
  const nodeIdToIndex = new Map<number, number>();
  tree.nodes.forEach((node, idx) => nodeIdToIndex.set(node.id, idx));

  const nodes: DialogueNodeForm[] = tree.nodes.map((node) => ({
    npc_text: node.npc_text,
    is_root: node.is_root,
    action_type: node.action_type || '',
    options: node.options.map((opt) => ({
      text: opt.text,
      next_node_index: opt.next_node_id !== null ? (nodeIdToIndex.get(opt.next_node_id) ?? null) : null,
    })),
  }));

  return { title: tree.title, nodes };
};

/* ── Component ── */

const DialogueEditor = ({ npcId, npcName, onClose }: DialogueEditorProps) => {
  const [trees, setTrees] = useState<DialogueTreeSummary[]>([]);
  const [loadingTrees, setLoadingTrees] = useState(true);

  // Editor state
  const [editingTreeId, setEditingTreeId] = useState<number | null>(null);
  const [title, setTitle] = useState('');
  const [nodes, setNodes] = useState<DialogueNodeForm[]>([]);
  const [editorOpen, setEditorOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const fetchTrees = useCallback(async () => {
    setLoadingTrees(true);
    try {
      const res = await axios.get<DialogueTreeSummary[]>(
        `${BASE_URL}/locations/admin/dialogues`,
        { params: { npc_id: npcId } },
      );
      setTrees(res.data);
    } catch {
      toast.error('Не удалось загрузить деревья диалогов');
    } finally {
      setLoadingTrees(false);
    }
  }, [npcId]);

  useEffect(() => {
    fetchTrees();
  }, [fetchTrees]);

  const openNewTree = () => {
    setEditingTreeId(null);
    setTitle('');
    setNodes([
      {
        npc_text: '',
        is_root: true,
        action_type: '',
        options: [],
      },
    ]);
    setEditorOpen(true);
  };

  const openEditTree = async (treeId: number) => {
    try {
      const res = await axios.get<ApiDialogueTree>(`${BASE_URL}/locations/admin/dialogues/${treeId}`);
      const { title: t, nodes: n } = apiTreeToForm(res.data);
      setEditingTreeId(treeId);
      setTitle(t);
      setNodes(n);
      setEditorOpen(true);
    } catch {
      toast.error('Не удалось загрузить дерево диалога');
    }
  };

  const handleDeleteTree = async (treeId: number) => {
    if (!window.confirm('Удалить дерево диалога? Это действие нельзя отменить.')) return;
    try {
      await axios.delete(`${BASE_URL}/locations/admin/dialogues/${treeId}`);
      toast.success('Дерево диалога удалено');
      setTrees((prev) => prev.filter((t) => t.id !== treeId));
      if (editingTreeId === treeId) {
        setEditorOpen(false);
        setEditingTreeId(null);
      }
    } catch {
      toast.error('Не удалось удалить дерево диалога');
    }
  };

  /* ── Node manipulation ── */

  const addNode = () => {
    setNodes((prev) => [
      ...prev,
      {
        npc_text: '',
        is_root: false,
        action_type: '',
        options: [],
      },
    ]);
  };

  const removeNode = (nodeIndex: number) => {
    setNodes((prev) => {
      const updated = prev.filter((_, i) => i !== nodeIndex);
      // Fix references in options
      return updated.map((node) => ({
        ...node,
        options: node.options
          .map((opt) => {
            if (opt.next_node_index === null) return opt;
            if (opt.next_node_index === nodeIndex) return { ...opt, next_node_index: null };
            if (opt.next_node_index > nodeIndex) return { ...opt, next_node_index: opt.next_node_index - 1 };
            return opt;
          }),
      }));
    });
  };

  const updateNode = (nodeIndex: number, field: keyof DialogueNodeForm, value: string | boolean) => {
    setNodes((prev) =>
      prev.map((node, i) => {
        if (i !== nodeIndex) {
          // If setting is_root, unset it on other nodes
          if (field === 'is_root' && value === true) {
            return { ...node, is_root: false };
          }
          return node;
        }
        return { ...node, [field]: value };
      }),
    );
  };

  const addOption = (nodeIndex: number) => {
    setNodes((prev) =>
      prev.map((node, i) =>
        i === nodeIndex
          ? { ...node, options: [...node.options, { text: '', next_node_index: null }] }
          : node,
      ),
    );
  };

  const removeOption = (nodeIndex: number, optionIndex: number) => {
    setNodes((prev) =>
      prev.map((node, i) =>
        i === nodeIndex
          ? { ...node, options: node.options.filter((_, oi) => oi !== optionIndex) }
          : node,
      ),
    );
  };

  const updateOption = (
    nodeIndex: number,
    optionIndex: number,
    field: keyof DialogueOptionForm,
    value: string | number | null,
  ) => {
    setNodes((prev) =>
      prev.map((node, i) =>
        i === nodeIndex
          ? {
              ...node,
              options: node.options.map((opt, oi) =>
                oi === optionIndex ? { ...opt, [field]: value } : opt,
              ),
            }
          : node,
      ),
    );
  };

  /* ── Save ── */

  const handleSave = async () => {
    if (!title.trim()) {
      toast.error('Название дерева обязательно');
      return;
    }
    if (nodes.length === 0) {
      toast.error('Добавьте хотя бы один узел');
      return;
    }
    if (!nodes.some((n) => n.is_root)) {
      toast.error('Отметьте один узел как корневой');
      return;
    }

    const payload = {
      title: title.trim(),
      npc_id: npcId,
      nodes: nodes.map((node) => ({
        npc_text: node.npc_text,
        is_root: node.is_root,
        action_type: node.action_type || null,
        options: node.options.map((opt) => ({
          text: opt.text,
          next_node_index: opt.next_node_index,
        })),
      })),
    };

    setSaving(true);
    try {
      if (editingTreeId) {
        await axios.put(`${BASE_URL}/locations/admin/dialogues/${editingTreeId}`, payload);
        toast.success('Дерево диалога обновлено');
      } else {
        await axios.post(`${BASE_URL}/locations/admin/dialogues`, payload);
        toast.success('Дерево диалога создано');
      }
      setEditorOpen(false);
      setEditingTreeId(null);
      fetchTrees();
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось сохранить дерево диалога';
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  /* ── Render ── */

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        <button
          onClick={onClose}
          className="text-white/50 hover:text-white transition-colors flex items-center gap-1 text-sm"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          Назад к НПС
        </button>
        <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase tracking-[0.06em]">
          Диалоги: {npcName}
        </h2>
        <button className="btn-blue !text-sm !px-5 !py-2 sm:ml-auto" onClick={openNewTree}>
          Создать дерево
        </button>
      </div>

      {/* Trees list */}
      {!editorOpen && (
        <div className="gray-bg p-4 sm:p-6">
          {loadingTrees ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
            </div>
          ) : trees.length === 0 ? (
            <p className="text-center text-white/50 text-sm py-6">Деревья диалогов не найдены</p>
          ) : (
            <div className="flex flex-col gap-3">
              {trees.map((tree) => (
                <div
                  key={tree.id}
                  className="flex flex-col sm:flex-row items-start sm:items-center gap-3 bg-white/[0.03] rounded-card p-4"
                >
                  <div className="flex flex-col gap-1 min-w-0 flex-1">
                    <span className="text-white text-sm font-medium">{tree.title}</span>
                    <span className="text-white/40 text-xs">
                      ID: {tree.id} | Узлов: {tree.nodes_count}
                    </span>
                  </div>
                  <div className="flex gap-3 shrink-0">
                    <button
                      onClick={() => openEditTree(tree.id)}
                      className="text-sm text-white hover:text-site-blue transition-colors"
                    >
                      Редактировать
                    </button>
                    <button
                      onClick={() => handleDeleteTree(tree.id)}
                      className="text-sm text-site-red hover:text-white transition-colors"
                    >
                      Удалить
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Editor */}
      {editorOpen && (
        <div className="gray-bg p-4 sm:p-6 flex flex-col gap-5">
          <h3 className="gold-text text-lg sm:text-xl font-medium uppercase tracking-[0.06em]">
            {editingTreeId ? 'Редактирование дерева' : 'Новое дерево диалога'}
          </h3>

          {/* Title */}
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Название дерева
            </span>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="input-underline max-w-md"
              placeholder="Например: Основной диалог"
            />
          </label>

          {/* Nodes */}
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-3">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Узлы диалога ({nodes.length})
              </span>
            </div>

            {nodes.map((node, nodeIndex) => (
              <div
                key={nodeIndex}
                className={`
                  bg-white/[0.03] rounded-card p-4 flex flex-col gap-4
                  border-l-4
                  ${node.is_root ? 'border-l-gold' : 'border-l-white/10'}
                `}
              >
                {/* Node header */}
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="text-white text-sm font-medium">
                    Узел #{nodeIndex + 1}
                  </span>
                  {node.is_root && (
                    <span className="px-2 py-0.5 rounded-full bg-gold/20 text-gold text-[10px] font-medium uppercase">
                      Корневой
                    </span>
                  )}
                  <button
                    onClick={() => removeNode(nodeIndex)}
                    className="text-xs text-site-red hover:text-white transition-colors ml-auto"
                    title="Удалить узел"
                  >
                    Удалить узел
                  </button>
                </div>

                {/* NPC text */}
                <label className="flex flex-col gap-1">
                  <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                    Текст НПС
                  </span>
                  <textarea
                    value={node.npc_text}
                    onChange={(e) => updateNode(nodeIndex, 'npc_text', e.target.value)}
                    rows={3}
                    className="textarea-bordered text-sm"
                    placeholder="Что скажет НПС..."
                  />
                </label>

                {/* Controls row */}
                <div className="flex flex-col sm:flex-row gap-3 sm:gap-4">
                  {/* Root checkbox */}
                  <label className="flex items-center gap-2 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={node.is_root}
                      onChange={(e) => updateNode(nodeIndex, 'is_root', e.target.checked)}
                      className="w-4 h-4 accent-gold"
                    />
                    <span className="text-white/70 text-sm">Корневой узел</span>
                  </label>

                  {/* Action type */}
                  <label className="flex items-center gap-2 flex-1 max-w-xs">
                    <span className="text-white/50 text-xs font-medium uppercase whitespace-nowrap">
                      Действие:
                    </span>
                    <select
                      value={node.action_type}
                      onChange={(e) => updateNode(nodeIndex, 'action_type', e.target.value)}
                      className="input-underline !text-sm"
                    >
                      {ACTION_TYPES.map((a) => (
                        <option key={a.value} value={a.value} className="bg-site-dark text-white">
                          {a.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                {/* Options */}
                <div className="flex flex-col gap-2">
                  <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                    Варианты ответов ({node.options.length})
                  </span>

                  {node.options.map((option, optIndex) => (
                    <div
                      key={optIndex}
                      className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 bg-black/20 rounded-card p-3"
                    >
                      {/* Option text */}
                      <input
                        value={option.text}
                        onChange={(e) => updateOption(nodeIndex, optIndex, 'text', e.target.value)}
                        className="input-underline !text-sm flex-1"
                        placeholder="Текст ответа игрока..."
                      />

                      {/* Next node selector */}
                      <select
                        value={option.next_node_index ?? ''}
                        onChange={(e) => {
                          const val = e.target.value;
                          updateOption(
                            nodeIndex,
                            optIndex,
                            'next_node_index',
                            val === '' ? null : Number(val),
                          );
                        }}
                        className="input-underline !text-sm max-w-[180px]"
                      >
                        <option value="" className="bg-site-dark text-white">
                          Конец диалога
                        </option>
                        {nodes.map((_, ni) => (
                          <option
                            key={ni}
                            value={ni}
                            className="bg-site-dark text-white"
                            disabled={ni === nodeIndex}
                          >
                            Узел #{ni + 1}
                            {ni === nodeIndex ? ' (текущий)' : ''}
                          </option>
                        ))}
                      </select>

                      {/* Delete option */}
                      <button
                        onClick={() => removeOption(nodeIndex, optIndex)}
                        className="text-site-red hover:text-white transition-colors p-1 shrink-0 self-center"
                        title="Удалить вариант"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  ))}

                  <button
                    onClick={() => addOption(nodeIndex)}
                    className="text-sm text-site-blue hover:text-white transition-colors self-start mt-1"
                  >
                    + Добавить вариант ответа
                  </button>
                </div>
              </div>
            ))}

            <button
              onClick={addNode}
              className="text-sm text-site-blue hover:text-white transition-colors self-start"
            >
              + Добавить узел
            </button>
          </div>

          {/* Actions */}
          <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 pt-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="btn-blue !text-base !px-8 !py-2 disabled:opacity-50"
            >
              {saving ? 'Сохранение...' : editingTreeId ? 'Сохранить' : 'Создать'}
            </button>
            <button
              onClick={() => {
                setEditorOpen(false);
                setEditingTreeId(null);
              }}
              className="btn-line !w-auto !px-8"
            >
              Отмена
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default DialogueEditor;
