import { useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useSearchParamsPatch } from './urlParams';

/**
 * FEAT-209/210 — «Готовность» list filter in `?ready=1|0` (replace, other params kept,
 * garbage removed silently). `ready`: `true` = only ready, `false` = only not ready, `null` = all.
 * Render it with `ReadyFilterSelect`; reset the page to 1 in its `onChange`.
 */

const READY_PARAM = 'ready';

const parseReady = (raw: string | null): boolean | null => {
  if (raw === '1') return true;
  if (raw === '0') return false;
  return null;
};

export const useReadyFilterUrlState = () => {
  const [searchParams] = useSearchParams();
  const patch = useSearchParamsPatch();
  const rawReady = searchParams.get(READY_PARAM);
  const ready = parseReady(rawReady);

  // Garbage → removed silently
  useEffect(() => {
    if (rawReady !== null && parseReady(rawReady) === null) patch({ [READY_PARAM]: null }, true);
  }, [rawReady, patch]);

  const setReady = useCallback(
    (value: boolean | null) => patch({ [READY_PARAM]: value === null ? null : value ? '1' : '0' }, true),
    [patch],
  );

  return { ready, setReady };
};
