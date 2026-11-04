/**
 * JailBanner (FEAT-198).
 *
 * Site-wide strip while the character serves a jail term (activity lock
 * `jail`): live countdown of the term (A8), the jail region and location,
 * self-bail with its price (confirmation) and an escape attempt with the chance
 * and the cooldown countdown. When the term ends the profile is refreshed.
 * Posting stays possible in the jail location itself (LocationPage).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import RemainingText from '../../CommonComponents/RemainingText';
import ConfirmDialog from './ConfirmDialog';
import { escapeFromJail, fetchLawJail, selfBail, type LawJailOut } from '../../../api/law';
import { apiErrorMessage } from '../../../api/errors';
import { useAppDispatch } from '../../../redux/store';
import { getMe } from '../../../redux/slices/userSlice';
import { fetchProfile } from '../../../redux/slices/profileSlice';
import { parseServerDate } from '../../../utils/serverDate';

interface JailBannerProps {
  characterId: number;
  /** Term end from the activity lock — the countdown works even before the jail details load. */
  until: Date | null;
}

const percentText = (pct: number): string =>
  `${pct.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} %`;

const JailBanner = ({ characterId, until }: JailBannerProps) => {
  const dispatch = useAppDispatch();
  const [jail, setJail] = useState<LawJailOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const pendingRef = useRef(false);
  const [confirmBail, setConfirmBail] = useState(false);
  const [lastMessage, setLastMessage] = useState<string | null>(null);
  /** Re-render once the escape cooldown passes so the button unlocks. */
  const [, setCooldownTick] = useState(0);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const data = await fetchLawJail(characterId);
      setJail(data);
      if (!data) void dispatch(getMe());
    } catch (err) {
      setLoadError(apiErrorMessage(err, 'Не удалось загрузить сведения о заключении'));
    }
  }, [characterId, dispatch]);

  useEffect(() => {
    void load();
  }, [load, until?.getTime()]); // eslint-disable-line react-hooks/exhaustive-deps

  const termEnd = jail ? parseServerDate(jail.until) : until;
  const escapeAt = jail?.can_escape_at ? parseServerDate(jail.can_escape_at) : null;
  const escapeReady = !escapeAt || escapeAt.getTime() <= Date.now();

  const run = async (call: () => Promise<{ message: string; jail: LawJailOut | null }>, fallback: string,
    success?: (message: string) => void) => {
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPending(true);
    try {
      const out = await call();
      setLastMessage(out.message);
      success?.(out.message);
      setJail(out.jail);
      if (!out.jail) {
        await dispatch(getMe());
        dispatch(fetchProfile(characterId));
      }
    } catch (err) {
      const text = apiErrorMessage(err, fallback);
      setLastMessage(text);
      toast.error(text);
      void load();
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  };

  const doEscape = () =>
    run(
      async () => {
        const out = await escapeFromJail(characterId);
        if (out.success) toast.success(out.message, { duration: 7000 });
        else toast.error(out.message, { duration: 7000 });
        return out;
      },
      'Не удалось попытаться бежать',
    );

  const doBail = () => {
    setConfirmBail(false);
    return run(() => selfBail(characterId), 'Не удалось внести залог', (m) => toast.success(m));
  };

  return (
    <div
      role="status"
      className="mb-4 rounded-card border border-site-red/40 bg-site-bg backdrop-blur-sm px-3 py-3 sm:px-4 flex flex-col gap-2.5"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-lg leading-none shrink-0" aria-hidden>⛓️</span>
        <div className="flex flex-col min-w-0 flex-1">
          <span className="text-white text-sm font-medium">
            Персонаж в тюрьме
            {jail?.region_name ? ` края «${jail.region_name}»` : ''}
            {termEnd && (
              <>
                {' — '}
                <RemainingText until={termEnd} doneText="срок истёк" onDone={() => void dispatch(getMe())}
                  className="text-gold-light" />
              </>
            )}
          </span>
          <span className="text-white/50 text-xs break-words">
            Перемещаться, торговать, сражаться и брать задания нельзя. Писать посты можно в самой тюрьме
            {jail?.location_name ? (
              <>
                {' — '}
                <Link to={`/location/${jail.location_id}`} className="site-link">
                  «{jail.location_name}»
                </Link>
              </>
            ) : null}
            .
          </span>
        </div>
      </div>

      {loadError && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-site-red text-xs">{loadError}</span>
          <button type="button" className="btn-line !text-xs !py-1 !px-3" onClick={() => void load()}>
            Повторить
          </button>
        </div>
      )}

      {jail && (
        <div className="flex flex-col sm:flex-row gap-2">
          <button
            type="button"
            disabled={pending}
            onClick={() => setConfirmBail(true)}
            className="btn-blue w-full sm:w-auto !text-xs sm:!text-sm !py-1.5 !px-4 disabled:opacity-50"
          >
            Внести залог · {jail.bail_price.toLocaleString('ru-RU')} золота
          </button>
          <button
            type="button"
            disabled={pending || !escapeReady}
            onClick={() => void doEscape()}
            className="btn-line w-full sm:w-auto !text-xs sm:!text-sm !py-1.5 !px-4 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {escapeReady ? (
              `Попытаться бежать · шанс ${percentText(jail.escape_chance_pct)}`
            ) : (
              <>
                Побег —{' '}
                <RemainingText until={escapeAt} prefix="через" onDone={() => setCooldownTick((n) => n + 1)} />
              </>
            )}
          </button>
        </div>
      )}
      {jail && (
        <p className="text-white/40 text-[11px] leading-snug">
          Провал побега продлевает срок наполовину от оставшегося; удачный побег делает розыск тяжёлым.
          За вас может заплатить залог любой персонаж у банкира.
        </p>
      )}
      {lastMessage && <p className="text-white/70 text-xs break-words">{lastMessage}</p>}

      {confirmBail && jail && (
        <ConfirmDialog
          title="Внести залог?"
          message={`С вас спишут ${jail.bail_price.toLocaleString('ru-RU')} золота в казну края, и вы выйдете на свободу.`}
          confirmLabel="Внести залог"
          onConfirm={() => void doBail()}
          onCancel={() => setConfirmBail(false)}
        />
      )}
    </div>
  );
};

export default JailBanner;
