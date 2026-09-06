/**
 * FEAT-154 — public surface of the passport module (task #16).
 * Downstream tasks (#17-#22, #32) import from here, not from the files.
 */

export { default as CharacterPassport } from './CharacterPassport';
export { default } from './CharacterPassport';

export {
  fromWizardDraft,
  fromCharacterPublic,
  fromCharacterListItem,
  fromModerationRequest,
} from './adapters';

export {
  computeDerivedStats,
  formatDerivedValue,
  PASSPORT_DERIVED_ROWS,
  PASSPORT_STAT_LABELS,
  POINTS_PER_LEVEL,
  PRESET_TOTAL_POINTS,
} from './derived';

export { PASSPORT_STAT_ORDER } from './types';

export type {
  DerivedStats,
  PassportAudience,
  PassportData,
  PassportExtras,
  PassportKit,
  PassportModerationRequest,
  PassportOrigin,
  PassportStats,
  PassportStatus,
  PassportTenure,
  PassportVariant,
  PassportWizardDraft,
  ResolvedItem,
  ResolvedSkill,
} from './types';
