// FEAT-151 — «Создать отряд» card for the no-party state (mock composition,
// design-system styles). Create flow preserved from FEAT-144.
// FEAT-166 — title moved into the PanelShell header band, shared primitives.
import { Check, MapPin, Plus, Star, Swords } from 'lucide-react';
import PanelShell from '../PanelShell';
import ProfileCard from '../shared/ProfileCard';
import GoldIconFrame from '../shared/GoldIconFrame';

const PARTY_NAME_MAX_LENGTH = 60;

const PARTY_BENEFITS = [
  'До 4 участников в постоянном отряде',
  'Совместные бои и данжи',
  'Бонус к опыту рядом с соотрядцами',
];

interface PartyCreateCardProps {
  name: string;
  onNameChange: (name: string) => void;
  busy: boolean;
  onCreate: () => void;
}

const PartyCreateCard = ({ name, onNameChange, busy, onCreate }: PartyCreateCardProps) => {
  return (
    <PanelShell
      title="Создать отряд"
      icon={<Plus size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
      bodyClassName="flex flex-col gap-4 p-4 lg:p-5"
    >
      {/* Intro: gold icon frame + status line */}
      <div className="flex items-center gap-3.5 min-w-0">
        <GoldIconFrame size={54} shape="circle" glow>
          <Swords size={24} strokeWidth={1.6} className="text-gold" />
        </GoldIconFrame>
        <span className="text-sm text-white/60 min-w-0">Вы пока не состоите в отряде</span>
      </div>

      {/* Party name input */}
      <div className="flex flex-col gap-2">
        <label
          htmlFor="party-name-input"
          className="text-[11px] uppercase tracking-[0.08em] text-white/50"
        >
          Название отряда
        </label>
        <div className="flex items-center gap-2.5 px-4 py-3 rounded-card bg-white/[0.03] border border-white/10 focus-within:border-gold/50 transition-colors duration-200 ease-site">
          <Star size={16} strokeWidth={1.8} className="text-gold/70 shrink-0" />
          <input
            id="party-name-input"
            type="text"
            value={name}
            maxLength={PARTY_NAME_MAX_LENGTH}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="Напр. «Хранители Зари»"
            className="flex-1 min-w-0 bg-transparent outline-none border-none text-white text-base sm:text-sm placeholder-white/30"
          />
          <span className="font-mono tabular-nums text-[11px] text-white/35 shrink-0">
            {name.length}/{PARTY_NAME_MAX_LENGTH}
          </span>
        </div>
      </div>

      {/* Benefits list */}
      <ProfileCard className="flex flex-col gap-2.5 p-4">
        <span className="text-[11px] uppercase tracking-[0.08em] text-white/45">
          Что даёт отряд
        </span>
        {PARTY_BENEFITS.map((benefit) => (
          <div key={benefit} className="flex items-center gap-2.5">
            <Check size={15} strokeWidth={2.2} className="text-stat-energy shrink-0" />
            <span className="text-[13px] text-white/80">{benefit}</span>
          </div>
        ))}
      </ProfileCard>

      {/* Location hint */}
      <div className="flex items-center gap-2 text-[11px] text-white/40">
        <MapPin size={14} strokeWidth={2} className="shrink-0" />
        Приглашать можно только игроков на вашей локации
      </div>

      <button
        type="button"
        disabled={busy}
        onClick={onCreate}
        className="btn-blue w-full sm:w-auto sm:self-start flex items-center justify-center gap-2 py-3 text-xs font-medium uppercase tracking-[0.05em] disabled:opacity-50"
      >
        <Plus size={16} strokeWidth={2} className="shrink-0" />
        Создать отряд
      </button>
    </PanelShell>
  );
};

export default PartyCreateCard;
