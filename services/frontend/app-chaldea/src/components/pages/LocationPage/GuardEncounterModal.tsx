/**
 * GuardEncounterModal (FEAT-198).
 *
 * The guards have stopped the character (activity lock `law_encounter`). Shows
 * the guard, the wanted level, the fine, the jail term and the flee chance, with
 * one button per server `options` entry (surrender / fight ask for a
 * confirmation). Closing only hides it — the lock stays and the caller reopens
 * it (ActivityLockBanner). If nobody answers by `expires_at` the server decides
 * (live countdown, A8).
 *
 * Results: fight → the battle page; jailed → the jail location; fled → the
 * location the character was moved back to (fresh `/users/me`); fined /
 * guard gone → lock cleared by the refreshed profile.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Shield } from 'lucide-react';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import RemainingText from '../../CommonComponents/RemainingText';
import ConfirmDialog from './ConfirmDialog';
import {
  chooseLawOption,
  fetchLawEncounter,
  jailTermText,
  type LawChoice,
  type LawEncounterOut,
} from '../../../api/law';
import { apiErrorMessage } from '../../../api/errors';
import { useAppDispatch } from '../../../redux/store';
import { getMe } from '../../../redux/slices/userSlice';
import { battlePath } from '../../../utils/battlePath';

interface GuardEncounterModalProps {
  characterId: number;
  /** Lock's encounter id — a change refetches. */
  encounterId: number | null;
  onClose: () => void;
}

const CHOICE_LABEL: Record<LawChoice, string> = {
  fine: 'Заплатить штраф',
  surrender: 'Сдаться',
  flee: 'Бежать',
  fight: 'Драться',
};

const CHOICE_ORDER: LawChoice[] = ['fine', 'surrender', 'flee', 'fight'];

const percentText = (pct: number): string =>
  `${pct.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} %`;

const GuardEncounterModal = ({ characterId, encounterId, onClose }: GuardEncounterModalProps) => {
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const [encounter, setEncounter] = useState<LawEncounterOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const pendingRef = useRef(false);
  const [confirming, setConfirming] = useState<LawChoice | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const enc = await fetchLawEncounter(characterId);
      setEncounter(enc);
      // Resolved meanwhile (timeout, staff): refresh the lock so the modal goes away.
      if (!enc) void dispatch(getMe());
    } catch (err) {
      setLoadError(apiErrorMessage(err, 'Не удалось загрузить встречу со стражей'));
    } finally {
      setLoading(false);
    }
  }, [characterId, dispatch]);

  useEffect(() => {
    void load();
  }, [load, encounterId]);

  /** Fresh `/users/me`; returns the character's current location id. */
  const refreshLocation = async (): Promise<number | null> => {
    const action = await dispatch(getMe());
    if (getMe.fulfilled.match(action)) return action.payload.character?.current_location?.id ?? null;
    return null;
  };

  const choose = async (choice: LawChoice) => {
    if (!encounter || pendingRef.current) return;
    pendingRef.current = true;
    setPending(true);
    setActionError(null);
    setConfirming(null);
    try {
      const out = await chooseLawOption(characterId, encounter.id, choice);
      switch (out.result) {
        case 'fight': {
          toast(out.message, { icon: '⚔️' });
          onClose();
          if (out.battle_id) navigate(battlePath(encounter.location_id, out.battle_id));
          void dispatch(getMe());
          break;
        }
        case 'jailed': {
          toast(out.message, { icon: '⛓️', duration: 7000 });
          onClose();
          const jailLocation = out.jail?.location_id ?? (await refreshLocation());
          if (out.jail) void dispatch(getMe());
          if (jailLocation) navigate(`/location/${jailLocation}`);
          break;
        }
        case 'fled': {
          toast.success(out.message, { duration: 6000 });
          onClose();
          const here = await refreshLocation();
          if (here) navigate(`/location/${here}`);
          break;
        }
        case 'flee_failed_blocked': {
          toast.error(out.message);
          setActionError(out.message);
          if (out.encounter) setEncounter(out.encounter);
          else void load();
          break;
        }
        default: {
          // fined / guard_gone
          toast.success(out.message, { duration: 6000 });
          onClose();
          void dispatch(getMe());
        }
      }
    } catch (err) {
      const text = apiErrorMessage(err, 'Не удалось выполнить действие');
      setActionError(text);
      toast.error(text);
      // The state may have moved (another tab, timeout): show it fresh.
      void load();
      void dispatch(getMe());
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  };

  const options = encounter ? CHOICE_ORDER.filter((c) => encounter.options.includes(c)) : [];
  const fighting = encounter?.status === 'fighting';

  const icon = (
    <div className="gold-outline relative w-9 h-9 rounded-full overflow-hidden bg-black/40 shrink-0">
      {encounter?.guard_avatar ? (
        <img src={encounter.guard_avatar} alt={encounter.guard_name ?? 'Стражник'} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-gold">
          <Shield size={18} />
        </div>
      )}
    </div>
  );

  const confirmText =
    confirming === 'surrender' && encounter
      ? `Вас заключат в тюрьму края на ${jailTermText(encounter.jail_hours)}. Выйти раньше можно по залогу или попытавшись бежать.`
      : 'Начнётся бой со стражником. Победа — путь свободен, но розыск станет тяжелее; поражение — тюрьма.';

  return (
    <>
      <ModalShell
        open
        onClose={onClose}
        title="Стража"
        icon={icon}
        size="md"
        dismissible={!pending}
      >
        {loading && !encounter ? (
          <div className="flex items-center justify-center py-10">
            <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
          </div>
        ) : !encounter ? (
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <p className={loadError ? 'text-site-red text-sm' : 'text-white/70 text-sm'}>
              {loadError ?? 'Стража больше вас не задерживает'}
            </p>
            {loadError ? (
              <button type="button" className="btn-line" onClick={() => void load()}>
                Повторить
              </button>
            ) : (
              <button type="button" className="btn-blue !text-xs !py-2 !px-5" onClick={onClose}>
                Закрыть
              </button>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-4 min-w-0">
            <p className="text-white text-sm sm:text-base leading-relaxed break-words">
              <span className="gold-text font-medium">{encounter.guard_name || 'Стражник'}</span>{' '}
              преграждает вам путь.{' '}
              {encounter.is_outlaw
                ? `Для края «${encounter.region_name || '—'}» вы вне закона — договориться не выйдет.`
                : `Вас разыскивают в крае «${encounter.region_name || '—'}».`}
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <div className="flex flex-col gap-0.5 bg-white/[0.03] border border-white/5 rounded-card p-3 min-w-0">
                <span className="text-white/50 text-[11px] uppercase tracking-wide">Розыск</span>
                <span className="text-site-red text-sm font-medium break-words">{encounter.level_name || '—'}</span>
              </div>
              {encounter.options.includes('fine') && (
                <div className="flex flex-col gap-0.5 bg-white/[0.03] border border-white/5 rounded-card p-3 min-w-0">
                  <span className="text-white/50 text-[11px] uppercase tracking-wide">Штраф</span>
                  <span className="text-gold text-sm font-medium">{encounter.fine.toLocaleString('ru-RU')} золота</span>
                </div>
              )}
              {encounter.has_jail && (
                <div className="flex flex-col gap-0.5 bg-white/[0.03] border border-white/5 rounded-card p-3 min-w-0">
                  <span className="text-white/50 text-[11px] uppercase tracking-wide">Срок</span>
                  <span className="text-white text-sm font-medium">{jailTermText(encounter.jail_hours)}</span>
                </div>
              )}
            </div>

            {fighting ? (
              <div className="flex flex-col gap-3">
                <p className="text-white/80 text-sm">Идёт бой со стражей.</p>
                {encounter.battle_id && (
                  <button
                    type="button"
                    className="btn-blue w-full sm:w-auto !py-2 !px-5 !text-sm"
                    onClick={() => {
                      onClose();
                      navigate(battlePath(encounter.location_id, encounter.battle_id as number));
                    }}
                  >
                    Вернуться к бою
                  </button>
                )}
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {options.map((choice) => (
                    <button
                      key={choice}
                      type="button"
                      disabled={pending}
                      onClick={() =>
                        choice === 'surrender' || choice === 'fight' ? setConfirming(choice) : void choose(choice)
                      }
                      className={`flex flex-col items-start gap-0.5 rounded-card border px-3 py-2.5 text-left transition-colors duration-200 ease-site disabled:opacity-50 disabled:cursor-not-allowed ${
                        choice === 'fight'
                          ? 'border-site-red/40 hover:bg-site-red/10'
                          : 'border-white/15 hover:border-gold-dark/50 hover:bg-white/[0.04]'
                      }`}
                    >
                      <span className={`text-sm font-medium ${choice === 'fight' ? 'text-site-red' : 'text-white'}`}>
                        {CHOICE_LABEL[choice]}
                      </span>
                      <span className="text-white/50 text-xs">
                        {choice === 'fine' && `${encounter.fine.toLocaleString('ru-RU')} золота — розыск снят`}
                        {choice === 'surrender' && `Тюрьма на ${jailTermText(encounter.jail_hours)}`}
                        {choice === 'flee' &&
                          `Шанс ${encounter.flee_chance_pct != null ? percentText(encounter.flee_chance_pct) : '—'}; провал — бой`}
                        {choice === 'fight' && 'Бой со стражником'}
                      </span>
                    </button>
                  ))}
                </div>
                {!encounter.has_jail && (
                  <p className="text-white/40 text-xs">В этом крае нет тюрьмы — сдаться некому.</p>
                )}
                <p className="text-white/50 text-xs leading-snug">
                  Пока вы не решите, персонаж задержан на месте. Если не ответить, стража решит сама —{' '}
                  {encounter.has_jail ? 'вы окажетесь в тюрьме' : 'с вас взыщут штраф'}:{' '}
                  <RemainingText
                    until={encounter.expires_at}
                    prefix="через"
                    doneText="вот-вот"
                    className="text-gold-light"
                  />
                </p>
              </>
            )}

            {actionError && (
              <p role="alert" className="text-site-red text-xs sm:text-sm break-words">
                {actionError}
              </p>
            )}
            {pending && <p className="text-white/50 text-xs">Стража ждёт…</p>}
          </div>
        )}
      </ModalShell>

      {confirming && (
        <ConfirmDialog
          title={confirming === 'surrender' ? 'Сдаться страже?' : 'Драться со стражей?'}
          message={confirmText}
          confirmLabel={confirming === 'surrender' ? 'Сдаться' : 'В бой'}
          danger={confirming === 'fight'}
          onConfirm={() => void choose(confirming)}
          onCancel={() => setConfirming(null)}
        />
      )}
    </>
  );
};

export default GuardEncounterModal;
