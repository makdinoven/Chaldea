import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Connection, Node, Edge } from 'reactflow';
import type {
  FullClassTreeResponse,
  FullClassTreeUpdateRequest,
  TreeNodeInTreeResponse,
  TreeNodeSkillRead,
} from '../types';
import { combineTrees } from '../../SkillTreeView/utils/combineTrees';
import { reactFlowToApi } from '../utils/treeTransforms';

/**
 * Editor state for the combined class wheel — all three class trees at once,
 * laid out exactly as the players see them.
 *
 * Unlike {@link useClassTreeEditor}, which drives one tree and stores positions
 * the author drags around, this one keeps the trees themselves as the source of
 * truth and derives node positions from the shared wheel layout. Dragging is
 * therefore meaningless here: a node's place follows from its level_ring and
 * its order inside that ring.
 */

/** Which tree a rendered node came from, so edits and saves can be routed back. */
export interface WheelNodeData extends TreeNodeInTreeResponse {
  treeId: number;
  classId: number;
  adminView: true;
}

export interface TreePayload {
  treeId: number;
  payload: FullClassTreeUpdateRequest;
}

const cloneTree = (tree: FullClassTreeResponse): FullClassTreeResponse => ({
  ...tree,
  nodes: tree.nodes.map((n) => ({ ...n, skills: [...(n.skills ?? [])] })),
  connections: tree.connections.map((c) => ({ ...c })),
});

export const useCombinedTreeEditor = (trees: FullClassTreeResponse[]) => {
  const [draft, setDraft] = useState<FullClassTreeResponse[]>([]);
  const [dirtyTreeIds, setDirtyTreeIds] = useState<Set<number>>(new Set());
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const tempIdCounter = useRef(1);

  useEffect(() => {
    setDraft(trees.map(cloneTree));
    setDirtyTreeIds(new Set());
    setSelectedNodeId(null);
    tempIdCounter.current = 1;
  }, [trees]);

  const markDirty = useCallback((treeId: number) => {
    setDirtyTreeIds((prev) => (prev.has(treeId) ? prev : new Set(prev).add(treeId)));
  }, []);

  /** Applies a change to one tree of the draft, leaving the others untouched. */
  const editTree = useCallback(
    (treeId: number, change: (tree: FullClassTreeResponse) => FullClassTreeResponse) => {
      setDraft((prev) => prev.map((t) => (t.id === treeId ? change(t) : t)));
      markDirty(treeId);
    },
    [markDirty],
  );

  /** Which tree holds a node, by the node's rendered (string) id. */
  const treeIdOfNode = useCallback(
    (nodeId: string): number | null => {
      for (const tree of draft) {
        if (tree.nodes.some((n) => String(n.id) === nodeId)) return tree.id;
      }
      return null;
    },
    [draft],
  );

  const layout = useMemo(() => combineTrees(draft), [draft]);

  const nodes: Node[] = useMemo(() => {
    const out: Node[] = [];
    for (const tree of draft) {
      for (const apiNode of tree.nodes) {
        const id = String(apiNode.id);
        const centre = layout.positions.get(id);
        if (!centre) continue;
        const half = (apiNode.node_type === 'root' || apiNode.node_type === 'subclass_choice' ? 70 : 40) / 2;
        const data: WheelNodeData = {
          ...apiNode,
          treeId: tree.id,
          classId: tree.class_id,
          adminView: true,
        };
        out.push({
          id,
          type: 'playerNode',
          position: { x: centre.x - half, y: centre.y - half },
          data: { ...data, visualState: 'locked', foreign: false },
          // Positions come from the wheel layout, so there is nothing to drag.
          draggable: false,
          selectable: true,
          connectable: true,
        });
      }
    }
    return out;
  }, [draft, layout]);

  const edges: Edge[] = useMemo(() => {
    const out: Edge[] = [];
    for (const tree of draft) {
      for (const conn of tree.connections) {
        out.push({
          id: String(conn.id ?? `edge-${conn.from_node_id}-${conn.to_node_id}`),
          source: String(conn.from_node_id),
          target: String(conn.to_node_id),
          type: 'gradient',
          data: { treeId: tree.id, classId: tree.class_id },
        });
      }
    }
    for (const bridge of layout.bridges) {
      out.push({
        id: bridge.id,
        source: bridge.fromNodeId,
        target: bridge.toNodeId,
        type: 'bridge',
        focusable: false,
        interactionWidth: 0,
      });
    }
    return out;
  }, [draft, layout]);

  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selectedNodeId) ?? null,
    [nodes, selectedNodeId],
  );

  const addNode = useCallback(
    (treeId: number, levelRing: number) => {
      const tempId = `temp-${treeId}-${tempIdCounter.current++}`;
      editTree(treeId, (tree) => ({
        ...tree,
        nodes: [
          ...tree.nodes,
          {
            id: tempId as unknown as number,
            tree_id: treeId,
            level_ring: levelRing,
            // The wheel ignores these, but the API still stores them and the
            // single-tree editor still uses them.
            position_x: 0,
            position_y: 0,
            name: 'Новый узел',
            description: null,
            node_type: 'regular',
            subclass_key: null,
            icon_image: null,
            // New nodes go last in their ring until the author reorders them.
            sort_order: tree.nodes.filter((n) => n.level_ring === levelRing).length,
            skills: [],
          },
        ],
      }));
      setSelectedNodeId(tempId);
      return tempId;
    },
    [editTree],
  );

  const removeNode = useCallback(
    (nodeId: string) => {
      const treeId = treeIdOfNode(nodeId);
      if (treeId === null) return;
      editTree(treeId, (tree) => ({
        ...tree,
        nodes: tree.nodes.filter((n) => String(n.id) !== nodeId),
        connections: tree.connections.filter(
          (c) => String(c.from_node_id) !== nodeId && String(c.to_node_id) !== nodeId,
        ),
      }));
      setSelectedNodeId((cur) => (cur === nodeId ? null : cur));
    },
    [editTree, treeIdOfNode],
  );

  const removeEdge = useCallback(
    (edgeId: string) => {
      const owner = draft.find((tree) =>
        tree.connections.some(
          (c) => String(c.id ?? `edge-${c.from_node_id}-${c.to_node_id}`) === edgeId,
        ),
      );
      if (!owner) return; // a sector bridge — decoration, nothing to delete
      editTree(owner.id, (tree) => ({
        ...tree,
        connections: tree.connections.filter(
          (c) => String(c.id ?? `edge-${c.from_node_id}-${c.to_node_id}`) !== edgeId,
        ),
      }));
    },
    [draft, editTree],
  );

  /**
   * Adds a connection. Returns an error message when the link is not allowed —
   * the caller shows it, since a silent no-op looks like a broken canvas.
   */
  const connectNodes = useCallback(
    (params: Connection): string | null => {
      const { source, target } = params;
      if (!source || !target) return null;
      if (source === target) return 'Узел нельзя связать с самим собой';

      const sourceTree = treeIdOfNode(source);
      const targetTree = treeIdOfNode(target);
      if (sourceTree === null || targetTree === null) return 'Узел не найден';
      if (sourceTree !== targetTree) {
        return 'Связи между деревьями разных классов не поддерживаются';
      }

      const tree = draft.find((t) => t.id === sourceTree);
      const exists = tree?.connections.some(
        (c) =>
          (String(c.from_node_id) === source && String(c.to_node_id) === target) ||
          (String(c.from_node_id) === target && String(c.to_node_id) === source),
      );
      if (exists) return 'Такая связь уже есть';

      editTree(sourceTree, (t) => ({
        ...t,
        connections: [
          ...t.connections,
          { id: `temp-c-${tempIdCounter.current++}`, from_node_id: source, to_node_id: target },
        ],
      }));
      return null;
    },
    [draft, editTree, treeIdOfNode],
  );

  const updateNodeData = useCallback(
    (nodeId: string, field: string, value: unknown) => {
      const treeId = treeIdOfNode(nodeId);
      if (treeId === null) return;
      editTree(treeId, (tree) => ({
        ...tree,
        nodes: tree.nodes.map((n) =>
          String(n.id) === nodeId ? { ...n, [field]: value } : n,
        ),
      }));
    },
    [editTree, treeIdOfNode],
  );

  const addSkillToNode = useCallback(
    (
      nodeId: string,
      skill: { skill_id: number; skill_name: string; skill_type: string; skill_image: string | null },
    ) => {
      const treeId = treeIdOfNode(nodeId);
      if (treeId === null) return;
      editTree(treeId, (tree) => ({
        ...tree,
        nodes: tree.nodes.map((n) => {
          if (String(n.id) !== nodeId) return n;
          const current: TreeNodeSkillRead[] = n.skills ?? [];
          if (current.some((s) => s.skill_id === skill.skill_id)) return n;
          return {
            ...n,
            skills: [
              ...current,
              {
                id: 0, // placeholder, resolved by the backend on save
                skill_id: skill.skill_id,
                sort_order: current.length,
                skill_name: skill.skill_name,
                skill_type: skill.skill_type,
                skill_image: skill.skill_image,
              },
            ],
          };
        }),
      }));
    },
    [editTree, treeIdOfNode],
  );

  const removeSkillFromNode = useCallback(
    (nodeId: string, skillId: number) => {
      const treeId = treeIdOfNode(nodeId);
      if (treeId === null) return;
      editTree(treeId, (tree) => ({
        ...tree,
        nodes: tree.nodes.map((n) =>
          String(n.id) === nodeId
            ? { ...n, skills: (n.skills ?? []).filter((s) => s.skill_id !== skillId) }
            : n,
        ),
      }));
    },
    [editTree, treeIdOfNode],
  );

  /** One save payload per tree that actually changed. */
  const getDirtyPayloads = useCallback((): TreePayload[] => {
    return draft
      .filter((tree) => dirtyTreeIds.has(tree.id))
      .map((tree) => {
        const rfNodes: Node[] = tree.nodes.map((n) => ({
          id: String(n.id),
          position: { x: n.position_x, y: n.position_y },
          data: n,
        }));
        const rfEdges: Edge[] = tree.connections.map((c) => ({
          id: String(c.id ?? `edge-${c.from_node_id}-${c.to_node_id}`),
          source: String(c.from_node_id),
          target: String(c.to_node_id),
        }));
        return {
          treeId: tree.id,
          payload: reactFlowToApi(rfNodes, rfEdges, {
            id: tree.id,
            class_id: tree.class_id,
            name: tree.name,
            description: tree.description,
            tree_type: tree.tree_type,
            parent_tree_id: tree.parent_tree_id,
            subclass_name: tree.subclass_name,
            subclass_key: tree.subclass_key,
            tree_image: tree.tree_image,
          }),
        };
      });
  }, [draft, dirtyTreeIds]);

  const clearDirty = useCallback(() => setDirtyTreeIds(new Set()), []);

  return {
    draft,
    nodes,
    edges,
    selectedNode,
    selectedNodeId,
    setSelectedNodeId,
    isDirty: dirtyTreeIds.size > 0,
    dirtyTreeIds,
    addNode,
    removeNode,
    removeEdge,
    connectNodes,
    updateNodeData,
    addSkillToNode,
    removeSkillFromNode,
    getDirtyPayloads,
    clearDirty,
  };
};
