import { motion, AnimatePresence } from 'motion/react';
import type { SessionMember } from '../../api/dungeons';

interface DungeonPartyPanelProps {
  members: SessionMember[];
  maxSize: number;
  currentCharacterId: number | null;
  isLeader: boolean;
  isForming?: boolean;
  onLeave?: () => void;
  onInviteClick?: () => void;
  leaveLoading?: boolean;
}

const statusLabel: Record<string, string> = {
  alive: 'Жив',
  dead: 'Мёртв',
  disconnected: 'Отключён',
};

const statusColor: Record<string, string> = {
  alive: 'bg-green-500',
  dead: 'bg-site-red',
  disconnected: 'bg-yellow-500',
};

const DungeonPartyPanel = ({
  members,
  maxSize,
  currentCharacterId,
  isLeader,
  isForming = false,
  onLeave,
  onInviteClick,
  leaveLoading = false,
}: DungeonPartyPanelProps) => {
  const isCurrentCharacterLeader = members.some(
    (m) => m.character_id === currentCharacterId && m.is_leader,
  );

  return (
    <div className="bg-black/40 rounded-card p-4 backdrop-blur-sm">
      <div className="flex items-center justify-between mb-3">
        <h3 className="gold-text text-lg font-medium uppercase">
          Группа
        </h3>
        <span className="text-white/60 text-sm">
          {members.length}/{maxSize}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        <AnimatePresence mode="popLayout">
          {members.map((member) => (
            <motion.div
              key={member.character_id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 transition-colors"
            >
              {/* Status dot */}
              <div
                className={`w-2.5 h-2.5 rounded-full shrink-0 ${statusColor[member.status] ?? 'bg-white/30'}`}
                title={statusLabel[member.status] ?? member.status}
              />

              {/* Name + leader badge */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-white text-sm truncate">
                    {member.name}
                  </span>
                  {member.is_leader && (
                    <span className="text-gold text-[10px] font-medium uppercase tracking-wide shrink-0">
                      Лидер
                    </span>
                  )}
                </div>
              </div>

              {/* Status label */}
              <span
                className={`text-xs shrink-0 ${
                  member.status === 'alive'
                    ? 'text-green-400'
                    : member.status === 'dead'
                      ? 'text-site-red'
                      : 'text-yellow-400'
                }`}
              >
                {statusLabel[member.status] ?? member.status}
              </span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Action buttons */}
      <div className="flex flex-col sm:flex-row gap-2 mt-4">
        {isForming && isLeader && members.length < maxSize && onInviteClick && (
          <button
            onClick={onInviteClick}
            className="btn-blue text-sm px-4 py-2 flex-1"
          >
            Пригласить
          </button>
        )}

        {!isCurrentCharacterLeader && onLeave && (
          <button
            onClick={onLeave}
            disabled={leaveLoading}
            className="text-sm px-4 py-2 rounded-card border border-white/20 text-white/70 hover:text-white hover:border-white/40 transition-colors disabled:opacity-50 flex-1"
          >
            {leaveLoading ? 'Выход...' : 'Покинуть группу'}
          </button>
        )}
      </div>
    </div>
  );
};

export default DungeonPartyPanel;
