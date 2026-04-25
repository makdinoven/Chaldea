/**
 * Local view-model types for the LocationPage GatheringSection component
 * family (FEAT-128, task #21).
 *
 * The canonical API shapes live in `src/types/gathering.ts` — this file
 * only declares props and small derived types that are specific to the UI
 * layer and not worth surfacing into the global types module.
 */
import type {
  GatheringNode,
  GatheringTool,
  ToolCategory,
} from '../../../../types/gathering';

/** Visual status of a single gathering node card. */
export type NodeUiStatus =
  | 'available'   // is_enabled, bank > 0, can be started
  | 'depleted'    // bank == 0 OR restore_at > now
  | 'occupied'    // single-gather mode and another character holds the slot
  | 'disabled';   // is_enabled=false or admin disabled it

export interface GatheringSectionProps {
  locationId: number;
  characterId: number | null;
  /** Inventory id used for the tool-selection lookup. In this codebase the
   *  /inventory/{id}/items endpoint is keyed by character_id, so callers
   *  should usually pass the same value as `characterId`. */
  inventoryId: number | null;
  /** True when the viewer's character is physically at this location.
   *  Mining is only allowed while the character stands on the location. */
  isCharacterHere: boolean;
  /** Combined lock flag — gathering is disabled when the character is in
   *  battle or already gathering elsewhere. */
  actionsLocked: boolean;
  nodes: GatheringNode[];
  /** Called by the section when a gather completes successfully so the
   *  parent can refresh /client/details and surface fresh bank counters. */
  onGatherSucceeded?: () => void;
}

export interface GatheringNodeCardProps {
  node: GatheringNode;
  characterId: number | null;
  inventoryId: number | null;
  isCharacterHere: boolean;
  actionsLocked: boolean;
  /** Notify parent that this card initiated a gather and the API responded
   *  OK. The parent can then refetch location details. */
  onStarted: () => void;
}

export interface ToolSelectionModalProps {
  node: GatheringNode;
  inventoryId: number;
  characterId: number;
  onClose: () => void;
  /** toolInventoryItemId is null when the user picks "without tool". */
  onConfirm: (toolInventoryItemId: number | null) => Promise<void> | void;
  /** Set while the parent is awaiting the start-gather API call. */
  submitting?: boolean;
}

/** A small derived view model fed from `node` + the wall-clock time so the
 *  card can render the right status without re-deriving on every render. */
export interface NodeStatusVm {
  status: NodeUiStatus;
  restoreRemainingSeconds: number;
  occupiedBy: { name: string; avatar: string | null } | null;
}

export type { GatheringNode, GatheringTool, ToolCategory };
