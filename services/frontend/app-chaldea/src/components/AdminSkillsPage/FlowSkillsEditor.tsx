// src/components/AdminSkillsPage/FlowSkillsEditor.tsx

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  Node,
  Edge,
  Connection,
} from 'reactflow';
import 'reactflow/dist/style.css';

import styles from './AdminSkillsPage.module.scss';
import { updateSkillFullTree } from '../../redux/actions/skillsAdminActions';
import { makeNodeTypes } from './nodeTypes';
import {
  EMPTY_RANK_TEMPLATE,
  CLASS_OPTIONS,
  RACE_OPTIONS,
  SUBRACE_OPTIONS,
  cloneRankAsNew,
  RankData,
} from './skillConstants';

import { useDispatch } from 'react-redux';

import { prepareSkillPayload } from './utils/preparePayload';

// ---- Types ----

interface SkillTree {
  id?: number | string;
  name?: string;
  skill_type?: string;
  description?: string;
  class_limitations?: string;
  race_limitations?: string;
  subrace_limitations?: string;
  min_level?: number;
  purchase_cost?: number;
  skill_image?: string;
  ranks?: RankData[];
}

interface FlowSkillsEditorProps {
  skillTree: SkillTree | null;
  updateStatus: string;
}

// ---- Helper functions ----

function findRoots(ranks: RankData[]): RankData[] {
  const childIDs = new Set<string | null>();
  for (const r of ranks) {
    if (r.left_child_id) childIDs.add(r.left_child_id);
    if (r.right_child_id) childIDs.add(r.right_child_id);
  }
  return ranks.filter(r => !childIDs.has(r.id));
}

function buildRankMap(ranks: RankData[]): Map<string, RankData> {
  const map = new Map<string, RankData>();
  for (const r of ranks) {
    map.set(String(r.id), r);
  }
  return map;
}

function layoutDFS(
  rank: RankData,
  x: number,
  y: number,
  visited: Set<string>,
  rankMap: Map<string, RankData>,
  nodeMap: Map<string, Node<RankData>>
): void {
  const node = nodeMap.get(String(rank.id));
  if (!node) return;
  node.position = { x, y };
  visited.add(String(rank.id));

  if (rank.left_child_id) {
    const child = rankMap.get(String(rank.left_child_id));
    if (child && !visited.has(String(rank.left_child_id))) {
      layoutDFS(child, x + 300, y - 100, visited, rankMap, nodeMap);
    }
  }
  if (rank.right_child_id) {
    const child = rankMap.get(String(rank.right_child_id));
    if (child && !visited.has(String(rank.right_child_id))) {
      layoutDFS(child, x + 300, y + 100, visited, rankMap, nodeMap);
    }
  }
}

function buildNodesAndEdges(skillTree: SkillTree): { loadedNodes: Node<RankData>[]; loadedEdges: Edge[] } {
  const ranks = skillTree?.ranks || [];

  const loadedNodes: Node<RankData>[] = ranks.map(r => ({
    id: String(r.id),
    position: { x: 0, y: 0 },
    data: { ...r, id: String(r.id) } as RankData,
    type: 'rankNode',
  }));

  const loadedEdges: Edge[] = [];
  for (const rank of ranks) {
    if (rank.left_child_id) {
      loadedEdges.push({
        id: `edge-${rank.id}-left-${rank.left_child_id}`,
        source: String(rank.id),
        target: String(rank.left_child_id),
        sourceHandle: 'left',
        type: 'default'
      });
    }
    if (rank.right_child_id) {
      loadedEdges.push({
        id: `edge-${rank.id}-right-${rank.right_child_id}`,
        source: String(rank.id),
        target: String(rank.right_child_id),
        sourceHandle: 'right',
        type: 'default'
      });
    }
  }

  const rankMap = buildRankMap(ranks);
  const nodeMap = new Map(loadedNodes.map(n => [n.id, n]));

  const roots = findRoots(ranks);
  let startY = 100;
  for (const root of roots) {
    layoutDFS(
      { ...root, id: String(root.id) } as RankData,
      100,
      startY,
      new Set(),
      rankMap,
      nodeMap
    );
    startY += 250;
  }

  return { loadedNodes, loadedEdges };
}

function FlowSkillsEditor({ skillTree, updateStatus }: FlowSkillsEditorProps) {
  const dispatch = useDispatch();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const [skillName, setSkillName] = useState('');
  const [skillType, setSkillType] = useState('attack');
  const [skillDesc, setSkillDesc] = useState('');
  const [skillClassLim, setSkillClassLim] = useState('');
  const [skillRaceLim, setSkillRaceLim] = useState('');
  const [skillSubraceLim, setSkillSubraceLim] = useState('');
  const [skillMinLevel, setSkillMinLevel] = useState(1);
  const [skillPurchaseCost, setSkillPurchaseCost] = useState(0);

  const onChangeNode = useCallback((nodeId: string, field: string, value: unknown) => {
    setNodes(prev => prev.map(n =>
      n.id === nodeId ? { ...n, data: { ...n.data, [field]: value } } : n
    ));
  }, [setNodes]);

  const handleDeleteRank = useCallback((nodeId: string) => {
    setNodes(prev => {
      const newNodes = prev.filter(n => n.id !== nodeId);
      return newNodes.map(n => ({
        ...n,
        data: {
          ...n.data,
          left_child_id: n.data.left_child_id === nodeId ? null : n.data.left_child_id,
          right_child_id: n.data.right_child_id === nodeId ? null : n.data.right_child_id
        }
      }));
    });
    setEdges(prev => prev.filter(e =>
      e.source !== nodeId && e.target !== nodeId
    ));
  }, [setNodes, setEdges]);

  const nodeTypes = useMemo(
    () => makeNodeTypes(onChangeNode, handleDeleteRank),
    [onChangeNode, handleDeleteRank]
  );

  useEffect(() => {
    if (!skillTree) return;

    setSkillName(skillTree.name || '');
    setSkillType(skillTree.skill_type || 'attack');
    setSkillDesc(skillTree.description || '');
    setSkillClassLim(skillTree.class_limitations || '');
    setSkillRaceLim(skillTree.race_limitations || '');
    setSkillSubraceLim(skillTree.subrace_limitations || '');
    setSkillMinLevel(skillTree.min_level || 1);
    setSkillPurchaseCost(skillTree.purchase_cost || 0);

    const { loadedNodes, loadedEdges } = buildNodesAndEdges(skillTree);
    setNodes(loadedNodes);
    setEdges(loadedEdges);
  }, [skillTree, setNodes, setEdges]);

  const onConnect = useCallback((params: Connection) => {
    setEdges(eds => addEdge(params, eds));
  setNodes(ns => ns.map(node => {
    if (node.id === params.source) {
      const newData = { ...node.data };
      if (params.sourceHandle === 'left') {
        newData.left_child_id = params.target;
      } else if (params.sourceHandle === 'right') {
        newData.right_child_id = params.target;
      }
      return { ...node, data: newData };
    }
    return node;
  }));
}, [setEdges, setNodes]);

 const handleSave = () => {
  const updatedRanks = nodes.map(n => ({
    ...n.data,
    selfDamage: n.data.selfDamage || [],
    enemyDamage: n.data.enemyDamage || [],
    selfResist: n.data.selfResist || [],
    enemyResist: n.data.enemyResist || [],
    selfDamageBuff: n.data.selfDamageBuff || [],
    enemyDamageBuff: n.data.enemyDamageBuff || [],
    selfComplexEffects: n.data.selfComplexEffects || [],
    enemyComplexEffects: n.data.enemyComplexEffects || [],
    selfStatMods: n.data.selfStatMods || [],
    enemyStatMods: n.data.enemyStatMods || [],
  }));

  const payload = prepareSkillPayload({
    id: skillTree?.id,
    name: skillName,
    skill_type: skillType,
    description: skillDesc,
    class_limitations: skillClassLim,
    race_limitations: skillRaceLim,
    subrace_limitations: skillSubraceLim,
    min_level: skillMinLevel,
    purchase_cost: skillPurchaseCost,
    skill_image: skillTree?.skill_image,
    ranks: updatedRanks
  });

  dispatch(updateSkillFullTree({ skillId: skillTree?.id, payload }) as any)
    .unwrap()
    .then((response: any) => {
      if (response.temp_id_map) {
        const idMap = response.temp_id_map;
        setNodes(prevNodes =>
          prevNodes.map(n => ({
            ...n,
            id: idMap[n.id] ? String(idMap[n.id]) : n.id,
            data: {
              ...n.data,
              id: idMap[n.data.id] || n.data.id,
              left_child_id: idMap[n.data.left_child_id] || n.data.left_child_id,
              right_child_id: idMap[n.data.right_child_id] || n.data.right_child_id
            }
          }))
        );
        setEdges(prevEdges =>
          prevEdges.map(e => ({
            ...e,
            source: idMap[e.source] ? String(idMap[e.source]) : e.source,
            target: idMap[e.target] ? String(idMap[e.target]) : e.target
          }))
        );
      }
    });
};

  let tempIdCounter = 1;
  const generateTempId = () => `temp-${tempIdCounter++}`;

  const addNode = () => {
    const lastNode = nodes[nodes.length - 1];
    const newRank = lastNode
      ? {
          ...cloneRankAsNew(lastNode.data as RankData),
          id: generateTempId(),
          rank_name: 'Новый ранг',
          rank_number: ((lastNode.data as RankData).rank_number || 0) + 1,
        }
      : {
          ...EMPTY_RANK_TEMPLATE,
          id: generateTempId(),
          rank_name: 'Новый ранг',
          damage_entries: [],
          effects: [],
        };

    setNodes(nds => [...nds, {
      id: newRank.id!,
      position: { x: 200, y: 200 },
      data: newRank as RankData,
      type: 'rankNode',
    }]);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%' }}>
      <div style={{ padding: '10px', background: '#fff', borderBottom: '1px solid #ccc' }}>
        {/* Поля навыка */}
        <div className={styles.inputRow}>
          <div className={styles.inputGroup}>
            <label>Название навыка:</label>
            <input
              type="text"
              value={skillName}
              onChange={e => setSkillName(e.target.value)}
            />
          </div>
          <div className={styles.inputGroup}>
            <label>Тип навыка:</label>
            <select value={skillType} onChange={e => setSkillType(e.target.value)}>
              <option value="attack">Атакующий</option>
              <option value="defense">Защитный</option>
              <option value="support">Поддержка</option>
            </select>
          </div>
        </div>

        <div className={styles.inputRow}>
          <div className={styles.inputGroup}>
            <label>Min уровень перса:</label>
            <input
              type="number"
              value={skillMinLevel}
              onChange={e => setSkillMinLevel(+e.target.value)}
            />
          </div>
          <div className={styles.inputGroup}>
            <label>Стоимость покупки:</label>
            <input
              type="number"
              value={skillPurchaseCost}
              onChange={e => setSkillPurchaseCost(+e.target.value)}
            />
          </div>
        </div>

        <div className={styles.inputRow}>
          <div className={styles.inputGroup}>
            <label>Огр. класс:</label>
            <select value={skillClassLim} onChange={e => setSkillClassLim(e.target.value)}>
              <option value="">(нет)</option>
              {CLASS_OPTIONS.map(c => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>
          <div className={styles.inputGroup}>
            <label>Огр. раса:</label>
            <select value={skillRaceLim} onChange={e => setSkillRaceLim(e.target.value)}>
              <option value="">(нет)</option>
              {RACE_OPTIONS.map(r => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>
          <div className={styles.inputGroup}>
            <label>Огр. подраса:</label>
            <select value={skillSubraceLim} onChange={e => setSkillSubraceLim(e.target.value)}>
              <option value="">(нет)</option>
              {SUBRACE_OPTIONS.map(sr => (
                <option key={sr.value} value={sr.value}>{sr.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className={styles.inputGroup}>
          <label>Описание навыка:</label>
          <textarea
            rows={2}
            value={skillDesc}
            onChange={e => setSkillDesc(e.target.value)}
          />
        </div>

        <div style={{ marginTop: '8px' }}>
          <button
            onClick={handleSave}
            disabled={updateStatus === 'loading'}
            className={styles.saveButton}
          >
            {updateStatus === 'loading' ? 'Сохранение...' : 'Сохранить'}
          </button>
          <button
            onClick={addNode}
            style={{ marginLeft: '8px' }}
            className={styles.saveButton}
          >
            + Новый ранг
          </button>
        </div>
      </div>

      <div className={styles.flowContainer}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          nodeTypes={nodeTypes}
          fitView
        >
          <Background variant="dots" gap={12} size={1} />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>
    </div>
  );
}

export default FlowSkillsEditor;
