/**
 * FEAT-216 — customs on the player side (character-service, feature file 3.7 C1–C5).
 * The officer job, the «Таможенник» window and «Досмотреть» a caravan the officer was alerted about.
 */

/** An officer's own active service (C1 `job`, C2/C4 `job`). */
export interface CustomsJob {
  country_id: number;
  country_name: string | null;
  /** Only `active` jobs are returned. */
  status: 'active' | string;
  enlisted_at: string;
  /** Seized contraband caravans. */
  seizures: number;
  /** Marks earned from seizures. */
  earned: number;
}

export interface CustomsOfficerParams {
  /** Officers' share of the fine (0..1). */
  officer_share: number;
  /** How long a detected caravan waits for «Досмотреть», minutes. */
  alert_minutes: number;
}

/** C1 — the «Таможенник» window. */
export interface CustomsOfficerView {
  npc_id: number;
  country_id: number;
  country_name: string | null;
  location_id: number;
  job: CustomsJob | null;
  can_enlist: boolean;
  /** Russian refusal text when `can_enlist` is false. */
  reason: string | null;
  params: CustomsOfficerParams;
}

/** C2 201 / C4 body. */
export interface CustomsJobWrap {
  job: CustomsJob | null;
}

/** C3 body. */
export interface CustomsResignResponse {
  ok: boolean;
}

/** C5 body. */
export interface CustomsInspectRequest {
  character_id: number;
  group: boolean;
}

/** C5 201 body. */
export interface CustomsInspectResponse {
  raid_id: number;
  battle_id: number;
}
