import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  DEFAULT_TIER_NAMES,
  REPUTATION_TIER_CODES,
  fetchReputationNpcRoles,
  fetchReputationSettings,
  type ReputationRoleWeight,
} from '../../../api/reputationAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { useAppSelector } from '../../../redux/store';
import { selectPermissions } from '../../../redux/slices/userSlice';
import { hasPermission } from '../../../utils/permissions';

export interface TierOption {
  code: string;
  name: string;
}

/** Position of a tier code in the fixed low → high order. */
export const tierIndex = (code: string): number => (REPUTATION_TIER_CODES as readonly string[]).indexOf(code);

const DEFAULT_OPTIONS: TierOption[] = REPUTATION_TIER_CODES.map((code) => ({ code, name: DEFAULT_TIER_NAMES[code] }));

/**
 * Module-level cache: every gate select on a page (quest editor, NPC form, plots, banks, teleport links) shares one
 * request. Reset after the settings are saved so renamed tiers show up at once.
 */
let tiersPromise: Promise<TierOption[]> | null = null;
let rolesPromise: Promise<ReputationRoleWeight[]> | null = null;

export const invalidateReputationRefs = () => {
  tiersPromise = null;
  rolesPromise = null;
};

const loadTiers = (): Promise<TierOption[]> => {
  if (!tiersPromise) {
    tiersPromise = fetchReputationSettings()
      .then((s) =>
        [...s.tiers]
          .sort((a, b) => tierIndex(a.code) - tierIndex(b.code))
          .map((t) => ({ code: t.code, name: t.name })),
      )
      .catch((e: unknown) => {
        tiersPromise = null;
        throw e;
      });
  }
  return tiersPromise;
};

const loadRoles = (): Promise<ReputationRoleWeight[]> => {
  if (!rolesPromise) {
    rolesPromise = fetchReputationNpcRoles().catch((e: unknown) => {
      rolesPromise = null;
      throw e;
    });
  }
  return rolesPromise;
};

/**
 * Tier options for the gate selects. Without `reputation:read` (e.g. an editor of NPCs) the seed names are used —
 * the codes are fixed, so the stored value is still correct; only a renamed tier would show its old name.
 */
export const useReputationTiers = (): TierOption[] => {
  const canRead = hasPermission(useAppSelector(selectPermissions), 'reputation:read');
  const [options, setOptions] = useState<TierOption[]>(DEFAULT_OPTIONS);

  useEffect(() => {
    if (!canRead) return undefined;
    let cancelled = false;
    loadTiers()
      .then((list) => {
        if (!cancelled && list.length > 0) setOptions(list);
      })
      .catch((e) => {
        if (!cancelled) toast.error(apiErrorMessage(e, 'Не удалось загрузить ступени репутации'));
      });
    return () => {
      cancelled = true;
    };
  }, [canRead]);

  return options;
};

/** NPC-role kill weights (`role → points`, `*` = any other role); null while loading or without `reputation:read`. */
export const useReputationRoleWeights = (): Record<string, number> | null => {
  const canRead = hasPermission(useAppSelector(selectPermissions), 'reputation:read');
  const [weights, setWeights] = useState<Record<string, number> | null>(null);

  useEffect(() => {
    if (!canRead) return undefined;
    let cancelled = false;
    loadRoles()
      .then((list) => {
        if (!cancelled) setWeights(Object.fromEntries(list.map((r) => [r.role, r.points])));
      })
      .catch((e) => {
        if (!cancelled) toast.error(apiErrorMessage(e, 'Не удалось загрузить веса ролей НПС'));
      });
    return () => {
      cancelled = true;
    };
  }, [canRead]);

  return weights;
};

/** The kill weight an NPC of `role` gets without its own override (same rule as `reputation_core.kill_points`). */
export const roleKillWeight = (weights: Record<string, number> | null, role: string | null | undefined): number | null => {
  if (!weights) return null;
  if (role && role in weights) return weights[role];
  if ('*' in weights) return weights['*'];
  return null;
};
