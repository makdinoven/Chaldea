import axios from 'axios';
import { apiErrorMessage } from './errors';

/**
 * FEAT-154 (D10) — public bulk-resolve endpoints.
 *
 * `GET /inventory/items/bulk?ids=` and `GET /skills/bulk?ids=` let the wizard
 * and the passport render a starter kit (which is stored id-only) in a couple
 * of requests instead of one request per item / per skill.
 */

/** Hard cap enforced by both backends. Larger lists are split into chunks. */
export const BULK_MAX_IDS = 100;

/**
 * One item, as returned by `GET /inventory/items/bulk`.
 *
 * ⚠️ Note N2: the backend deliberately maps its own column names
 * (`image`, `item_rarity`, `item_type`) onto these response keys. These key
 * names ARE the contract — do not "fix" them.
 */
export interface ItemBulk {
  id: number;
  name: string;
  description: string | null;
  image_url: string | null;
  rarity: string | null;
  type: string | null;
}

/**
 * One skill, as returned by `GET /skills/bulk`.
 *
 * ⚠️ Note N1: a skill has **no `class_id`**. The `skills` table has no class FK;
 * scoping is expressed by the comma-separated `class_limitations` string.
 * Never read `skill.class_id` — it does not exist.
 */
export interface SkillBulk {
  id: number;
  name: string;
  description: string | null;
  icon_url: string | null;
  class_limitations: string | null;
}

/** Deduplicates, drops non-positive ids and splits into ≤100-id chunks. */
const toChunks = (ids: number[]): number[][] => {
  const unique = Array.from(new Set(ids.filter((id) => Number.isInteger(id) && id > 0)));
  const chunks: number[][] = [];
  for (let i = 0; i < unique.length; i += BULK_MAX_IDS) {
    chunks.push(unique.slice(i, i + BULK_MAX_IDS));
  }
  return chunks;
};

const fetchBulk = async <T>(url: string, ids: number[], fallback: string): Promise<T[]> => {
  const chunks = toChunks(ids);
  // An empty `ids` param is a 400 on the backend — never send the request at all.
  if (chunks.length === 0) return [];

  try {
    const responses = await Promise.all(
      chunks.map((chunk) => axios.get<T[]>(url, { params: { ids: chunk.join(',') } })),
    );
    return responses.flatMap((response) => response.data ?? []);
  } catch (error) {
    // Both 400 (malformed ids) and 422 (missing ids) are possible — see N11.
    throw new Error(apiErrorMessage(error, fallback));
  }
};

/**
 * Resolves items by id. Unknown ids are silently omitted by the backend, so the
 * result may be shorter than the input — callers must handle a missing id.
 */
export const fetchItemsBulk = (ids: number[]): Promise<ItemBulk[]> =>
  fetchBulk<ItemBulk>('/inventory/items/bulk', ids, 'Не удалось загрузить предметы.');

/** Resolves skills by id. Unknown ids are silently omitted by the backend. */
export const fetchSkillsBulk = (ids: number[]): Promise<SkillBulk[]> =>
  fetchBulk<SkillBulk>('/skills/bulk', ids, 'Не удалось загрузить навыки.');

/** Convenience: id → item, for rendering a kit without repeated `.find()`. */
export const indexById = <T extends { id: number }>(rows: T[]): Map<number, T> =>
  new Map(rows.map((row) => [row.id, row]));
