import { useCallback, useEffect, useState } from 'react';
import { BACKPACK_CHANGED, fetchBackpack, type BackpackState } from '../../../api/backpack';
import { apiErrorMessage } from '../../../api/errors';

/** The character's camp backpack, reloaded whenever any view on the page changes it. */
const useBackpack = (characterId: number | null | undefined, reloadKey?: unknown) => {
  const [state, setState] = useState<BackpackState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!characterId) return;
    try {
      setState(await fetchBackpack(characterId));
      setError(null);
    } catch (e) {
      setError(apiErrorMessage(e, 'Не удалось загрузить походный рюкзак'));
    }
  }, [characterId]);

  useEffect(() => {
    void reload();
  }, [reload, reloadKey]);

  useEffect(() => {
    const onChange = () => void reload();
    window.addEventListener(BACKPACK_CHANGED, onChange);
    return () => window.removeEventListener(BACKPACK_CHANGED, onChange);
  }, [reload]);

  return { state, error, reload };
};

export default useBackpack;
