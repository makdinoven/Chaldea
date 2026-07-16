import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { User } from 'react-feather';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { getMe } from '../../../redux/slices/userSlice';
import { fetchUserCharacters } from '../../../api/userProfile';
import { BASE_URL_DEFAULT } from '../../../api/api';

interface SwitchCharacterItem {
  id: number;
  name: string;
  avatar: string | null;
  level: number | null;
}

interface CharacterSwitchDropdownProps {
  /** Positioning classes relative to the (relative) trigger container */
  className?: string;
  onClose: () => void;
}

/**
 * Dropdown listing the user's characters with one-click switching of the
 * active character. Used by the desktop CharacterChip and the mobile
 * character strip. Follows the SelectCharacterPage switch pattern:
 * PUT /users/{id}/update_character → re-dispatch getMe().
 */
const CharacterSwitchDropdown = ({ className = '', onClose }: CharacterSwitchDropdownProps) => {
  const dispatch = useAppDispatch();
  const userId = useAppSelector((state) => state.user.id);
  const activeCharacterId = useAppSelector((state) => state.user.character?.id ?? null);

  const [characters, setCharacters] = useState<SwitchCharacterItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadCharacters = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetchUserCharacters(userId);
      setCharacters(response.data?.characters ?? []);
    } catch {
      setError('Не удалось загрузить персонажей');
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    loadCharacters();
  }, [loadCharacters]);

  // Close on Esc
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  const handleSwitch = async (characterId: number) => {
    if (!userId || switching !== null || characterId === activeCharacterId) return;

    setSwitching(characterId);
    try {
      const token = localStorage.getItem('accessToken');
      const response = await fetch(`${BASE_URL_DEFAULT}/users/${userId}/update_character`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ current_character: characterId }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail ?? 'Не удалось переключить персонажа');
      }

      await dispatch(getMe()).unwrap();
      toast.success('Персонаж переключён');
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Ошибка переключения персонажа';
      toast.error(message);
    } finally {
      setSwitching(null);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: -5 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -5 }}
      transition={{ duration: 0.15 }}
      className={`dropdown-menu z-50 overflow-hidden ${className}`}
    >
      <div className="px-4 py-2 border-b border-white/10">
        <span className="nav-link text-sm">Персонажи</span>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-6">
          <div className="w-6 h-6 border-2 border-white/20 border-t-white rounded-full animate-spin" />
        </div>
      )}

      {error && !loading && (
        <div className="px-4 py-4 text-center">
          <p className="text-site-red text-sm mb-2">{error}</p>
          <button
            onClick={loadCharacters}
            className="text-sm text-site-blue hover:text-gold-light transition-colors duration-200 ease-site"
          >
            Повторить
          </button>
        </div>
      )}

      {!loading && !error && characters.length === 0 && (
        <p className="px-4 py-4 text-white/50 text-sm text-center">
          У вас пока нет персонажей
        </p>
      )}

      {!loading && !error && characters.length > 0 && (
        <div className="max-h-[280px] overflow-y-auto gold-scrollbar">
          {characters.map((char) => {
            const isActive = char.id === activeCharacterId;
            const isSwitching = switching === char.id;
            return (
              <button
                key={char.id}
                onClick={() => handleSwitch(char.id)}
                disabled={isActive || switching !== null}
                className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors duration-200 ease-site ${
                  isActive
                    ? 'bg-gold/[0.08] cursor-default'
                    : 'hover:bg-white/[0.07] cursor-pointer'
                } ${isSwitching ? 'opacity-60' : ''} disabled:opacity-70`}
              >
                <div className="w-9 h-9 rounded-full overflow-hidden bg-white/10 flex items-center justify-center flex-shrink-0">
                  {char.avatar ? (
                    <img src={char.avatar} alt={char.name} className="w-full h-full object-cover" />
                  ) : (
                    <User size={18} className="text-white/40" />
                  )}
                </div>
                <div className="flex flex-col min-w-0 flex-1">
                  <span className={`text-sm font-medium truncate ${isActive ? 'gold-text' : 'text-white'}`}>
                    {char.name}
                  </span>
                  {char.level != null && (
                    <span className="text-white/40 text-xs">Уровень {char.level}</span>
                  )}
                </div>
                {isActive && (
                  <span className="text-gold text-xs flex-shrink-0">Активный</span>
                )}
                {isSwitching && (
                  <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin flex-shrink-0" />
                )}
              </button>
            );
          })}
        </div>
      )}

      <div className="border-t border-white/10">
        <Link to="/profile" className="dropdown-item" onClick={onClose}>
          Профиль персонажа
        </Link>
        <Link to="/selectCharacter" className="dropdown-item" onClick={onClose}>
          Управление персонажами
        </Link>
      </div>
    </motion.div>
  );
};

export default CharacterSwitchDropdown;
