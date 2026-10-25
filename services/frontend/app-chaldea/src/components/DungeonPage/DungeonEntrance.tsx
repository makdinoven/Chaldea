import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { motion } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchDungeonsAtLocation,
  createSession,
  partyRunThunk,
  clearDungeonsAtLocation,
  selectDungeonsAtLocation,
  selectDungeonsLoading,
  selectDungeonsError,
  selectSessionLoading,
} from '../../redux/slices/dungeonSlice';
import type { DungeonAtLocation } from '../../api/dungeons';
import { checkActiveSession } from '../../api/dungeons';
import { getMyParty, type Party } from '../../api/squads';
import ModalShell from '../CommonComponents/ModalShell/ModalShell';

interface DungeonEntranceProps {
  locationId: number;
  currentCharacterId: number | null;
}

const STABILITY_LABELS: Record<string, string> = {
  static: 'Изученный',
  unstable: 'Опасный',
  chaotic: 'Смертельный',
};

const STABILITY_COLORS: Record<string, string> = {
  static: 'bg-green-600/80 text-green-100',
  unstable: 'bg-yellow-600/80 text-yellow-100',
  chaotic: 'bg-red-600/80 text-red-100',
};

const DANGER_LABELS: Record<string, string> = {
  safe: 'Безопасный',
  deadly: 'Смертельный',
};

const DANGER_COLORS: Record<string, string> = {
  safe: 'bg-site-blue/30 text-site-blue',
  deadly: 'bg-site-red/30 text-site-red',
};

const formatCooldown = (seconds: number): string => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
};

interface MyRun {
  sessionId: number | null;
  pendingLootSessionId: number | null;
}

const DungeonEntrance = ({ locationId, currentCharacterId }: DungeonEntranceProps) => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();

  const dungeons = useAppSelector(selectDungeonsAtLocation);
  const loading = useAppSelector(selectDungeonsLoading);
  const listError = useAppSelector(selectDungeonsError);
  const sessionLoading = useAppSelector(selectSessionLoading);

  // The character's own run: in progress, or finished with loot to share.
  const [myRun, setMyRun] = useState<MyRun>({ sessionId: null, pendingLootSessionId: null });
  const [myRunError, setMyRunError] = useState<string | null>(null);

  // Entry modal + the last entry error per dungeon (shown inline on the card)
  const [entryDungeonId, setEntryDungeonId] = useState<number | null>(null);
  const [entryErrors, setEntryErrors] = useState<Record<number, string>>({});

  // Cooldown timers
  const [cooldowns, setCooldowns] = useState<Record<number, number>>({});
  const cooldownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Squad (party-service): the leader enters with squadmates on this location
  const [party, setParty] = useState<Party | null>(null);

  useEffect(() => {
    if (!currentCharacterId) return;
    let cancelled = false;
    checkActiveSession(currentCharacterId)
      .then((result) => {
        if (cancelled) return;
        setMyRunError(null);
        setMyRun({
          sessionId: result.in_dungeon ? result.session_id : null,
          pendingLootSessionId: result.pending_loot_session_id ?? null,
        });
      })
      .catch(() => {
        if (!cancelled) setMyRunError('Не удалось проверить, есть ли у персонажа незавершённый забег');
      });
    return () => {
      cancelled = true;
    };
  }, [currentCharacterId]);

  useEffect(() => {
    if (!currentCharacterId) {
      setParty(null);
      return;
    }
    getMyParty(currentCharacterId)
      .then(setParty)
      .catch(() => {
        setParty(null);
        toast.error('Не удалось загрузить данные отряда');
      });
  }, [currentCharacterId]);

  // Fetch dungeons at this location
  useEffect(() => {
    dispatch(fetchDungeonsAtLocation(locationId));
    return () => {
      dispatch(clearDungeonsAtLocation());
    };
  }, [dispatch, locationId]);

  // Initialize cooldown timers
  useEffect(() => {
    const initial: Record<number, number> = {};
    for (const d of dungeons) {
      if (d.is_on_cooldown && d.cooldown_remaining_seconds > 0) {
        initial[d.id] = d.cooldown_remaining_seconds;
      }
    }
    setCooldowns(initial);
  }, [dungeons]);

  // Tick cooldown timers
  useEffect(() => {
    if (cooldownIntervalRef.current) {
      clearInterval(cooldownIntervalRef.current);
    }

    const hasActive = Object.values(cooldowns).some((v) => v > 0);
    if (!hasActive) return;

    cooldownIntervalRef.current = setInterval(() => {
      setCooldowns((prev) => {
        const next: Record<number, number> = {};
        let anyActive = false;
        for (const [key, val] of Object.entries(prev)) {
          const newVal = Math.max(0, val - 1);
          next[Number(key)] = newVal;
          if (newVal > 0) anyActive = true;
        }
        if (!anyActive && cooldownIntervalRef.current) {
          clearInterval(cooldownIntervalRef.current);
          cooldownIntervalRef.current = null;
        }
        return next;
      });
    }, 1000);

    return () => {
      if (cooldownIntervalRef.current) {
        clearInterval(cooldownIntervalRef.current);
        cooldownIntervalRef.current = null;
      }
    };
  }, [cooldowns]);

  const coLocatedMates = (party?.members ?? []).filter(
    (m) =>
      m.status === 'accepted' &&
      m.character_id !== currentCharacterId &&
      m.current_location_id === locationId,
  );
  const isSquadLeader = !!party && party.leader_character_id === currentCharacterId;
  const canPartyRun = isSquadLeader && coLocatedMates.length >= 1;

  const onEntryFailed = useCallback(
    (dungeonId: number, message: string) => {
      setEntryErrors((prev) => ({ ...prev, [dungeonId]: message }));
      // Occupancy / cooldown may have changed under us.
      dispatch(fetchDungeonsAtLocation(locationId));
    },
    [dispatch, locationId],
  );

  const handleSoloEntry = useCallback(
    (dungeonId: number) => {
      if (!currentCharacterId) {
        toast.error('Выберите персонажа');
        return;
      }
      setEntryErrors((prev) => ({ ...prev, [dungeonId]: '' }));
      dispatch(createSession({ dungeonId, characterId: currentCharacterId }))
        .unwrap()
        .then((session) => navigate(`/dungeon-session/${session.session_id}`))
        .catch((message: string) => onEntryFailed(dungeonId, message));
    },
    [dispatch, currentCharacterId, navigate, onEntryFailed],
  );

  const handlePartyRun = useCallback(
    (dungeonId: number) => {
      if (!currentCharacterId) {
        toast.error('Выберите персонажа');
        return;
      }
      setEntryErrors((prev) => ({ ...prev, [dungeonId]: '' }));
      dispatch(partyRunThunk({ dungeonId, characterId: currentCharacterId }))
        .unwrap()
        .then((state) => navigate(`/dungeon-session/${state.session_id}`))
        .catch((message: string) => onEntryFailed(dungeonId, message));
    },
    [dispatch, currentCharacterId, navigate, onEntryFailed],
  );

  if (loading && dungeons.length === 0) {
    return (
      <div className="flex items-center justify-center py-6">
        <div className="w-6 h-6 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

  if (listError && dungeons.length === 0) {
    return (
      <div className="bg-site-bg backdrop-blur-sm rounded-card border border-site-red/30 p-4 flex flex-col sm:flex-row sm:items-center gap-3">
        <p className="text-site-red text-sm flex-1">{listError}</p>
        <button
          onClick={() => dispatch(fetchDungeonsAtLocation(locationId))}
          className="btn-line text-sm px-4 py-1.5 self-start sm:self-auto"
        >
          Повторить
        </button>
      </div>
    );
  }

  if (dungeons.length === 0) {
    return null;
  }

  const entryDungeon = dungeons.find((d) => d.id === entryDungeonId) ?? null;

  return (
    <section className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 shadow-card overflow-hidden">
      {/* Section header (FEAT-152 card language) */}
      <div className="flex items-center gap-2.5 px-4 sm:px-5 py-3.5 border-b border-white/[0.07]">
        <svg xmlns="http://www.w3.org/2000/svg" className="w-[18px] h-[18px] text-gold shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 21V8a8 8 0 0116 0v13" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 21v-6a3 3 0 016 0v6" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M2 21h20" />
        </svg>
        <h2 className="gold-text text-[13px] font-medium uppercase tracking-[0.08em]">
          Подземелья
        </h2>
        <span className="bg-white/10 text-white/60 text-[10px] font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">
          {dungeons.length}
        </span>
      </div>

      <div className="flex flex-col gap-3 px-3 sm:px-4 py-4">
        {myRunError && (
          <p className="text-site-red text-xs">{myRunError}</p>
        )}

        {/* An ended run with undivided loot (completed or escaped) */}
        {myRun.pendingLootSessionId && !myRun.sessionId && (
          <div className="rounded-card border border-gold-dark/30 bg-gold/5 px-3 py-2.5 flex flex-col sm:flex-row sm:items-center gap-2">
            <p className="text-white/80 text-sm flex-1">
              Забег окончен, но добыча ещё не поделена.
            </p>
            <button
              onClick={() => navigate(`/dungeon-session/${myRun.pendingLootSessionId}`)}
              className="btn-blue text-xs sm:text-sm px-4 py-1.5 self-start sm:self-auto"
            >
              К дележу добычи
            </button>
          </div>
        )}

        {dungeons.map((dungeon) => (
          <DungeonCard
            key={dungeon.id}
            dungeon={dungeon}
            cooldownSeconds={cooldowns[dungeon.id] ?? 0}
            currentCharacterId={currentCharacterId}
            sessionLoading={sessionLoading}
            activeSessionId={myRun.sessionId}
            entryError={entryErrors[dungeon.id] || null}
            onReturnToDungeon={(sessionId) => navigate(`/dungeon-session/${sessionId}`)}
            onEnterClick={(id) => setEntryDungeonId(id)}
          />
        ))}
      </div>

      {/* Entry modal: solo or with the squad */}
      <ModalShell
        open={entryDungeon !== null}
        onClose={() => setEntryDungeonId(null)}
        title={entryDungeon ? `Войти: ${entryDungeon.name}` : 'Войти в подземелье'}
        size="sm"
        footer={
          <>
            <button
              onClick={() => setEntryDungeonId(null)}
              className="btn-line text-sm w-full sm:w-auto"
            >
              Отмена
            </button>
            <button
              onClick={() => {
                const id = entryDungeonId;
                setEntryDungeonId(null);
                if (id !== null) handleSoloEntry(id);
              }}
              disabled={sessionLoading}
              className="btn-blue text-sm w-full sm:w-auto disabled:opacity-50"
            >
              {sessionLoading ? 'Вход...' : 'В одиночку'}
            </button>
            {canPartyRun && (
              <button
                onClick={() => {
                  const id = entryDungeonId;
                  setEntryDungeonId(null);
                  if (id !== null) handlePartyRun(id);
                }}
                disabled={sessionLoading}
                className="btn-blue text-sm w-full sm:w-auto disabled:opacity-50"
              >
                {sessionLoading ? 'Вход...' : `Отрядом (${coLocatedMates.length + 1})`}
              </button>
            )}
          </>
        }
      >
        <div className="flex flex-col gap-3 text-sm">
          <p className="text-white/80">
            Пока вы внутри, персонаж не сможет перемещаться, писать посты и сражаться снаружи.
            Другие группы не смогут войти, пока вы не выйдете.
          </p>
          <p className="text-white/50 text-xs">
            Для входа нужен свежий пост с намерением «Вход в подземелье» на этой локации.
          </p>
          {canPartyRun ? (
            <p className="text-white/50 text-xs">
              Отрядом пойдут сопартийцы на этой локации. Кто не сможет войти (без сознания, в бою, в другом
              подземелье), останется снаружи — вы увидите, кто и почему.
            </p>
          ) : party && !isSquadLeader ? (
            <p className="text-white/50 text-xs">Войти отрядом может только лидер отряда.</p>
          ) : party ? (
            <p className="text-white/50 text-xs">
              Чтобы войти отрядом, сопартийцы должны стоять на этой же локации.
            </p>
          ) : null}
        </div>
      </ModalShell>
    </section>
  );
};

// --- Dungeon Card sub-component ---

interface DungeonCardProps {
  dungeon: DungeonAtLocation;
  cooldownSeconds: number;
  currentCharacterId: number | null;
  sessionLoading: boolean;
  activeSessionId: number | null;
  entryError: string | null;
  onReturnToDungeon: (sessionId: number) => void;
  onEnterClick: (dungeonId: number) => void;
}

const DungeonCard = ({
  dungeon,
  cooldownSeconds,
  currentCharacterId,
  sessionLoading,
  activeSessionId,
  entryError,
  onReturnToDungeon,
  onEnterClick,
}: DungeonCardProps) => {
  const isOnCooldown = cooldownSeconds > 0;
  const isOccupied = dungeon.is_occupied;
  const entryBlocked = isOnCooldown || isOccupied;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="bg-white/[0.04] border border-white/[0.08] rounded-card p-3 sm:p-4 flex flex-col gap-3"
    >
      {/* Header row */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2">
        <h3 className="gold-text text-base sm:text-lg font-medium flex-1 min-w-0 truncate">
          {dungeon.name}
        </h3>
        <div className="flex flex-wrap gap-2">
          <span className={`text-[10px] sm:text-xs px-2 py-0.5 rounded-full font-medium ${STABILITY_COLORS[dungeon.stability_type] ?? 'bg-white/10 text-white'}`}>
            {STABILITY_LABELS[dungeon.stability_type] ?? dungeon.stability_type}
          </span>
          <span className={`text-[10px] sm:text-xs px-2 py-0.5 rounded-full font-medium ${DANGER_COLORS[dungeon.danger_level] ?? 'bg-white/10 text-white'}`}>
            {DANGER_LABELS[dungeon.danger_level] ?? dungeon.danger_level}
          </span>
        </div>
      </div>

      {/* Description */}
      <p className="text-white/70 text-sm leading-relaxed">
        {dungeon.description}
      </p>

      {/* Lore text */}
      {dungeon.lore_text && (
        <p className="text-gold-dark/80 text-xs italic border-l-2 border-gold-dark/40 pl-3">
          {dungeon.lore_text}
        </p>
      )}

      {/* Meta row */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-white/50">
        {dungeon.recommended_level && (
          <span>Рек. уровень: <span className="text-white/80">{dungeon.recommended_level}</span></span>
        )}
        {dungeon.recommended_party_size && (
          <span>Рек. группа: <span className="text-white/80">{dungeon.recommended_party_size}</span></span>
        )}
      </div>

      {/* Occupied by another group */}
      {isOccupied && !activeSessionId && (
        <div className="text-gold text-sm font-medium flex items-center gap-2">
          <span aria-hidden>🔒</span>
          Внутри уже группа — дождитесь, пока она выйдет
        </div>
      )}

      {/* Cooldown message */}
      {isOnCooldown && (
        <div className="text-site-red text-sm font-medium flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Подземелье зачищено. Восстановится через {formatCooldown(cooldownSeconds)}
        </div>
      )}

      {/* Last entry error */}
      {entryError && (
        <p className="text-site-red text-sm" role="alert">{entryError}</p>
      )}

      {/* Actions */}
      <div className="flex flex-col sm:flex-row gap-2">
        {activeSessionId ? (
          <button
            onClick={() => onReturnToDungeon(activeSessionId)}
            className="btn-blue text-sm px-5 py-2"
          >
            Вернуться к забегу
          </button>
        ) : (
          currentCharacterId && (
            <button
              onClick={() => onEnterClick(dungeon.id)}
              disabled={sessionLoading || entryBlocked}
              className="btn-blue text-sm px-5 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {sessionLoading ? 'Вход...' : 'Войти'}
            </button>
          )
        )}
      </div>
    </motion.div>
  );
};

export default DungeonEntrance;
