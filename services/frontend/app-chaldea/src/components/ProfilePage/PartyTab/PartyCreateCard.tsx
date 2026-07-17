// FEAT-151 — «Создать отряд» card for the no-party state (mock composition,
// design-system styles). Create flow preserved from FEAT-144.
import { Check, MapPin, Plus, Star, Swords } from 'lucide-react';
import PanelShell from '../PanelShell';

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
      className="bg-gradient-to-b from-gold/[0.06] to-transparent"
      bodyClassName="flex flex-col gap-4 p-5 sm:p-6"
    >
      {/* Heading: gold icon frame + title */}
      <div className="flex items-center gap-3.5">
        <div className="w-[54px] h-[54px] shrink-0 rounded-[14px] p-[2px] bg-gradient-to-b from-gold-light to-gold-dark shadow-[0_0_16px_rgba(240,217,92,0.35)]">
          <div className="w-full h-full rounded-xl bg-site-dark flex items-center justify-center">
            <Swords size={26} strokeWidth={1.6} className="text-gold" />
          </div>
        </div>
        <div className="flex flex-col gap-1 min-w-0">
          <h4 className="text-white text-lg font-medium">Создать отряд</h4>
          <span className="text-xs text-white/50">Вы пока не состоите в отряде</span>
        </div>
      </div>

      {/* Party name input */}
      <div className="flex flex-col gap-2">
        <label
          htmlFor="party-name-input"
          className="text-[11px] uppercase tracking-[0.08em] text-white/50"
        >
          Название отряда
        </label>
        <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-black/30 border border-gold/20 focus-within:border-gold/50 transition-colors duration-200 ease-site">
          <Star size={16} strokeWidth={1.8} className="text-gold/70 shrink-0" />
          <input
            id="party-name-input"
            type="text"
            value={name}
            maxLength={PARTY_NAME_MAX_LENGTH}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="Напр. «Хранители Зари»"
            className="flex-1 min-w-0 bg-transparent outline-none border-none text-white text-sm placeholder-white/30"
          />
          <span className="font-mono tabular-nums text-[11px] text-white/35 shrink-0">
            {name.length}/{PARTY_NAME_MAX_LENGTH}
          </span>
        </div>
      </div>

      {/* Benefits list */}
      <div className="flex flex-col gap-2.5 rounded-xl bg-white/[0.03] border border-white/[0.07] p-4">
        <span className="text-[11px] uppercase tracking-[0.08em] text-white/45">
          Что даёт отряд
        </span>
        {PARTY_BENEFITS.map((benefit) => (
          <div key={benefit} className="flex items-center gap-2.5">
            <Check size={15} strokeWidth={2.2} className="text-stat-energy shrink-0" />
            <span className="text-[13px] text-white/80">{benefit}</span>
          </div>
        ))}
      </div>

      {/* Location hint */}
      <div className="flex items-center gap-2 text-[11px] text-white/40">
        <MapPin size={14} strokeWidth={2} className="shrink-0" />
        Приглашать можно только игроков на вашей локации
      </div>

      <button
        type="button"
        disabled={busy}
        onClick={onCreate}
        className="btn-blue w-full flex items-center justify-center gap-2 py-3 text-xs font-medium uppercase tracking-[0.05em] disabled:opacity-50"
      >
        <Plus size={16} strokeWidth={2} className="shrink-0" />
        Создать отряд
      </button>
    </PanelShell>
  );
};

export default PartyCreateCard;
