import axios from 'axios';
import { apiErrorMessage } from './errors';

/**
 * FEAT-154 — starter kits keyed by the pair (class × origin), rules 12a-12d.
 *
 * `origin_id = 0` is the sentinel for «class default» (D16) — it is NOT a
 * nullable column, because MySQL treats NULLs as distinct inside a UNIQUE index
 * and two competing defaults would then be accepted.
 */

/** One line of a kit. Contents are id-only — resolve names via `bulk.ts`. */
export interface StarterKitItem {
  item_id: number;
  quantity: number;
}

export interface StarterKitSkill {
  skill_id: number;
}

/** A stored kit row (`GET /characters/starter-kits`, `PUT` responses). */
export interface StarterKit {
  id: number;
  class_id: number;
  /** 0 = class default, >0 = override for that origin. */
  origin_id: number;
  items: StarterKitItem[];
  skills: StarterKitSkill[];
  currency_amount: number;
}

/**
 * How the resolver arrived at the kit it returned.
 *
 * ⚠️ Note N10: asking for `origin_id=0` directly is reported as `"exact"`, not
 * `"class_default"` — nothing was fallen back to.
 */
export type StarterKitResolvedFrom = 'exact' | 'class_default' | 'none';

/** Result of `GET /characters/starter-kits/resolve` — and the shape frozen
 *  into `characters.granted_kit` at approval (plus `granted_at`). */
export interface StarterKitResolved {
  class_id: number;
  origin_id: number;
  resolved_from: StarterKitResolvedFrom;
  items: StarterKitItem[];
  skills: StarterKitSkill[];
  currency_amount: number;
}

/** Body of both kit `PUT` endpoints. */
export interface StarterKitUpdatePayload {
  items: StarterKitItem[];
  skills: StarterKitSkill[];
  currency_amount: number;
}

export interface StarterKitCoverageClass {
  id_class: number;
  name: string;
  has_default: boolean;
}

export interface StarterKitCoverageOverride {
  class_id: number;
  origin_id: number;
}

/** `GET /characters/starter-kits/coverage` — the content-seeding checklist. */
export interface StarterKitCoverage {
  classes: StarterKitCoverageClass[];
  overrides: StarterKitCoverageOverride[];
}

// ── Public reads ────────────────────────────────────────────────────────────

/**
 * Without `includeOrigins` this returns only the class defaults (`origin_id=0`),
 * i.e. exactly the row set that existed before FEAT-154 — backward compatible.
 */
export const fetchStarterKits = async (includeOrigins = false): Promise<StarterKit[]> => {
  try {
    const { data } = await axios.get<StarterKit[]>('/characters/starter-kits', {
      params: includeOrigins ? { include_origins: true } : undefined,
    });
    return data ?? [];
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось загрузить стартовые наборы.'));
  }
};

/**
 * What the wizard's «Путь» step shows: exact pair → class default → empty.
 * `originId` is optional; omitting it (or passing 0) resolves the class default.
 * **404** when the class does not exist.
 */
export const resolveStarterKit = async (
  classId: number,
  originId?: number | null,
): Promise<StarterKitResolved> => {
  try {
    const { data } = await axios.get<StarterKitResolved>('/characters/starter-kits/resolve', {
      params: { class_id: classId, ...(originId ? { origin_id: originId } : {}) },
    });
    return data;
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось загрузить стартовый набор.'));
  }
};

// ── Admin (`characters:update`) ─────────────────────────────────────────────

export const fetchStarterKitCoverage = async (): Promise<StarterKitCoverage> => {
  try {
    const { data } = await axios.get<StarterKitCoverage>('/characters/starter-kits/coverage');
    return data;
  } catch (error) {
    throw new Error(
      apiErrorMessage(error, 'Не удалось загрузить заполненность стартовых наборов.'),
    );
  }
};

/** Writes the class default (`origin_id = 0`). Unchanged pre-FEAT-154 endpoint. */
export const updateStarterKitDefault = async (
  classId: number,
  payload: StarterKitUpdatePayload,
): Promise<StarterKit> => {
  try {
    const { data } = await axios.put<StarterKit>(`/characters/starter-kits/${classId}`, payload);
    return data;
  } catch (error) {
    throw new Error(apiErrorMessage(error, 'Не удалось сохранить стартовый набор класса.'));
  }
};

/**
 * Creates or updates the override for one (class, origin) pair.
 * **400** when `originId` is 0 — the class default has its own endpoint.
 */
export const updateStarterKitForOrigin = async (
  classId: number,
  originId: number,
  payload: StarterKitUpdatePayload,
): Promise<StarterKit> => {
  try {
    const { data } = await axios.put<StarterKit>(
      `/characters/starter-kits/${classId}/origins/${originId}`,
      payload,
    );
    return data;
  } catch (error) {
    throw new Error(
      apiErrorMessage(error, 'Не удалось сохранить стартовый набор для происхождения.'),
    );
  }
};

/**
 * Removes an override so the pair falls back to the class default again.
 * **404** when no override exists.
 */
export const deleteStarterKitOverride = async (
  classId: number,
  originId: number,
): Promise<{ message: string }> => {
  try {
    const { data } = await axios.delete<{ message: string }>(
      `/characters/starter-kits/${classId}/origins/${originId}`,
    );
    return data;
  } catch (error) {
    throw new Error(
      apiErrorMessage(error, 'Не удалось удалить переопределение стартового набора.'),
    );
  }
};
