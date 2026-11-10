import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { parsePositiveId, useSearchParamsPatch } from './urlParams';

/**
 * FEAT-208/210 — `?<param>=<id|new>&tab=<key>`: the expanded element of a list lives in the URL.
 *
 * - `target` — parsed open element: `number` id, `'new'` (create plate) or `null` (closed / garbage)
 * - `rawTarget` — raw param value (`rawTarget !== null && target === null` ⇒ garbage → `normalize(null)`)
 * - `tab` — parsed tab (`null` when absent or rejected by `isTabKey`)
 * - `open(target, tab = defaultTab)`, `setTab(tab)`, `close()` — push a history entry (back works)
 * - `normalize(target, tab = defaultTab)` — the same write with `replace` (silent URL fixes)
 *
 * The page decides which tabs are available for the element and normalizes an unavailable `tab`.
 */

export type PanelTarget = number | 'new';

const TAB_PARAM = 'tab';

const parseTarget = (raw: string | null): PanelTarget | null => (raw === 'new' ? 'new' : parsePositiveId(raw));

export const usePanelUrlState = <K extends string>(
  param: string,
  isTabKey: (value: string | null) => value is K,
  defaultTab: K,
) => {
  const [searchParams] = useSearchParams();
  const patch = useSearchParamsPatch();

  const rawTarget = searchParams.get(param);
  const rawTab = searchParams.get(TAB_PARAM);
  const target = useMemo(() => parseTarget(rawTarget), [rawTarget]);
  const tab: K | null = isTabKey(rawTab) ? rawTab : null;

  const write = useCallback(
    (next: PanelTarget | null, nextTab: K | null, replace: boolean) => {
      patch(
        next === null
          ? { [param]: null, [TAB_PARAM]: null }
          : { [param]: String(next), [TAB_PARAM]: nextTab ?? defaultTab },
        replace,
      );
    },
    [patch, param, defaultTab],
  );

  const open = useCallback(
    (next: PanelTarget, nextTab: K = defaultTab) => write(next, nextTab, false),
    [write, defaultTab],
  );
  const setTab = useCallback(
    (nextTab: K) => {
      if (target !== null) write(target, nextTab, false);
    },
    [target, write],
  );
  const close = useCallback(() => write(null, null, false), [write]);
  const normalize = useCallback(
    (next: PanelTarget | null, nextTab: K | null = defaultTab) => write(next, nextTab, true),
    [write, defaultTab],
  );

  return { target, rawTarget, tab, rawTab, open, setTab, close, normalize };
};
