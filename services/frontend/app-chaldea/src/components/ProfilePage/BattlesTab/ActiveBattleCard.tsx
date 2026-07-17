// FEAT-151 — active-battle preview card for the profile Battles tab.
// Data comes from GET /battles/{id}/preview (fetched once per mount, no polling).
import { motion } from 'motion/react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import type { BattlePreview, BattlePreviewParticipant } from '../../../api/battles';
import MiniStatBar from '../shared/MiniStatBar';

interface ActiveBattleCardProps {
  preview: BattlePreview;
  /** Existing battle-page route: /location/{locationId}/battle/{battleId} */
  battleUrl: string;
}

const initialOf = (name: string): string => name.trim().charAt(0).toUpperCase() || '?';

interface ParticipantRowProps {
  participant: BattlePreviewParticipant;
  /** MP bar is shown for allies only */
  showMana: boolean;
  /** Row tint: green for allies, red for enemies */
  tintClassName: string;
}

const ParticipantRow = ({ participant, showMana, tintClassName }: ParticipantRowProps) => {
  return (
    <div
      className={`flex gap-3 px-3 py-2.5 rounded-card border ${tintClassName} ${
        participant.is_alive ? '' : 'opacity-50'
      }`}
    >
      {/* Avatar in gold-gradient frame */}
      <div className="w-10 h-10 shrink-0 rounded-full p-[2px] bg-gradient-to-b from-gold-light to-gold-dark">
        <div className="w-full h-full rounded-full bg-site-dark flex items-center justify-center overflow-hidden">
          {participant.avatar ? (
            <img
              src={participant.avatar}
              alt={participant.name}
              className="w-full h-full object-cover"
            />
          ) : (
            <span className="text-xs font-medium text-white/50">
              {initialOf(participant.name)}
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-1 flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[13px] font-medium text-white truncate">
            {participant.name}
          </span>
          {!participant.is_alive && (
            <span className="text-[10px] font-medium uppercase tracking-[0.04em] text-white/40 shrink-0">
              Выбыл
            </span>
          )}
        </div>
        <MiniStatBar
          variant="hp"
          label="HP"
          current={participant.hp}
          max={participant.max_hp}
        />
        {showMana && (
          <MiniStatBar
            variant="mana"
            label="MP"
            current={participant.mana}
            max={participant.max_mana}
          />
        )}
      </div>
    </div>
  );
};

const ActiveBattleCard = ({ preview, battleUrl }: ActiveBattleCardProps) => {
  const allies = preview.participants.filter((p) => p.is_ally);
  const enemies = preview.participants.filter((p) => !p.is_ally);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="relative rounded-card border border-site-red/40 bg-site-bg shadow-card overflow-hidden"
    >
      {/* Subtle red tint layer (no freestyle gradients) */}
      <span className="absolute inset-0 bg-site-red/[0.06] pointer-events-none" aria-hidden />

      <div className="relative flex flex-col gap-4 p-4 sm:p-5">
        {/* Header: pulsing dot + status + location · turn */}
        <div className="flex items-center gap-3 flex-wrap">
          <span className="w-2.5 h-2.5 rounded-full bg-stat-hp shadow-[0_0_10px_rgba(233,69,69,0.9)] animate-pulse shrink-0" />
          <span className="text-sm font-medium uppercase tracking-[0.08em] text-site-red">
            Бой идёт
          </span>
          <span className="text-xs text-white/50">
            {preview.location_name ?? 'Локация'} · Ход {preview.turn_number}
          </span>
        </div>

        {/* Turn-order strip */}
        {preview.turn_order.length > 0 && (
          <div className="flex items-center gap-2.5 flex-wrap px-3.5 py-3 rounded-card bg-black/30">
            <span className="text-[10px] font-medium uppercase tracking-[0.08em] text-white/45 shrink-0">
              Очередь
            </span>
            <div className="flex items-center gap-2 flex-wrap">
              {preview.turn_order.map((entry) => (
                <span
                  key={entry.participant_id}
                  title={entry.name}
                  className={`flex w-[34px] h-[34px] rounded-full p-[2px] ${
                    entry.is_current
                      ? 'bg-gradient-to-b from-gold-light to-gold-dark outline outline-2 outline-gold/70 outline-offset-2'
                      : 'bg-white/20 opacity-50'
                  }`}
                >
                  <span className="w-full h-full rounded-full bg-site-dark flex items-center justify-center text-[13px] font-medium text-white">
                    {initialOf(entry.name)}
                  </span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Combatants: allies / enemies */}
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-stat-energy">
              Ваш отряд
            </span>
            {allies.map((p) => (
              <ParticipantRow
                key={p.participant_id}
                participant={p}
                showMana
                tintClassName="bg-stat-energy/[0.06] border-stat-energy/[0.18]"
              />
            ))}
          </div>
          <div className="flex flex-col gap-2">
            <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-site-red">
              Противники
            </span>
            {enemies.map((p) => (
              <ParticipantRow
                key={p.participant_id}
                participant={p}
                showMana={false}
                tintClassName="bg-site-red/[0.06] border-site-red/[0.18]"
              />
            ))}
          </div>
        </div>

        {/* Footer: go-to-battle */}
        <div className="flex items-center justify-between gap-3 flex-wrap pt-0.5">
          <span className="text-xs text-white/50">
            Нажмите «Перейти к бою», чтобы продолжить сражение
          </span>
          <Link
            to={battleUrl}
            className="btn-blue flex items-center gap-2 px-5 py-2.5 text-xs font-medium uppercase tracking-[0.04em]"
          >
            Перейти к бою
            <ArrowRight size={14} strokeWidth={2.2} className="shrink-0" />
          </Link>
        </div>
      </div>
    </motion.div>
  );
};

export default ActiveBattleCard;
