// Types for Admin Class Tree Editor — matching backend Pydantic schemas (Section 3.5)

// --- Tree Node Skill (inside a node) ---

export interface TreeNodeSkillEntry {
  skill_id: number;
  sort_order: number;
}

export interface TreeNodeSkillRead {
  id: number;
  skill_id: number;
  sort_order: number;
  skill_name: string | null;
  skill_type: string | null;
  skill_image: string | null;
}

// --- Tree Node in full tree request/response ---

export interface TreeNodeInTree {
  id: number | string; // int for existing, "temp-N" for new
  level_ring: number;
  position_x: number;
  position_y: number;
  name: string;
  description: string | null;
  node_type: string; // 'regular' | 'root' | 'subclass_choice'
  icon_image: string | null;
  sort_order: number;
  skills: TreeNodeSkillEntry[];
}

export interface TreeNodeInTreeResponse {
  id: number;
  tree_id: number;
  level_ring: number;
  position_x: number;
  position_y: number;
  name: string;
  description: string | null;
  node_type: string;
  icon_image: string | null;
  sort_order: number;
  skills: TreeNodeSkillRead[];
}

// --- Connection ---

export interface TreeNodeConnectionInTree {
  id: number | string | null;
  from_node_id: number | string;
  to_node_id: number | string;
}

// --- Class Skill Tree ---

export interface ClassSkillTreeRead {
  id: number;
  class_id: number;
  name: string;
  description: string | null;
  tree_type: string;
  parent_tree_id: number | null;
  subclass_name: string | null;
  tree_image: string | null;
}

export interface ClassSkillTreeCreate {
  class_id: number;
  name: string;
  description?: string | null;
  tree_type?: string;
  parent_tree_id?: number | null;
  subclass_name?: string | null;
  tree_image?: string | null;
}

// --- Full Tree ---

export interface FullClassTreeResponse {
  id: number;
  class_id: number;
  name: string;
  description: string | null;
  tree_type: string;
  parent_tree_id: number | null;
  subclass_name: string | null;
  tree_image: string | null;
  nodes: TreeNodeInTreeResponse[];
  connections: TreeNodeConnectionInTree[];
}

export interface FullClassTreeUpdateRequest {
  id: number;
  class_id: number;
  name: string;
  description: string | null;
  tree_type: string;
  parent_tree_id: number | null;
  subclass_name: string | null;
  tree_image: string | null;
  nodes: TreeNodeInTree[];
  connections: TreeNodeConnectionInTree[];
}

// --- Bulk save response ---

export interface SaveClassTreeResponse {
  detail: string;
  temp_id_map: Record<string, number>;
}

// --- Skill list item (reused from skills admin) ---

export interface SkillListItem {
  id: number;
  name: string;
  skill_type: string;
  skill_image: string | null;
}

// --- Redux state ---

export interface ClassTreeAdminState {
  treeList: ClassSkillTreeRead[];
  selectedFullTree: FullClassTreeResponse | null;
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  updateStatus: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
}

// --- Level ring options ---

export const LEVEL_RING_OPTIONS = [
  { value: 1, label: '1 (Старт)' },
  { value: 5, label: '5' },
  { value: 10, label: '10' },
  { value: 15, label: '15' },
  { value: 20, label: '20' },
  { value: 25, label: '25' },
  { value: 30, label: '30' },
  { value: 35, label: '35' },
  { value: 40, label: '40' },
  { value: 45, label: '45' },
  { value: 50, label: '50' },
] as const;

export const NODE_TYPE_OPTIONS = [
  { value: 'regular', label: 'Обычный' },
  { value: 'root', label: 'Корневой' },
  { value: 'subclass_choice', label: 'Выбор подкласса' },
] as const;

export const CLASS_OPTIONS = [
  { value: 1, label: 'Воин' },
  { value: 2, label: 'Плут' },
  { value: 3, label: 'Маг' },
] as const;

export const TREE_TYPE_OPTIONS = [
  { value: 'class', label: 'Дерево класса' },
  { value: 'subclass', label: 'Дерево подкласса' },
] as const;
