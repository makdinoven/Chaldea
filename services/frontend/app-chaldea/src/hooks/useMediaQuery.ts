import { useEffect, useState } from 'react';

/**
 * Tracks a CSS media query. Returns false during SSR-less first paint only if
 * the query genuinely does not match, so there is no layout flash.
 */
const useMediaQuery = (query: string): boolean => {
  const [matches, setMatches] = useState<boolean>(
    () => typeof window !== 'undefined' && window.matchMedia(query).matches,
  );

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mql = window.matchMedia(query);
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches);
    setMatches(mql.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);

  return matches;
};

export default useMediaQuery;
