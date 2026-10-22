/*
  What a node's page in a book says, and what can be done from it. Built
  outside the 3D scene (see useNodePage), inked onto the left-hand page inside
  it (see nodePageInk).
*/

export type NodePageTone = 'chosen' | 'available' | 'blocked' | 'muted';

export interface NodePageSkill {
  skillId: number;
  name: string;
  /** "Атака", "Защита", … */
  typeLabel: string | null;
  /** Same-origin URL of the skill's picture, if it has one the page can draw. */
  image: string | null;
  learned: boolean;
  /** Being learned right now. */
  busy: boolean;
}

export interface NodePageModel {
  nodeId: number;
  title: string;
  /** "Корневой узел · Уровень 1" */
  meta: string;
  description: string | null;
  status: { text: string; tone: NodePageTone };
  /** The one large action the page offers, if any. */
  action: { kind: 'choose' | 'subclass'; label: string; busy: boolean } | null;
  /** Skills listed with buttons (own, chosen node), plainly (another class), or not at all. */
  skills: NodePageSkill[];
  skillsMode: 'learnable' | 'listed' | 'hidden';
  /** A short line of advice under everything else. */
  hint: string | null;
  canReset: boolean;
}

export type NodePageAction =
  | { kind: 'close' }
  | { kind: 'choose' }
  | { kind: 'subclass' }
  | { kind: 'learn'; skillId: number }
  | { kind: 'upgrade'; skillId: number }
  | { kind: 'reset' };

/** Stable key for an action, for hover and hit-testing. */
export const actionKey = (a: NodePageAction) => ('skillId' in a ? `${a.kind}:${a.skillId}` : a.kind);
