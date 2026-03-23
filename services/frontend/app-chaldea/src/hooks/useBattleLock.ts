import { useState, useEffect } from 'react';
import axios from 'axios';

interface BattleLockState {
  inBattle: boolean;
  battleId: number | null;
  loading: boolean;
}

/**
 * Hook to check if a character is currently in an active battle.
 * Returns { inBattle, battleId, loading }.
 */
const useBattleLock = (characterId: number | null | undefined): BattleLockState => {
  const [state, setState] = useState<BattleLockState>({
    inBattle: false,
    battleId: null,
    loading: false,
  });

  useEffect(() => {
    if (!characterId) {
      setState({ inBattle: false, battleId: null, loading: false });
      return;
    }

    let cancelled = false;
    setState((prev) => ({ ...prev, loading: true }));

    axios
      .get<{ in_battle: boolean; battle_id: number | null }>(
        `/battles/character/${characterId}/in-battle`
      )
      .then((res) => {
        if (!cancelled) {
          setState({
            inBattle: res.data.in_battle,
            battleId: res.data.battle_id ?? null,
            loading: false,
          });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState({ inBattle: false, battleId: null, loading: false });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [characterId]);

  return state;
};

export default useBattleLock;
