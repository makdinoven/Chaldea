import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import axios from 'axios';
import {
  getPendingInvitations,
  respondToInvitation,
  cancelInvitation,
} from '../../../api/pvp';
import type { PvpInvitation, OutgoingInvitation } from '../../../api/pvp';

const POLL_INTERVAL = 7000; // 7 seconds

const BATTLE_TYPE_LABELS: Record<string, string> = {
  pvp_training: 'Тренировочный бой',
  pvp_death: 'Смертельный бой',
};

interface PendingInvitationsPanelProps {
  locationId: number;
}

const PendingInvitationsPanel = ({ locationId }: PendingInvitationsPanelProps) => {
  const navigate = useNavigate();
  const [incoming, setIncoming] = useState<PvpInvitation[]>([]);
  const [outgoing, setOutgoing] = useState<OutgoingInvitation[]>([]);
  const [respondingId, setRespondingId] = useState<number | null>(null);
  const [cancellingId, setCancellingId] = useState<number | null>(null);

  const fetchInvitations = useCallback(async () => {
    try {
      const data = await getPendingInvitations();
      setIncoming(data.incoming);
      setOutgoing(data.outgoing);
    } catch {
      // Silently fail on poll — not critical
    }
  }, []);

  // Initial fetch + polling
  useEffect(() => {
    fetchInvitations();
    const interval = setInterval(fetchInvitations, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchInvitations]);

  const handleAccept = async (invitationId: number) => {
    setRespondingId(invitationId);
    try {
      const result = await respondToInvitation(invitationId, 'accept');
      toast.success('Вызов принят! Бой начинается.');
      setIncoming((prev) => prev.filter((inv) => inv.invitation_id !== invitationId));
      if (result.battle_id) {
        navigate(`/location/${locationId}/battle/${result.battle_id}`);
      }
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось принять вызов';
      toast.error(message);
    } finally {
      setRespondingId(null);
    }
  };

  const handleDecline = async (invitationId: number) => {
    setRespondingId(invitationId);
    try {
      await respondToInvitation(invitationId, 'decline');
      toast('Вызов отклонён');
      setIncoming((prev) => prev.filter((inv) => inv.invitation_id !== invitationId));
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось отклонить вызов';
      toast.error(message);
    } finally {
      setRespondingId(null);
    }
  };

  const handleCancel = async (invitationId: number) => {
    setCancellingId(invitationId);
    try {
      await cancelInvitation(invitationId);
      toast('Вызов отменён');
      setOutgoing((prev) => prev.filter((inv) => inv.invitation_id !== invitationId));
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось отменить вызов';
      toast.error(message);
    } finally {
      setCancellingId(null);
    }
  };

  // Nothing to show
  if (incoming.length === 0 && outgoing.length === 0) return null;

  return (
    <section className="gold-outline relative rounded-card bg-black/50 p-4 sm:p-5 flex flex-col gap-4">
      <h2 className="gold-text text-lg sm:text-xl font-medium uppercase">
        Вызовы на бой
      </h2>

      {/* Incoming invitations */}
      {incoming.length > 0 && (
        <div className="flex flex-col gap-3">
          <h3 className="text-white/70 text-xs uppercase tracking-wider font-medium">
            Входящие
          </h3>
          <AnimatePresence mode="popLayout">
            {incoming.map((inv) => (
              <motion.div
                key={inv.invitation_id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.2 }}
                className="flex flex-col sm:flex-row sm:items-center gap-3 bg-black/40 rounded-card p-3"
              >
                {/* Initiator info */}
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div className="gold-outline relative w-10 h-10 sm:w-14 sm:h-14 rounded-full overflow-hidden bg-black/40 shrink-0">
                    {inv.initiator_avatar ? (
                      <img
                        src={inv.initiator_avatar}
                        alt={inv.initiator_name}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-white/20">
                        <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5 sm:w-7 sm:h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col min-w-0">
                    <span className="text-white text-xs sm:text-sm font-medium truncate">
                      {inv.initiator_name}
                    </span>
                    <span className="gold-text text-[10px] sm:text-xs">
                      LVL {inv.initiator_level}
                    </span>
                    <span className="text-site-blue text-[10px] sm:text-xs">
                      {BATTLE_TYPE_LABELS[inv.battle_type] ?? inv.battle_type}
                    </span>
                  </div>
                </div>

                {/* Action buttons */}
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => handleAccept(inv.invitation_id)}
                    disabled={respondingId === inv.invitation_id}
                    className="btn-blue text-[10px] sm:text-xs px-3 py-1 sm:px-4 sm:py-1.5 disabled:opacity-50"
                  >
                    {respondingId === inv.invitation_id ? '...' : 'Принять'}
                  </button>
                  <button
                    onClick={() => handleDecline(inv.invitation_id)}
                    disabled={respondingId === inv.invitation_id}
                    className="btn-line text-[10px] sm:text-xs px-3 py-1 sm:px-4 sm:py-1.5 disabled:opacity-50"
                  >
                    Отклонить
                  </button>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Outgoing invitations */}
      {outgoing.length > 0 && (
        <div className="flex flex-col gap-3">
          <h3 className="text-white/70 text-xs uppercase tracking-wider font-medium">
            Исходящие
          </h3>
          <AnimatePresence mode="popLayout">
            {outgoing.map((inv) => (
              <motion.div
                key={inv.invitation_id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.2 }}
                className="flex flex-col sm:flex-row sm:items-center gap-3 bg-black/40 rounded-card p-3"
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div className="flex flex-col min-w-0">
                    <span className="text-white text-xs sm:text-sm font-medium truncate">
                      Вызов для {inv.target_name}
                    </span>
                    <span className="text-site-blue text-[10px] sm:text-xs">
                      {BATTLE_TYPE_LABELS[inv.battle_type] ?? inv.battle_type}
                    </span>
                    <span className="text-white/40 text-[10px]">
                      Ожидание ответа...
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => handleCancel(inv.invitation_id)}
                  disabled={cancellingId === inv.invitation_id}
                  className="btn-line text-[10px] sm:text-xs px-3 py-1 sm:px-4 sm:py-1.5 disabled:opacity-50 shrink-0"
                >
                  {cancellingId === inv.invitation_id ? '...' : 'Отменить'}
                </button>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </section>
  );
};

export default PendingInvitationsPanel;
