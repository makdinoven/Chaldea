import { useState, useCallback, useRef, useEffect } from 'react';
import {
  useNodesState,
  useEdgesState,
  addEdge,
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  type OnConnect,
} from 'reactflow';
import type {
  FullClassTreeResponse,
  TreeNodeSkillRead,
  TreeNodeInTreeResponse,
} from '../types';
import { apiToReactFlow, reactFlowToApi } from '../utils/treeTransforms';

export const useClassTreeEditor = (fullTree: FullClassTreeResponse | null) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const tempIdCounter = useRef(1);

  // Tree metadata editable fields
  const [treeName, setTreeName] = useState('');
  const [treeDescription, setTreeDescription] = useState('');

  // Load full tree into ReactFlow state
  useEffect(() => {
    if (!fullTree) {
      setNodes([]);
      setEdges([]);
      setSelectedNodeId(null);
      setIsDirty(false);
      return;
    }
    const { nodes: rfNodes, edges: rfEdges } = apiToReactFlow(fullTree);
    setNodes(rfNodes);
    setEdges(rfEdges);
    setTreeName(fullTree.name);
    setTreeDescription(fullTree.description ?? '');
    setSelectedNodeId(null);
    setIsDirty(false);
    tempIdCounter.current = 1;
  }, [fullTree, setNodes, setEdges]);

  const handleNodesChange: OnNodesChange = useCallback(
    (changes) => {
      onNodesChange(changes);
      setIsDirty(true);
    },
    [onNodesChange]
  );

  const handleEdgesChange: OnEdgesChange = useCallback(
    (changes) => {
      onEdgesChange(changes);
      setIsDirty(true);
    },
    [onEdgesChange]
  );

  const handleConnect: OnConnect = useCallback(
    (params) => {
      const newEdgeId = `temp-c-${tempIdCounter.current++}`;
      setEdges((eds) =>
        addEdge({ ...params, id: newEdgeId, style: { stroke: '#f0d95c', strokeWidth: 2 } }, eds)
      );
      setIsDirty(true);
    },
    [setEdges]
  );

  const generateTempId = useCallback(() => {
    return `temp-${tempIdCounter.current++}`;
  }, []);

  const addNode = useCallback(
    (levelRing: number = 5) => {
      const tempId = generateTempId();
      const newNodeData: TreeNodeInTreeResponse = {
        id: tempId as unknown as number,
        tree_id: fullTree?.id ?? 0,
        level_ring: levelRing,
        position_x: 200 + Math.random() * 200,
        position_y: 200 + Math.random() * 200,
        name: 'Новый узел',
        description: null,
        node_type: 'regular',
        icon_image: null,
        sort_order: 0,
        skills: [],
      };

      const newNode: Node = {
        id: tempId,
        type: 'treeNode',
        position: { x: newNodeData.position_x, y: newNodeData.position_y },
        data: newNodeData,
      };

      setNodes((nds) => [...nds, newNode]);
      setIsDirty(true);
      return tempId;
    },
    [generateTempId, fullTree, setNodes]
  );

  const removeNode = useCallback(
    (nodeId: string) => {
      setNodes((nds) => nds.filter((n) => n.id !== nodeId));
      setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
      if (selectedNodeId === nodeId) setSelectedNodeId(null);
      setIsDirty(true);
    },
    [setNodes, setEdges, selectedNodeId]
  );

  const updateNodeData = useCallback(
    (nodeId: string, field: string, value: unknown) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId
            ? { ...n, data: { ...n.data, [field]: value } }
            : n
        )
      );
      setIsDirty(true);
    },
    [setNodes]
  );

  const addSkillToNode = useCallback(
    (nodeId: string, skill: { skill_id: number; skill_name: string; skill_type: string; skill_image: string | null }) => {
      setNodes((nds) =>
        nds.map((n) => {
          if (n.id !== nodeId) return n;
          const currentSkills: TreeNodeSkillRead[] = n.data.skills ?? [];
          // Prevent duplicate
          if (currentSkills.some((s: TreeNodeSkillRead) => s.skill_id === skill.skill_id)) return n;
          const newSkill: TreeNodeSkillRead = {
            id: 0, // placeholder, resolved by backend
            skill_id: skill.skill_id,
            sort_order: currentSkills.length,
            skill_name: skill.skill_name,
            skill_type: skill.skill_type,
            skill_image: skill.skill_image,
          };
          return {
            ...n,
            data: { ...n.data, skills: [...currentSkills, newSkill] },
          };
        })
      );
      setIsDirty(true);
    },
    [setNodes]
  );

  const removeSkillFromNode = useCallback(
    (nodeId: string, skillId: number) => {
      setNodes((nds) =>
        nds.map((n) => {
          if (n.id !== nodeId) return n;
          const currentSkills: TreeNodeSkillRead[] = n.data.skills ?? [];
          return {
            ...n,
            data: {
              ...n.data,
              skills: currentSkills.filter((s: TreeNodeSkillRead) => s.skill_id !== skillId),
            },
          };
        })
      );
      setIsDirty(true);
    },
    [setNodes]
  );

  const selectedNode = nodes.find((n) => n.id === selectedNodeId) ?? null;

  const getApiPayload = useCallback(() => {
    if (!fullTree) return null;
    return reactFlowToApi(nodes, edges, {
      id: fullTree.id,
      class_id: fullTree.class_id,
      name: treeName,
      description: treeDescription || null,
      tree_type: fullTree.tree_type,
      parent_tree_id: fullTree.parent_tree_id,
      subclass_name: fullTree.subclass_name,
      tree_image: fullTree.tree_image,
    });
  }, [fullTree, nodes, edges, treeName, treeDescription]);

  const applyTempIdMap = useCallback(
    (tempIdMap: Record<string, number>) => {
      setNodes((nds) =>
        nds.map((n) => {
          const realId = tempIdMap[n.id];
          if (realId !== undefined) {
            return {
              ...n,
              id: String(realId),
              data: { ...n.data, id: realId },
            };
          }
          return n;
        })
      );
      setEdges((eds) =>
        eds.map((e) => ({
          ...e,
          id: tempIdMap[e.id] ? String(tempIdMap[e.id]) : e.id,
          source: tempIdMap[e.source] ? String(tempIdMap[e.source]) : e.source,
          target: tempIdMap[e.target] ? String(tempIdMap[e.target]) : e.target,
        }))
      );
      setIsDirty(false);
    },
    [setNodes, setEdges]
  );

  return {
    nodes,
    edges,
    selectedNode,
    selectedNodeId,
    isDirty,
    treeName,
    treeDescription,
    setTreeName,
    setTreeDescription,
    setSelectedNodeId,
    setNodes,
    onNodesChange: handleNodesChange,
    onEdgesChange: handleEdgesChange,
    onConnect: handleConnect,
    addNode,
    removeNode,
    updateNodeData,
    addSkillToNode,
    removeSkillFromNode,
    getApiPayload,
    applyTempIdMap,
    setIsDirty,
  };
};
