/**
 * Shared post/gate constants for the location editor surfaces (FEAT-159, T5a).
 *
 * Extracted verbatim from `PostCreateForm.tsx` — **no behaviour change**. The
 * reason for the move is that `PostEditModal.tsx` has to show the very same
 * character counter, and the counter is the player's only preview of a rule the
 * server enforces (`crud.required_symbols_for_gates`,
 * `services/locations-service/app/crud.py`). Two copies of the cost table would
 * drift, and a drifted counter promises gates the server then refuses.
 *
 * Keep this file free of React and of component-specific state: it is pure data
 * plus one pure function.
 */

/** Minimum plain length of any post — mirrors `crud.MIN_POST_LENGTH`. */
export const MIN_POST_LENGTH = 300;

/**
 * Cost of a gate target whose `action_type` is not in `GATE_COST`.
 *
 * Mirrors the server's `GATE_SYMBOL_COST.get(action_type, 500)`
 * (`crud.required_symbols_for_gates`). It must NOT be 0: a post may carry a
 * gate type this table does not list (`pvp` is created by other paths, and
 * `GATED_POST_TYPES` may grow), and pricing it at 0 would let the counter say
 * «можно сохранять» on a text the server then refuses.
 */
export const DEFAULT_GATE_COST = 500;

/** FEAT-145 v2: symbol cost per gate target. Mirrors `crud.GATE_SYMBOL_COST`. */
export const GATE_COST: Record<string, number> = {
  combat: 200,
  pvp: 500,
  npc_dialogue: 500,
  gathering: 500,
  dungeon: 500,
};

export const GATE_LABEL: Record<string, string> = {
  combat: 'Нападение на мобов',
  pvp: 'PvP',
  npc_dialogue: 'Диалог с НПС',
  gathering: 'Сбор ресурсов',
  dungeon: 'Вход в подземелье',
};

/** FEAT-152: per-action visual accents for the gate grid (mock language). */
export const GATE_STYLE: Record<string, { icon: string; activeCls: string }> = {
  combat: { icon: '⚔', activeCls: 'border-stat-hp/40 bg-stat-hp/10 text-stat-hp' },
  npc_dialogue: { icon: '💬', activeCls: 'border-site-blue/40 bg-site-blue/10 text-site-blue' },
  gathering: { icon: '⛏', activeCls: 'border-stat-energy/40 bg-stat-energy/10 text-stat-energy' },
  dungeon: { icon: '🏰', activeCls: 'border-rarity-epic/40 bg-rarity-epic/10 text-rarity-epic' },
  pvp: { icon: '⚔', activeCls: 'border-gold/20 bg-gold/10 text-gold/90' },
};

/** Style for a gate type this table does not know — never a missing lookup. */
export const FALLBACK_GATE_STYLE = {
  icon: '•',
  activeCls: 'border-gold/20 bg-gold/10 text-gold/90',
};

export const GATE_ORDER = ['combat', 'npc_dialogue', 'gathering', 'dungeon'] as const;

export interface GateOption {
  id: number;
  name: string;
}

export type GateOptions = Partial<Record<string, GateOption[]>>;

export interface PostGate {
  action_type: string;
  targets: number[];
}

/**
 * Plain length of the post **exactly as the backend counts it**.
 *
 * This deliberately mirrors `crud.strip_html_tags`
 * (`services/locations-service/app/crud.py`) byte-for-byte, including its two
 * known defects: no separator at block boundaries (`<p>Один</p><p>Два</p>` ->
 * `"ОдинДва"`) and no entity decoding. It feeds `charCount`, which drives the
 * minimum-length and gate thresholds, so if it stopped matching the server the
 * UI would promise gates the server then refuses.
 *
 * Do NOT "fix" it and do NOT replace it with `htmlToSpellText` — that walker is
 * the correct model and is used only for spell-checking (FEAT-157, section 3.3).
 * Correcting the backend twin changes post XP and every gate threshold, i.e. it
 * is a balance decision; it is tracked in `docs/ISSUES.md`.
 */
export const stripHtmlTags = (html: string) => html.replace(/<[^>]*>/g, '').trim();

/** True when the editor holds nothing but markup. */
export const isContentEmpty = (html: string) => stripHtmlTags(html).length === 0;

/**
 * Symbols the server will demand for this text + gate selection.
 *
 * Mirror of `crud.required_symbols_for_gates`: the floor is `MIN_POST_LENGTH`,
 * and every gate costs `GATE_COST[action_type] * max(1, targets)`, with an
 * unknown type falling back to `DEFAULT_GATE_COST` exactly as the server's
 * `GATE_SYMBOL_COST.get(action_type, 500)` does.
 *
 * `GATE_ORDER` is the *create* form's menu, not this function's domain: the
 * edit modal prices gate types the form never offers (a post can hold a `pvp`
 * gate), so every type reaching here is priced, none is silently free.
 */
export const requiredSymbolsForGates = (gates: PostGate[]): number =>
  Math.max(
    MIN_POST_LENGTH,
    gates.reduce(
      (sum, g) =>
        sum + (GATE_COST[g.action_type] ?? DEFAULT_GATE_COST) * Math.max(1, g.targets.length),
      0,
    ),
  );
