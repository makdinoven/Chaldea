import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

/* FEAT-210 — URL helpers shared by the ExpandableList hooks. */

const POSITIVE_INT_RE = /^[1-9]\d*$/;

/** Strict positive integer parse (garbage → null). */
export const parsePositiveId = (raw: string | null): number | null => {
  if (!raw || !POSITIVE_INT_RE.test(raw)) return null;
  const id = Number(raw);
  return Number.isSafeInteger(id) ? id : null;
};

export type ParamPatch = Record<string, string | null | undefined>;

/**
 * Returns `patch(changes, replace)` that sets / deletes the given query params and keeps
 * all the others. The base is the live `window.location.search` (BrowserRouter updates it
 * synchronously), so several patches fired in one effect cycle by different hooks
 * (panel normalisation, filter garbage reset) don't overwrite each other.
 */
export const useSearchParamsPatch = () => {
  const [, setSearchParams] = useSearchParams();
  return useCallback(
    (changes: ParamPatch, replace: boolean) => {
      setSearchParams(
        () => {
          const next = new URLSearchParams(window.location.search);
          Object.entries(changes).forEach(([key, value]) => {
            if (value === null || value === undefined) next.delete(key);
            else next.set(key, value);
          });
          return next;
        },
        { replace },
      );
    },
    [setSearchParams],
  );
};
