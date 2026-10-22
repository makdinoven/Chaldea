import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { fetchCharacterPublic } from '../../api/charactersPublic';
import { fetchOrigins } from '../../api/origins';
import { fetchGameTime } from '../../redux/actions/gameTimeActions';
import { selectCurrentGameYear } from '../../redux/slices/gameTimeSlice';
import { fromCharacterPublic } from '../CommonComponents/CharacterPassport/adapters';
import type { PassportData } from '../CommonComponents/CharacterPassport/types';

/**
 * The player's own Скиталец passport, for the paper copy lying beside their
 * book on the table: the same record the characters list shows, built the
 * same way, plus the in-game year its tenure is counted to.
 */
const useCharacterDossier = (characterId: number | null, enabled: boolean) => {
  const dispatch = useAppDispatch();
  const currentGameYear = useAppSelector(selectCurrentGameYear);
  const gameTimeLoaded = useAppSelector((state) => state.gameTime.computed !== null);
  const [passport, setPassport] = useState<PassportData | null>(null);

  useEffect(() => {
    if (enabled && !gameTimeLoaded) dispatch(fetchGameTime());
  }, [enabled, gameTimeLoaded, dispatch]);

  useEffect(() => {
    if (!enabled || !characterId) {
      setPassport(null);
      return;
    }
    let cancelled = false;
    Promise.all([fetchCharacterPublic(characterId), fetchOrigins()])
      .then(([character, origins]) => {
        if (!cancelled) setPassport(fromCharacterPublic(character, { origins }));
      })
      .catch((err: unknown) => {
        if (!cancelled) toast.error(err instanceof Error ? err.message : 'Не удалось загрузить паспорт Скитальца');
      });
    return () => {
      cancelled = true;
    };
  }, [characterId, enabled]);

  return { passport, currentGameYear };
};

export default useCharacterDossier;
