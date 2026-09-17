// FEAT-151 — party header (mock's leader header, composition only); FEAT-166 —
// restyled as an identity band inside the «Отряд» panel (like CharacterPanel).
// Preserves the existing leader entry points: avatar upload (click on avatar)
// and party rename (inline edit), both from FEAT-144.
import { useState } from 'react';
import { Check, Crown, Swords, X } from 'lucide-react';
import type { Party } from '../../../api/squads';
import GoldIconFrame from '../shared/GoldIconFrame';

const PARTY_MAX_SIZE = 4;
const PARTY_NAME_MAX_LENGTH = 60;
const AVATAR_SIZE = 56;

interface PartyHeaderCardProps {
  party: Party;
  /** Whether the viewer is the party leader (enables avatar upload + rename) */
  isLeader: boolean;
  busy: boolean;
  /** Opens the hidden file input for the squad avatar (leader only) */
  onAvatarClick: () => void;
  /** Saves a new party name (leader only) */
  onRename: (name: string) => Promise<void>;
}

const PartyHeaderCard = ({
  party,
  isLeader,
  busy,
  onAvatarClick,
  onRename,
}: PartyHeaderCardProps) => {
  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState(party.name);

  const acceptedCount = party.members.filter((m) => m.status === 'accepted').length;

  const startEditing = () => {
    setDraftName(party.name);
    setEditing(true);
  };

  const saveName = async () => {
    const trimmed = draftName.trim();
    if (!trimmed || trimmed === party.name) {
      setEditing(false);
      return;
    }
    await onRename(trimmed);
    setEditing(false);
  };

  const avatar = (
    <GoldIconFrame
      size={AVATAR_SIZE}
      shape="circle"
      glow
      src={party.avatar}
      alt={party.name}
      fallback={<Swords size={24} strokeWidth={1.6} className="text-gold" />}
    />
  );

  return (
    <div className="flex items-center gap-3.5 min-w-0">
      {/* 56px round avatar in glowing gold frame; leader → upload entry point */}
      {isLeader ? (
        <button
          type="button"
          disabled={busy}
          onClick={onAvatarClick}
          title="Сменить аватар отряда"
          className="relative shrink-0 rounded-full cursor-pointer group disabled:opacity-50"
        >
          {avatar}
          <span className="absolute inset-[2px] rounded-full bg-site-dark/70 opacity-0 group-hover:opacity-100 transition-opacity duration-200 ease-site flex items-center justify-center text-[10px] text-white leading-tight text-center">
            Сменить
          </span>
        </button>
      ) : (
        avatar
      )}

      <div className="flex flex-col gap-1 flex-1 min-w-0">
        {editing ? (
          <div className="flex items-center gap-2 min-w-0">
            <input
              type="text"
              value={draftName}
              maxLength={PARTY_NAME_MAX_LENGTH}
              autoFocus
              onChange={(e) => setDraftName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') saveName();
                if (e.key === 'Escape') setEditing(false);
              }}
              className="flex-1 min-w-0 bg-transparent border-b border-white/20 focus:border-gold outline-none py-0.5 text-white text-base transition-colors duration-200 ease-site"
            />
            <button
              type="button"
              disabled={busy}
              onClick={saveName}
              title="Сохранить название"
              className="flex items-center justify-center w-8 h-8 text-stat-energy hover:opacity-80 transition-opacity duration-200 ease-site disabled:opacity-40 shrink-0"
            >
              <Check size={17} strokeWidth={2.2} />
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setEditing(false)}
              title="Отмена"
              className="flex items-center justify-center w-8 h-8 text-white/40 hover:text-white transition-colors duration-200 ease-site disabled:opacity-40 shrink-0"
            >
              <X size={17} strokeWidth={2.2} />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2.5 min-w-0">
            <h4 className="gold-text text-xl font-medium uppercase leading-tight truncate">
              {party.name}
            </h4>
            {isLeader && (
              <span className="flex items-center gap-1 shrink-0 text-[10px] font-medium uppercase tracking-[0.05em] px-2 py-0.5 rounded text-gold bg-gold/[0.14]">
                <Crown size={11} strokeWidth={2.2} />
                Лидер
              </span>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <span className="text-xs text-white/75">
            {acceptedCount} / {PARTY_MAX_SIZE} в отряде
          </span>
          {isLeader && !editing && (
            <button
              type="button"
              disabled={busy}
              onClick={startEditing}
              className="text-[11px] text-white/40 hover:text-site-blue transition-colors duration-200 ease-site disabled:opacity-40 cursor-pointer"
            >
              Переименовать
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default PartyHeaderCard;
