import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  DEFAULT_FAME_TIER_NAMES,
  FAME_TIER_CODES,
  fetchFameTierNames,
  fetchShadowSettings,
  type ShadowSettingsData,
} from '../../../api/shadowAdmin';
import { apiErrorMessage } from '../../../api/errors';
import type { TierOption } from './useReputationRefs';

/** Seed infamy names: used until the live settings load (codes are fixed). */
const DEFAULT_INFAMY_TIER_NAMES: Record<string, string> = {
  none: 'О вас не говорят',
  whispers: 'Шёпот в тавернах',
  rumored: 'О вас ходят слухи',
  notorious: 'Дурная слава',
  dreaded: 'Имя, которое произносят шёпотом',
};

const DEFAULT_FAME_OPTIONS: TierOption[] = FAME_TIER_CODES.map((code) => ({ code, name: DEFAULT_FAME_TIER_NAMES[code] }));

/** `fame:<code>` / `infamy:<code>` → tier name. */
export type RenownTierNames = Record<string, string>;

const defaultNames = (): RenownTierNames => {
  const out: RenownTierNames = {};
  Object.entries(DEFAULT_FAME_TIER_NAMES).forEach(([code, name]) => {
    out[`fame:${code}`] = name;
  });
  Object.entries(DEFAULT_INFAMY_TIER_NAMES).forEach(([code, name]) => {
    out[`infamy:${code}`] = name;
  });
  return out;
};

/** Module-level caches: one request per page; reset after the shadow settings are saved. */
let fameTiersPromise: Promise<TierOption[]> | null = null;
let settingsPromise: Promise<ShadowSettingsData> | null = null;

export const invalidateShadowRefs = () => {
  fameTiersPromise = null;
  settingsPromise = null;
};

const loadFameTiers = (): Promise<TierOption[]> => {
  if (!fameTiersPromise) {
    fameTiersPromise = fetchFameTierNames()
      .then((list) => [...list].sort((a, b) => a.sort_order - b.sort_order).map((t) => ({ code: t.code, name: t.name })))
      .catch((e: unknown) => {
        fameTiersPromise = null;
        throw e;
      });
  }
  return fameTiersPromise;
};

const loadSettings = (): Promise<ShadowSettingsData> => {
  if (!settingsPromise) {
    settingsPromise = fetchShadowSettings().catch((e: unknown) => {
      settingsPromise = null;
      throw e;
    });
  }
  return settingsPromise;
};

/** Fame tier options for the quest gate select (public endpoint — editors without `reputation:read` too). */
export const useFameTierOptions = (): TierOption[] => {
  const [options, setOptions] = useState<TierOption[]>(DEFAULT_FAME_OPTIONS);

  useEffect(() => {
    let cancelled = false;
    loadFameTiers()
      .then((list) => {
        if (!cancelled && list.length > 0) setOptions(list);
      })
      .catch((e) => {
        if (!cancelled) toast.error(apiErrorMessage(e, 'Не удалось загрузить ступени славы'));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return options;
};

/** Live names of both ladders (staff with `reputation:read`) for the renown log; seed names until loaded. */
export const useRenownTierNames = (): RenownTierNames => {
  const [names, setNames] = useState<RenownTierNames>(defaultNames);

  useEffect(() => {
    let cancelled = false;
    loadSettings()
      .then((d) => {
        if (cancelled) return;
        const out = defaultNames();
        d.fame_tiers.forEach((t) => {
          out[`fame:${t.code}`] = t.name;
        });
        d.infamy_tiers.forEach((t) => {
          out[`infamy:${t.code}`] = t.name;
        });
        setNames(out);
      })
      .catch((e) => {
        if (!cancelled) toast.error(apiErrorMessage(e, 'Не удалось загрузить названия ступеней славы'));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return names;
};

export const renownTierName = (names: RenownTierNames, scale: string, code: string): string =>
  names[`${scale}:${code}`] ?? code;
