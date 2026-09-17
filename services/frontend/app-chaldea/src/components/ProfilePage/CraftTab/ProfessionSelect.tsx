// FEAT-151/166 — CraftTab no-profession screen: full-width PanelShell
// «Выбор профессии» with profession cards (gold icon frame, name, short
// description, «Выбрать») and the confirmation dialog (ModalShell, portaled).
import { useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { motion } from 'motion/react';
import { Hammer } from 'lucide-react';
import type { Profession } from '../../../types/professions';
import PanelShell from '../PanelShell';
import { MotionProfileCard } from '../shared/ProfileCard';
import GoldIconFrame from '../shared/GoldIconFrame';
import ModalShell from '../shared/ModalShell';

interface ProfessionSelectProps {
  professions: Profession[];
  loading: boolean;
  onSelect: (professionId: number) => void;
  /** Right side of the panel header (active craft buffs) */
  headerExtra?: ReactNode;
}

const ProfessionSelect = ({ professions, loading, onSelect, headerExtra }: ProfessionSelectProps) => {
  const [confirmId, setConfirmId] = useState<number | null>(null);

  const confirmProfession = professions.find((p) => p.id === confirmId);
  // Keep the last shown profession so the dialog body stays filled during its exit animation
  const shownProfessionRef = useRef<Profession | undefined>(undefined);
  if (confirmProfession) shownProfessionRef.current = confirmProfession;
  const shownProfession = shownProfessionRef.current;

  const handleConfirm = () => {
    if (confirmId !== null) {
      onSelect(confirmId);
      setConfirmId(null);
    }
  };

  return (
    <PanelShell
      title="Выбор профессии"
      icon={<Hammer size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
      headerExtra={headerExtra}
    >
      <p className="text-white/50 text-sm mb-4">
        Профессия определяет, какие предметы вы сможете создавать. Выбрать можно только одну.
      </p>

      <motion.div
        initial="hidden"
        animate="visible"
        variants={{
          hidden: {},
          visible: { transition: { staggerChildren: 0.06 } },
        }}
        className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3.5"
      >
        {[...professions]
          .filter((p) => p.is_active)
          .sort((a, b) => a.sort_order - b.sort_order)
          .map((prof) => (
            <MotionProfileCard
              key={prof.id}
              interactive
              variants={{
                hidden: { opacity: 0, y: 10 },
                visible: { opacity: 1, y: 0 },
              }}
              className="flex flex-col gap-3 p-4 !cursor-default"
            >
              {/* Icon frame + name */}
              <div className="flex items-center gap-3 min-w-0">
                <GoldIconFrame
                  size={56}
                  src={prof.icon}
                  alt={prof.name}
                  fallback={<span className="text-gold text-lg">{prof.name.charAt(0)}</span>}
                />
                <h4 className="text-white text-[15px] font-medium leading-tight break-words min-w-0">
                  {prof.name}
                </h4>
              </div>

              {/* Description */}
              {prof.description && (
                <p className="text-white/50 text-xs leading-relaxed line-clamp-3">
                  {prof.description}
                </p>
              )}

              {/* Select button */}
              <button
                type="button"
                onClick={() => setConfirmId(prof.id)}
                disabled={loading}
                className="mt-auto w-full py-2.5 rounded-[10px] text-xs font-medium uppercase tracking-[0.04em] bg-site-blue/20 text-site-blue hover:bg-site-blue/30 transition-colors duration-200 ease-site disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Выбрать
              </button>
            </MotionProfileCard>
          ))}
      </motion.div>

      {/* Confirmation dialog */}
      <ModalShell
        open={Boolean(confirmProfession)}
        onClose={() => setConfirmId(null)}
        title="Подтверждение"
        icon={<Hammer size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
        size="sm"
        footer={
          <>
            <button
              type="button"
              onClick={() => setConfirmId(null)}
              className="btn-line w-full sm:w-auto"
            >
              Отмена
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={loading}
              className="btn-blue w-full sm:w-auto disabled:opacity-50"
            >
              {loading ? 'Выбор...' : 'Подтвердить'}
            </button>
          </>
        }
      >
        {shownProfession && (
          <p className="text-white text-sm sm:text-base">
            Вы уверены, что хотите выбрать профессию{' '}
            <span className="text-gold font-medium">{shownProfession.name}</span>?
          </p>
        )}
      </ModalShell>
    </PanelShell>
  );
};

export default ProfessionSelect;
