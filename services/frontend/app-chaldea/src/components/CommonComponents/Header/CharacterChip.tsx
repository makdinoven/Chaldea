import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { MapPin, User } from 'react-feather';
import { AnimatePresence, motion } from 'motion/react';
import { useAppSelector } from '../../../redux/store';
import CharacterSwitchDropdown from './CharacterSwitchDropdown';

export const CoinIcon = ({ size = 12 }: { size?: number }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    className="flex-shrink-0"
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="9" />
    <circle cx="12" cy="12" r="4" />
  </svg>
);

/**
 * Desktop header character chip (reference `.hdr-chip` layout):
 * gold-ring avatar + name / level + coins / location link.
 * Click opens the character switch dropdown.
 */
const CharacterChip = () => {
  const character = useAppSelector((state) => state.user.character);
  const userId = useAppSelector((state) => state.user.id);

  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  const coins = typeof character?.currency_balance === 'number' ? character.currency_balance : null;
  const level = typeof character?.level === 'number' ? character.level : null;

  return (
    <div ref={containerRef} className="relative flex-shrink-0">
      {/* div, not button: contains a nested location <Link> */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => setOpen((prev) => !prev)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setOpen((prev) => !prev);
          }
        }}
        className="flex items-center gap-2.5 pl-1.5 pr-3 py-1.5 rounded-full border border-gold/25 bg-black/30 hover:border-gold/50 transition-colors duration-200 ease-site cursor-pointer select-none"
        aria-label={character ? `Персонаж: ${character.name}` : 'Персонаж'}
        aria-expanded={open}
      >
        {/* Gold-ring avatar */}
        <div className="w-10 h-10 rounded-full p-[2px] bg-gradient-to-b from-gold-light to-gold-dark flex-shrink-0">
          <div className="w-full h-full rounded-full bg-site-dark overflow-hidden flex items-center justify-center">
            {character?.avatar ? (
              <img
                src={character.avatar}
                alt={character.name}
                className="w-full h-full object-cover"
              />
            ) : (
              <User size={20} className="text-white/50" />
            )}
          </div>
        </div>

        {character ? (
          <div className="flex flex-col items-start gap-0.5 w-[104px] xl:w-[128px] min-w-0">
            <span className="text-white text-xs font-medium leading-none truncate w-full text-left">
              {character.name}
            </span>
            <span className="flex items-center gap-2 leading-none">
              {level != null && (
                <span className="text-white/70 text-[11px] whitespace-nowrap">Ур. {level}</span>
              )}
              {coins != null && (
                <span className="flex items-center gap-1 text-gold text-[11px] whitespace-nowrap">
                  <CoinIcon size={11} />
                  {coins.toLocaleString('ru-RU')}
                </span>
              )}
            </span>
            {character.current_location ? (
              <Link
                to={`/location/${character.current_location.id}`}
                onClick={(e) => e.stopPropagation()}
                title="Перейти в локацию"
                className="flex items-center gap-1 text-site-blue hover:text-gold transition-colors duration-200 ease-site leading-none max-w-full"
              >
                <MapPin size={11} className="flex-shrink-0" />
                <span className="text-[10.5px] font-medium truncate">
                  {character.current_location.name}
                </span>
              </Link>
            ) : (
              <span className="text-white/30 text-[10.5px] leading-none">Вне мира</span>
            )}
          </div>
        ) : (
          <span className="text-white/70 text-xs font-medium pr-1 whitespace-nowrap">
            Персонаж
          </span>
        )}
      </div>

      <AnimatePresence>
        {open && (
          userId && character ? (
            <CharacterSwitchDropdown
              className="absolute top-full right-0 mt-2 w-[280px]"
              onClose={() => setOpen(false)}
            />
          ) : (
            /* Guest or no active character — fallback (current behavior) */
            <motion.div
              initial={{ opacity: 0, y: -5 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -5 }}
              transition={{ duration: 0.15 }}
              className="dropdown-menu absolute top-full right-0 mt-2 z-50"
            >
              <Link to="/createCharacter" className="dropdown-item" onClick={() => setOpen(false)}>
                Создать
              </Link>
              <Link to="/selectCharacter" className="dropdown-item" onClick={() => setOpen(false)}>
                Выбрать
              </Link>
            </motion.div>
          )
        )}
      </AnimatePresence>
    </div>
  );
};

export default CharacterChip;
