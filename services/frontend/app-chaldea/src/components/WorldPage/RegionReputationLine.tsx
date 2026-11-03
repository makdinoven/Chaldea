import { useEffect, useState } from 'react';
import { fetchReputation } from '../../api/reputation';
import type { ReputationRegion } from '../../api/reputation';
import { apiErrorMessage } from '../../api/errors';
import { REPUTATION_TONE_TEXT, reputationTone } from '../../utils/reputationTiers';

/**
 * FEAT-197: «Ваша репутация: Свой человек» under the region title on the world map.
 * Rendered only when a character is selected; no numbers, tier name only.
 */

interface RegionReputationLineProps {
  characterId: number;
  regionId: number;
}

const RegionReputationLine = ({ characterId, regionId }: RegionReputationLineProps) => {
  const [entry, setEntry] = useState<ReputationRegion | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setEntry(null);
    setError(null);
    fetchReputation(characterId, regionId)
      .then((data) => {
        if (!cancelled) setEntry(data.regions[0] ?? null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(apiErrorMessage(err, 'Не удалось загрузить репутацию в регионе'));
      });
    return () => {
      cancelled = true;
    };
  }, [characterId, regionId]);

  if (error) {
    return <p className="text-site-red text-xs text-center mb-3 px-2 break-words">{error}</p>;
  }
  if (!entry) return null;

  const tone = reputationTone(entry.tier_code);
  return (
    <div className="flex flex-col items-center gap-0.5 mb-3 px-2 text-center">
      <p className="text-sm text-white/60">
        Ваша репутация:{' '}
        <span className={`font-medium ${REPUTATION_TONE_TEXT[tone]}`}>{entry.tier_name}</span>
      </p>
      {entry.trade_refused && (
        <p className="text-xs text-site-red">Торговцы этого края отказываются иметь с вами дело</p>
      )}
    </div>
  );
};

export default RegionReputationLine;
