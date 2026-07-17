// FEAT-151 — gold party header card (mock's leader header, composition only).
// Preserves the existing leader entry points: avatar upload (click on avatar)
// and party rename (inline edit), both from FEAT-144.
import { useState } from 'react';
import { Check, Crown, Swords, X } from 'lucide-react';
import type { Party } from '../../../api/squads';

const PARTY_MAX_SIZE = 4;
const PARTY_NAME_MAX_LENGTH = 60;

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

  const avatarInner = (
    <div className="w-full h-full rounded-xl bg-site-dark flex items-center justify-center overflow-hidden">
      {party.avatar ? (
        <img src={party.avatar} alt={party.name} className="w-full h-full object-cover" />
      ) : (
        <Swords size={24} strokeWidth={1.6} className="text-gold" />
      )}
    </div>
  );

  return (
    <div className="relative rounded-card border border-gold/[0.22] bg-site-bg bg-gradient-to-b from-gold/[0.07] to-transparent shadow-card flex items-center gap-4 p-4 sm:px-5">
      {/* 56px avatar in glowing gold frame; leader → upload entry point */}
      {isLeader ? (
        <button
          type="button"
          disabled={busy}
          onClick={onAvatarClick}
          title="Сменить аватар отряда"
          className="relative w-14 h-14 shrink-0 rounded-[14px] p-[2px] bg-gradient-to-b from-gold-light to-gold-dark shadow-[0_0_16px_rgba(240,217,92,0.35)] cursor-pointer group disabled:opacity-50"
        >
          {avatarInner}
          <span className="absolute inset-[2px] rounded-xl bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity duration-200 ease-site flex items-center justify-center text-[10px] text-white leading-tight text-center">
            Сменить
          </span>
        </button>
      ) : (
        <div className="w-14 h-14 shrink-0 rounded-[14px] p-[2px] bg-gradient-to-b from-gold-light to-gold-dark shadow-[0_0_16px_rgba(240,217,92,0.35)]">
          {avatarInner}
        </div>
      )}

      <div className="flex flex-col gap-1 flex-1 min-w-0">
        {editing ? (
          <div className="flex items-center gap-2">
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
              className="text-stat-energy hover:opacity-80 transition-opacity duration-200 ease-site disabled:opacity-40 shrink-0"
            >
              <Check size={17} strokeWidth={2.2} />
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setEditing(false)}
              title="Отмена"
              className="text-white/40 hover:text-white transition-colors duration-200 ease-site disabled:opacity-40 shrink-0"
            >
              <X size={17} strokeWidth={2.2} />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2.5 min-w-0">
            <h4 className="text-white text-lg font-medium truncate">{party.name}</h4>
            {isLeader && (
              <span className="flex items-center gap-1 shrink-0 text-[10px] font-medium uppercase tracking-[0.05em] px-2 py-0.5 rounded text-gold bg-gold/[0.14]">
                <Crown size={11} strokeWidth={2.2} />
                Лидер
              </span>
            )}
          </div>
        )}

        <div className="flex items-center gap-2.5">
          <span className="text-xs text-white/55">
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
