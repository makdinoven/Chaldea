import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { motion, AnimatePresence } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchDungeonsAtLocation,
  createSession,
  inviteMember,
  leaveSession,
  enterDungeon,
  clearDungeonsAtLocation,
  selectDungeonsAtLocation,
  selectDungeonsLoading,
  selectCurrentSession,
  selectSessionLoading,
  updateSessionFromWs,
  updateSessionMembers,
} from '../../redux/slices/dungeonSlice';
import type { DungeonAtLocation, SessionState, SessionCreateResponse } from '../../api/dungeons';
import { checkActiveSession } from '../../api/dungeons';
import type { Player } from '../pages/LocationPage/types';
import type { DungeonWsMessage } from '../../hooks/useDungeonWebSocket';
import useDungeonWebSocket from '../../hooks/useDungeonWebSocket';
import DungeonPartyPanel from './DungeonPartyPanel';

interface DungeonEntranceProps {
  locationId: number;
  players: Player[];
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

const DungeonEntrance = ({ locationId, players, currentCharacterId }: DungeonEntranceProps) => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();

  const dungeons = useAppSelector(selectDungeonsAtLocation);
  const loading = useAppSelector(selectDungeonsLoading);
  const currentSession = useAppSelector(selectCurrentSession);
  const sessionLoading = useAppSelector(selectSessionLoading);

  const [showInviteModal, setShowInviteModal] = useState(false);
  const [activeDungeonId, setActiveDungeonId] = useState<number | null>(null);

  // Active session check (for "Return to dungeon" button)
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);

  // Confirmation modals state
  const [soloConfirmDungeonId, setSoloConfirmDungeonId] = useState<number | null>(null);
  const [groupConfirmDungeonId, setGroupConfirmDungeonId] = useState<number | null>(null);
  const [enterConfirm, setEnterConfirm] = useState(false);

  // Cooldown timers
  const [cooldowns, setCooldowns] = useState<Record<number, number>>({});
  const cooldownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // WebSocket
  const token = typeof window !== 'undefined' ? localStorage.getItem('accessToken') : null;
  const { lastMessage } = useDungeonWebSocket(
    currentSession?.session_id ?? null,
    token,
  );

  // Handle WS messages
  useEffect(() => {
    if (!lastMessage) return;

    const msg = lastMessage as DungeonWsMessage;

    switch (msg.type) {
      case 'session_update':
        if (msg.data && typeof msg.data === 'object' && 'session_id' in msg.data) {
          dispatch(updateSessionMembers(msg.data as unknown as SessionCreateResponse));
        }
        break;
      case 'session_status':
        if (msg.data && 'status' in msg.data) {
          const status = msg.data.status as string;
          if (status === 'active' && 'session_state' in msg.data) {
            dispatch(updateSessionFromWs(msg.data.session_state as SessionState));
          }
        }
        break;
      case 'leader_changed':
        toast('Лидер группы изменён');
        break;
      default:
        break;
    }
  }, [lastMessage, dispatch]);

  // Check if character has an active dungeon session
  useEffect(() => {
    if (!currentCharacterId) return;
    checkActiveSession(currentCharacterId)
      .then((result) => {
        if (result.in_dungeon && result.session_id) {
          setActiveSessionId(result.session_id);
        } else {
          setActiveSessionId(null);
        }
      })
      .catch(() => {
        setActiveSessionId(null);
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

  // Handlers
  const handleCreateSession = useCallback(
    (dungeonId: number) => {
      if (!currentCharacterId) {
        toast.error('Выберите персонажа');
        return;
      }
      setActiveDungeonId(dungeonId);
      dispatch(createSession({ dungeonId, characterId: currentCharacterId }));
    },
    [dispatch, currentCharacterId],
  );

  const handleSoloEntry = useCallback(
    (dungeonId: number) => {
      if (!currentCharacterId) {
        toast.error('Выберите персонажа');
        return;
      }
      dispatch(createSession({ dungeonId, characterId: currentCharacterId }))
        .unwrap()
        .then((session) => {
          return dispatch(enterDungeon({ sessionId: session.session_id, characterId: currentCharacterId }))
            .unwrap()
            .then(() => {
              navigate(`/dungeon-session/${session.session_id}`);
            });
        })
        .catch(() => {
          // Errors already shown via toast in thunks
        });
    },
    [dispatch, currentCharacterId, navigate],
  );

  const handleInvite = useCallback(
    (targetCharacterId: number) => {
      if (!currentSession) return;
      dispatch(inviteMember({ sessionId: currentSession.session_id, characterId: targetCharacterId }));
      setShowInviteModal(false);
    },
    [dispatch, currentSession],
  );

  const handleLeave = useCallback(() => {
    if (!currentSession || !currentCharacterId) return;
    dispatch(leaveSession({ sessionId: currentSession.session_id, characterId: currentCharacterId }));
  }, [dispatch, currentSession, currentCharacterId]);

  const handleEnter = useCallback(() => {
    if (!currentSession || !currentCharacterId) return;
    setEnterConfirm(true);
  }, [currentSession, currentCharacterId]);

  const handleEnterConfirmed = useCallback(() => {
    if (!currentSession || !currentCharacterId) return;
    setEnterConfirm(false);
    dispatch(enterDungeon({ sessionId: currentSession.session_id, characterId: currentCharacterId }))
      .unwrap()
      .then(() => {
        navigate(`/dungeon-session/${currentSession.session_id}`);
      })
      .catch(() => {
        // Error already shown via toast in thunk
      });
  }, [dispatch, currentSession, currentCharacterId, navigate]);

  // Characters available for invite (at this location, not in party)
  const invitablePlayers = players.filter(
    (p) =>
      p.id !== currentCharacterId &&
      !currentSession?.members.some((m) => m.character_id === p.id),
  );

  const isLeader = currentSession?.members.some(
    (m) => m.character_id === currentCharacterId && m.is_leader,
  ) ?? false;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <div className="w-6 h-6 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

  if (dungeons.length === 0) {
    return null;
  }

  return (
    <section className="bg-black/60 rounded-card p-4 sm:p-6 backdrop-blur-sm flex flex-col gap-4">
      <h2 className="gold-text text-lg sm:text-xl font-medium uppercase">
        Подземелья
      </h2>

      <div className="flex flex-col gap-4">
        {dungeons.map((dungeon) => (
          <DungeonCard
            key={dungeon.id}
            dungeon={dungeon}
            cooldownSeconds={cooldowns[dungeon.id] ?? 0}
            isActive={activeDungeonId === dungeon.id && !!currentSession}
            currentSession={activeDungeonId === dungeon.id ? currentSession : null}
            currentCharacterId={currentCharacterId}
            isLeader={isLeader}
            sessionLoading={sessionLoading}
            activeSessionId={activeSessionId}
            onReturnToDungeon={(sessionId) => navigate(`/dungeon-session/${sessionId}`)}
            onSoloClick={(id) => setSoloConfirmDungeonId(id)}
            onGroupClick={(id) => setGroupConfirmDungeonId(id)}
            onEnter={handleEnter}
            onLeave={handleLeave}
            onInviteClick={() => setShowInviteModal(true)}
          />
        ))}
      </div>

      {/* Solo Confirm Modal */}
      <AnimatePresence>
        {soloConfirmDungeonId !== null && (
          <div className="modal-overlay" onClick={() => setSoloConfirmDungeonId(null)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick max-w-sm w-full mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <h3 className="gold-text text-lg font-medium uppercase mb-3">
                Подтверждение
              </h3>
              <p className="text-white/80 text-sm mb-5">
                Вы уверены, что хотите войти в подземелье в одиночку?
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => {
                    const id = soloConfirmDungeonId;
                    setSoloConfirmDungeonId(null);
                    handleSoloEntry(id);
                  }}
                  disabled={sessionLoading}
                  className="btn-blue text-sm flex-1 py-2 disabled:opacity-50"
                >
                  {sessionLoading ? 'Вход...' : 'Да, войти'}
                </button>
                <button
                  onClick={() => setSoloConfirmDungeonId(null)}
                  className="btn-line text-sm flex-1 py-2"
                >
                  Отмена
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Group Confirm Modal */}
      <AnimatePresence>
        {groupConfirmDungeonId !== null && (
          <div className="modal-overlay" onClick={() => setGroupConfirmDungeonId(null)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick max-w-sm w-full mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <h3 className="gold-text text-lg font-medium uppercase mb-3">
                Подтверждение
              </h3>
              <p className="text-white/80 text-sm mb-5">
                Создать группу для прохождения подземелья?
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => {
                    const id = groupConfirmDungeonId;
                    setGroupConfirmDungeonId(null);
                    handleCreateSession(id);
                  }}
                  disabled={sessionLoading}
                  className="btn-blue text-sm flex-1 py-2 disabled:opacity-50"
                >
                  {sessionLoading ? 'Создание...' : 'Да, создать'}
                </button>
                <button
                  onClick={() => setGroupConfirmDungeonId(null)}
                  className="btn-line text-sm flex-1 py-2"
                >
                  Отмена
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Enter Dungeon Confirm Modal */}
      <AnimatePresence>
        {enterConfirm && (
          <div className="modal-overlay" onClick={() => setEnterConfirm(false)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick max-w-sm w-full mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <h3 className="gold-text text-lg font-medium uppercase mb-3">
                Подтверждение
              </h3>
              <p className="text-white/80 text-sm mb-5">
                Войти в подземелье с текущей группой?
              </p>
              <div className="flex gap-3">
                <button
                  onClick={handleEnterConfirmed}
                  disabled={sessionLoading}
                  className="btn-blue text-sm flex-1 py-2 disabled:opacity-50"
                >
                  {sessionLoading ? 'Вход...' : 'Да, войти'}
                </button>
                <button
                  onClick={() => setEnterConfirm(false)}
                  className="btn-line text-sm flex-1 py-2"
                >
                  Отмена
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Invite Modal */}
      <AnimatePresence>
        {showInviteModal && (
          <div className="modal-overlay" onClick={() => setShowInviteModal(false)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick max-w-md w-full mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <h3 className="gold-text text-xl font-medium uppercase mb-4">
                Пригласить в группу
              </h3>

              {invitablePlayers.length === 0 ? (
                <p className="text-white/60 text-sm">
                  Нет доступных персонажей для приглашения на этой локации
                </p>
              ) : (
                <div className="flex flex-col gap-2 max-h-60 overflow-y-auto gold-scrollbar">
                  {invitablePlayers.map((player) => (
                    <button
                      key={player.id}
                      onClick={() => handleInvite(player.id)}
                      disabled={sessionLoading}
                      className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 transition-colors text-left disabled:opacity-50"
                    >
                      <div className="gold-outline relative w-8 h-8 rounded-full overflow-hidden bg-black/40 shrink-0">
                        {player.avatar ? (
                          <img src={player.avatar} alt={player.name} className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-white/20">
                            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                            </svg>
                          </div>
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <span className="text-white text-sm truncate block">{player.name}</span>
                        <span className="text-white/40 text-xs">Ур. {player.level}</span>
                      </div>
                    </button>
                  ))}
                </div>
              )}

              <button
                onClick={() => setShowInviteModal(false)}
                className="btn-line text-sm mt-4 w-full"
              >
                Закрыть
              </button>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </section>
  );
};

// --- Dungeon Card sub-component ---

interface DungeonCardProps {
  dungeon: DungeonAtLocation;
  cooldownSeconds: number;
  isActive: boolean;
  currentSession: {
    session_id: number;
    members: { character_id: number; name: string; user_id: number; status: 'alive' | 'dead' | 'disconnected'; is_leader: boolean }[];
  } | null;
  currentCharacterId: number | null;
  isLeader: boolean;
  sessionLoading: boolean;
  activeSessionId: number | null;
  onReturnToDungeon: (sessionId: number) => void;
  onSoloClick: (dungeonId: number) => void;
  onGroupClick: (dungeonId: number) => void;
  onEnter: () => void;
  onLeave: () => void;
  onInviteClick: () => void;
}

const DungeonCard = ({
  dungeon,
  cooldownSeconds,
  isActive,
  currentSession,
  currentCharacterId,
  isLeader,
  sessionLoading,
  activeSessionId,
  onReturnToDungeon,
  onSoloClick,
  onGroupClick,
  onEnter,
  onLeave,
  onInviteClick,
}: DungeonCardProps) => {
  const isOnCooldown = cooldownSeconds > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="bg-white/5 rounded-card p-4 flex flex-col gap-3"
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

      {/* Cooldown message */}
      {isOnCooldown && (
        <div className="text-site-red text-sm font-medium flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Недоступно. Восстановится через {formatCooldown(cooldownSeconds)}
        </div>
      )}

      {/* Party panel (when session is active for this dungeon) */}
      {isActive && currentSession && (
        <DungeonPartyPanel
          members={currentSession.members}
          maxSize={dungeon.recommended_party_size ?? 4}
          currentCharacterId={currentCharacterId}
          isLeader={isLeader}
          isForming
          onLeave={onLeave}
          onInviteClick={onInviteClick}
          leaveLoading={sessionLoading}
        />
      )}

      {/* Actions */}
      <div className="flex flex-col sm:flex-row gap-2">
        {/* Return to dungeon button — shown when character has active session */}
        {activeSessionId && !isActive && (
          <button
            onClick={() => onReturnToDungeon(activeSessionId)}
            className="btn-blue text-sm px-5 py-2"
          >
            Вернуться в данж
          </button>
        )}

        {/* Solo / Group buttons — shown when no active session and no cooldown */}
        {!activeSessionId && !isActive && !isOnCooldown && currentCharacterId && (
          <>
            <button
              onClick={() => onSoloClick(dungeon.id)}
              disabled={sessionLoading}
              className="btn-blue text-sm px-5 py-2 disabled:opacity-50"
            >
              {sessionLoading ? 'Вход...' : 'Зайти одному'}
            </button>
            <button
              onClick={() => onGroupClick(dungeon.id)}
              disabled={sessionLoading}
              className="btn-blue text-sm px-5 py-2 disabled:opacity-50"
            >
              {sessionLoading ? 'Создание...' : 'Создать группу'}
            </button>
          </>
        )}

        {/* Enter dungeon button — shown when party is forming and user is leader */}
        {isActive && isLeader && (
          <button
            onClick={onEnter}
            disabled={sessionLoading}
            className="btn-blue text-sm px-5 py-2 disabled:opacity-50"
          >
            {sessionLoading ? 'Вход...' : 'Войти в подземелье'}
          </button>
        )}
      </div>
    </motion.div>
  );
};

export default DungeonEntrance;
