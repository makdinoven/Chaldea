import { formatServerDateTime } from '../../../utils/serverDate';

/**
 * FEAT-209/210 — the admin «Готов» mark in a section-independent shape.
 * NPCs store it as `npc_ready*`, items / mob templates as `admin_ready*`;
 * convert with `toReadyMark` / `adminReadyMark` before passing it to the kit.
 */
export interface ReadyMark {
  ready: boolean;
  /** UTC-naive server datetime, set when the flag became true */
  at: string | null;
  /** Username snapshot of who set the flag */
  by: string | null;
}

export const toReadyMark = (
  ready: boolean | null | undefined,
  at: string | null | undefined,
  by: string | null | undefined,
): ReadyMark => ({ ready: !!ready, at: at ?? null, by: by ?? null });

/** `{admin_ready, admin_ready_at, admin_ready_by}` (items, mob templates) → ReadyMark. */
export const adminReadyMark = (row: {
  admin_ready?: boolean | null;
  admin_ready_at?: string | null;
  admin_ready_by?: string | null;
}): ReadyMark => toReadyMark(row.admin_ready, row.admin_ready_at, row.admin_ready_by);

/** Tooltip «Отметил <имя>, <дата>» (or null when nothing is known). */
export const readyTooltip = (by: string | null, at: string | null): string | null => {
  if (!by && !at) return null;
  const parts = [by ? `Отметил ${by}` : 'Отмечен', at ? formatServerDateTime(at) : null].filter(Boolean);
  return parts.join(', ');
};
