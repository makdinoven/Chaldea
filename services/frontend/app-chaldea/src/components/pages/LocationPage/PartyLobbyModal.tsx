import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { motion } from 'motion/react';
import { X } from 'react-feather';
import {
  createParty,
  getParty,
  inviteToParty,
  leaveParty,
  respondToParty,
  startParty,
  type PartyState,
} from '../../../api/party';

export interface PartyPlayer {
  id: number;
  name: string;
  level: number;
  avatar: string | null;
}

interface PartyLobbyModalProps {
  characterId: number;
  locationId: number;
  players: PartyPlayer[];
  initialPartyId?: number | null;
  onClose: () => void;
}

const TEAMS = [0, 1];
const POLL_MS = 3000;

const PartyLobbyModal = ({
  characterId,
  locationId,
  players,
  initialPartyId = null,
  onClose,
}: PartyLobbyModalProps) => {
  const navigate = useNavigate();
  const [party, setParty] = useState<PartyState | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const navigatedRef = useRef(false);

  const isLeader = party?.leader_character_id === characterId;

  // Create-or-load the party once.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = initialPartyId
          ? await getParty(initialPartyId)
          : await createParty(characterId, 'pvp_training');
        if (!cancelled) setParty(p);
      } catch (e) {
        const err = e as { response?: { data?: { detail?: string } } };
        toast.error(err?.response?.data?.detail || 'Не удалось открыть группу');
        if (!cancelled) onClose();
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll the lobby; navigate into the battle once it starts.
  useEffect(() => {
    if (!party) return;
    const id = party.id;
    const tick = async () => {
      try {
        const p = await getParty(id);
        setParty(p);
        if (p.status === 'started' && p.battle_id && !navigatedRef.current) {
          navigatedRef.current = true;
          navigate(`/location/${locationId}/battle/${p.battle_id}`);
        } else if (p.status === 'cancelled') {
          toast('Группа распущена');
          onClose();
        }
      } catch {
        /* keep last known state */
      }
    };
    const interval = setInterval(tick, POLL_MS);
    return () => clearInterval(interval);
  }, [party?.id, locationId, navigate, onClose]);

  const refresh = useCallback(async () => {
    if (!party) return;
    try {
      setParty(await getParty(party.id));
    } catch {
      /* ignore */
    }
  }, [party?.id]);

  const handleInvite = async (targetId: number, team: number) => {
    if (!party) return;
    setBusy(true);
    try {
      setParty(await inviteToParty(party.id, targetId, team));
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast.error(err?.response?.data?.detail || 'Не удалось пригласить');
    } finally {
      setBusy(false);
    }
  };

  const handleKick = async (targetId: number) => {
    if (!party) return;
    setBusy(true);
    try {
      await leaveParty(party.id, targetId);
      await refresh();
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast.error(err?.response?.data?.detail || 'Не удалось убрать игрока');
    } finally {
      setBusy(false);
    }
  };

  const handleLeave = async () => {
    if (!party) return;
    setBusy(true);
    try {
      await leaveParty(party.id, characterId);
      onClose();
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast.error(err?.response?.data?.detail || 'Не удалось выйти');
    } finally {
      setBusy(false);
    }
  };

  const handleStart = async () => {
    if (!party) return;
    setBusy(true);
    try {
      const res = await startParty(party.id);
      navigatedRef.current = true;
      navigate(`/location/${locationId}/battle/${res.battle_id}`);
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast.error(err?.response?.data?.detail || 'Не удалось начать бой');
    } finally {
      setBusy(false);
    }
  };

  const memberIds = new Set((party?.members ?? []).map((m) => m.character_id));
  const invitable = players.filter((p) => p.id !== characterId && !memberIds.has(p.id));

  const accepted = (party?.members ?? []).filter((m) => m.status === 'accepted');
  const teamsWithAccepted = new Set(accepted.map((m) => m.team));
  const canStart = accepted.length >= 2 && teamsWithAccepted.size >= 2;

  const statusBadge = (status: string) => {
    if (status === 'accepted')
      return <span className="text-green-400 text-[10px]">✓ готов</span>;
    if (status === 'declined')
      return <span className="text-site-red text-[10px]">✗ отказ</span>;
    return <span className="text-yellow-300/80 text-[10px]">⏳ ждёт</span>;
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="modal-content gold-outline gold-outline-thick w-[92%] max-w-[560px] max-h-[80vh] overflow-y-auto gold-scrollbar"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="gold-text text-xl uppercase">Сбор группы</h2>
          <button
            onClick={onClose}
            className="text-white/50 hover:text-white transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {loading || !party ? (
          <p className="text-white/50 text-sm py-8 text-center">Загрузка...</p>
        ) : (
          <>
            {/* Teams */}
            <div className="grid grid-cols-2 gap-3">
              {TEAMS.map((team) => {
                const members = party.members.filter((m) => m.team === team);
                return (
                  <div key={team} className="bg-white/5 rounded-card p-3">
                    <p className="text-white/50 text-xs font-medium uppercase tracking-wider mb-2">
                      Команда {team + 1}
                    </p>
                    <div className="flex flex-col gap-2">
                      {members.length === 0 && (
                        <p className="text-white/25 text-xs italic">Пусто</p>
                      )}
                      {members.map((m) => (
                        <div
                          key={m.character_id}
                          className="flex items-center gap-2 bg-white/5 rounded p-1.5"
                        >
                          {m.character_avatar ? (
                            <img
                              src={m.character_avatar}
                              alt=""
                              className="w-7 h-7 rounded object-cover flex-shrink-0"
                            />
                          ) : (
                            <div className="w-7 h-7 rounded bg-white/10 flex-shrink-0" />
                          )}
                          <div className="flex-1 min-w-0">
                            <p className="text-white text-xs truncate">
                              {m.character_name}
                              {m.is_leader && (
                                <span className="text-gold ml-1">★</span>
                              )}
                            </p>
                            <div className="flex items-center gap-1.5">
                              <span className="text-white/40 text-[10px]">
                                Ур.{m.character_level}
                              </span>
                              {statusBadge(m.status)}
                            </div>
                          </div>
                          {isLeader && !m.is_leader && (
                            <button
                              onClick={() => handleKick(m.character_id)}
                              disabled={busy}
                              className="text-white/30 hover:text-site-red transition-colors flex-shrink-0"
                              title="Убрать"
                            >
                              <X size={13} />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Invite list (leader only) */}
            {isLeader && (
              <div className="mt-4 border-t border-white/10 pt-3">
                <p className="text-white/50 text-xs font-medium uppercase tracking-wider mb-2">
                  Пригласить игроков на локации
                </p>
                {invitable.length === 0 ? (
                  <p className="text-white/25 text-xs italic">
                    Нет доступных игроков
                  </p>
                ) : (
                  <div className="flex flex-col gap-1.5 max-h-[160px] overflow-y-auto gold-scrollbar pr-1">
                    {invitable.map((p) => (
                      <div
                        key={p.id}
                        className="flex items-center gap-2 bg-white/5 rounded p-1.5"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-white text-xs truncate">{p.name}</p>
                          <span className="text-white/40 text-[10px]">
                            Ур.{p.level}
                          </span>
                        </div>
                        {TEAMS.map((team) => (
                          <button
                            key={team}
                            onClick={() => handleInvite(p.id, team)}
                            disabled={busy}
                            className="btn-line text-[10px] px-2 py-1 disabled:opacity-40"
                          >
                            → К{team + 1}
                          </button>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Footer actions */}
            <div className="mt-5 flex items-center justify-between gap-3">
              <button
                onClick={handleLeave}
                disabled={busy}
                className="text-site-red/70 hover:text-site-red text-xs transition-colors disabled:opacity-40"
              >
                {isLeader ? 'Распустить группу' : 'Покинуть группу'}
              </button>
              {isLeader && (
                <button
                  onClick={handleStart}
                  disabled={busy || !canStart}
                  className="btn-blue text-sm px-5 py-2 disabled:opacity-40 disabled:cursor-not-allowed"
                  title={
                    canStart
                      ? ''
                      : 'Нужно минимум 2 готовых игрока в двух командах'
                  }
                >
                  Начать бой
                </button>
              )}
            </div>
          </>
        )}
      </motion.div>
    </div>
  );
};

export default PartyLobbyModal;
