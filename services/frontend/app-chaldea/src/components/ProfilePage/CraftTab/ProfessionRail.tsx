// FEAT-151 — CraftTab profession rail (mock 941-952): all professions as
// horizontal chips. The active one is gold-highlighted; the rest are dimmed.
// Clicking a non-active profession opens the existing change-profession modal
// (with its progress-loss warning), preselecting the clicked profession.
// FEAT-166: the dialog uses the shared portaled ModalShell.
import { useState } from 'react';
import { Hammer } from 'lucide-react';
import type { CharacterProfession, Profession } from '../../../types/professions';
import ModalShell from '../shared/ModalShell';
import ProfileCard from '../shared/ProfileCard';
import GoldIconFrame from '../shared/GoldIconFrame';

interface ProfessionRailProps {
  /** All professions from craftingSlice (filtered to is_active inside) */
  professions: Profession[];
  characterProfession: CharacterProfession;
  /** True while the change request is in flight */
  loading: boolean;
  onChangeProfession: (professionId: number) => void;
}

const ProfessionRail = ({
  professions,
  characterProfession,
  loading,
  onChangeProfession,
}: ProfessionRailProps) => {
  const [showChangeModal, setShowChangeModal] = useState(false);
  const [selectedNewId, setSelectedNewId] = useState<number | null>(null);

  const activeId = characterProfession.profession.id;
  const rail = [...professions]
    .filter((p) => p.is_active)
    .sort((a, b) => a.sort_order - b.sort_order);
  const otherProfessions = rail.filter((p) => p.id !== activeId);

  const openChangeModal = (professionId: number) => {
    setSelectedNewId(professionId);
    setShowChangeModal(true);
  };

  const closeModal = () => {
    setShowChangeModal(false);
    setSelectedNewId(null);
  };

  const handleConfirmChange = () => {
    if (selectedNewId !== null) {
      onChangeProfession(selectedNewId);
      closeModal();
    }
  };

  return (
    <>
      {/* Horizontal chip rail — scrolls on narrow screens */}
      <div className="flex gap-2 overflow-x-auto gold-scrollbar pb-1">
        {rail.map((prof) => {
          const isActive = prof.id === activeId;
          return (
            <button
              key={prof.id}
              type="button"
              onClick={() => {
                if (!isActive) openChangeModal(prof.id);
              }}
              className={`chip-outline flex items-center gap-2.5 shrink-0 px-4 py-2 rounded-card whitespace-nowrap transition-all duration-200 ease-site ${
                isActive
                  ? 'chip-outline-active cursor-default'
                  : 'opacity-50 hover:opacity-80 cursor-pointer'
              }`}
            >
              {prof.icon ? (
                <img
                  src={prof.icon}
                  alt={prof.name}
                  className="w-[26px] h-[26px] rounded-md object-cover shrink-0"
                />
              ) : (
                <span className="w-[26px] h-[26px] rounded-md bg-white/10 flex items-center justify-center shrink-0">
                  <span className="text-gold text-xs">{prof.name.charAt(0)}</span>
                </span>
              )}
              <span className="flex flex-col items-start gap-px">
                <span
                  className={`text-[13px] font-medium leading-tight ${
                    isActive ? 'text-gold' : 'text-white'
                  }`}
                >
                  {prof.name}
                </span>
                <span className="font-mono tabular-nums text-[9.5px] text-white/45 leading-tight">
                  {isActive
                    ? `Ранг ${characterProfession.current_rank} · ${characterProfession.rank_name}`
                    : 'Не изучена'}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      {/* Change-profession confirmation dialog (existing flow, progress-loss warning) */}
      <ModalShell
        open={showChangeModal}
        onClose={closeModal}
        title="Сменить профессию"
        icon={<Hammer size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
        size="sm"
        footer={
          <>
            <button type="button" onClick={closeModal} className="btn-line w-full sm:w-auto">
              Отмена
            </button>
            <button
              type="button"
              onClick={handleConfirmChange}
              disabled={loading || selectedNewId === null}
              className="btn-blue w-full sm:w-auto disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Смена...' : 'Сменить'}
            </button>
          </>
        }
      >
        {/* Warning */}
        <ProfileCard variant="danger" className="mb-4 p-2.5">
          <p className="text-site-red text-sm">
            Прогресс будет потерян, выученные рецепты сохранятся. Продолжить?
          </p>
        </ProfileCard>

        {/* Profession selector */}
        <div className="flex flex-col gap-2">
          {otherProfessions.map((p) => (
            <ProfileCard
              key={p.id}
              as="button"
              interactive
              active={selectedNewId === p.id}
              onClick={() => setSelectedNewId(p.id)}
              className="!flex items-center gap-3 p-2.5"
            >
              <GoldIconFrame
                size={36}
                src={p.icon}
                alt={p.name}
                fallback={<span className="text-gold text-sm">{p.name.charAt(0)}</span>}
              />
              <div className="min-w-0">
                <p className="text-white text-sm font-medium break-words">{p.name}</p>
                {p.description && (
                  <p className="text-white/40 text-xs line-clamp-1">{p.description}</p>
                )}
              </div>
            </ProfileCard>
          ))}
        </div>
      </ModalShell>
    </>
  );
};

export default ProfessionRail;
