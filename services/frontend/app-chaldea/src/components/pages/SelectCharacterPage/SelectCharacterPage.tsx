import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { User, Plus } from 'react-feather';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { getMe } from '../../../redux/slices/userSlice';
import { BASE_URL_DEFAULT } from '../../../api/api';

const MAX_CHARACTERS = 5;

interface CharacterItem {
  id: number;
  name: string;
  avatar: string | null;
  level: number | null;
  id_race?: number | null;
  id_class?: number | null;
  race_name?: string | null;
  class_name?: string | null;
  subrace_name?: string | null;
}

const RACE_BORDER_COLORS: Record<number, string> = {
  1: 'ring-blue-400',
  2: 'ring-emerald-400',
  3: 'ring-red-500',
  4: 'ring-amber-400',
  5: 'ring-purple-400',
  6: 'ring-cyan-400',
  7: 'ring-orange-400',
  8: 'ring-pink-400',
  9: 'ring-indigo-400',
  10: 'ring-teal-400',
};

const getRingColor = (raceId: number | null | undefined): string => {
  if (raceId == null) return 'ring-white/30';
  return RACE_BORDER_COLORS[raceId] ?? 'ring-white/30';
};

const SelectCharacterPage = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const userId = useAppSelector((state) => state.user.id);
  const currentCharacter = useAppSelector((state) => state.user.character);

  const [characters, setCharacters] = useState<CharacterItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!userId) return;

    const fetchCharacters = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${BASE_URL_DEFAULT}/users/${userId}/characters`);
        if (!response.ok) {
          throw new Error('Не удалось загрузить персонажей');
        }
        const data = await response.json();
        setCharacters(data.characters ?? []);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Ошибка загрузки';
        setError(message);
        toast.error(message);
      } finally {
        setLoading(false);
      }
    };

    fetchCharacters();
  }, [userId]);

  const handleSwitch = async (characterId: number) => {
    if (!userId) return;
    if (switching) return;

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
      navigate('/profile');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Ошибка переключения';
      toast.error(message);
    } finally {
      setSwitching(null);
    }
  };

  if (!userId) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-white/50">Необходимо авторизоваться</p>
      </div>
    );
  }

  return (
    <div className="w-full max-w-[900px] mx-auto py-8 px-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold gold-text">Выбор персонажа</h1>
          <p className="text-white/50 text-sm mt-1">
            Персонажи: {characters.length}/{MAX_CHARACTERS}
          </p>
        </div>
        {characters.length < MAX_CHARACTERS && (
          <Link
            to="/createCharacter"
            className="btn-blue flex items-center gap-2 px-4 py-2 text-sm"
          >
            <Plus size={16} />
            Создать нового
          </Link>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-2 border-white/20 border-t-white rounded-full animate-spin" />
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <div className="gray-bg p-6 text-center">
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && characters.length === 0 && (
        <div className="gray-bg p-12 text-center">
          <User size={48} className="text-white/20 mx-auto mb-4" />
          <p className="text-white/50 mb-4">У вас пока нет персонажей</p>
          <Link to="/createCharacter" className="btn-blue px-6 py-2">
            Создать персонажа
          </Link>
        </div>
      )}

      {/* Character cards */}
      {!loading && !error && characters.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {characters.map((char) => {
            const isActive = currentCharacter?.id === char.id;
            const isSwitching = switching === char.id;
            const ringColor = getRingColor(char.id_race);

            return (
              <button
                key={char.id}
                onClick={() => !isActive && handleSwitch(char.id)}
                disabled={isActive || switching !== null}
                className={`
                  relative gray-bg p-5 rounded-card text-left transition-all duration-200
                  ${isActive
                    ? 'ring-2 ring-amber-400/80 cursor-default'
                    : 'hover:ring-1 hover:ring-white/20 cursor-pointer'
                  }
                  ${isSwitching ? 'opacity-60' : ''}
                  disabled:opacity-70
                `}
              >
                {/* Active badge */}
                {isActive && (
                  <div className="absolute top-3 right-3 px-2 py-0.5 rounded-full bg-amber-400/20 text-amber-400 text-xs font-medium">
                    Активный
                  </div>
                )}

                <div className="flex items-center gap-4">
                  {/* Avatar */}
                  <div
                    className={`
                      w-[72px] h-[72px] sm:w-[80px] sm:h-[80px]
                      rounded-full flex-shrink-0 overflow-hidden
                      bg-black/30 flex items-center justify-center
                      ring-2 ${ringColor}
                    `}
                  >
                    {char.avatar ? (
                      <img
                        src={char.avatar}
                        alt={char.name}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <User size={32} className="text-white/20" />
                    )}
                  </div>

                  {/* Info */}
                  <div className="flex flex-col gap-1 min-w-0">
                    <span className="text-white font-medium text-base truncate">
                      {char.name}
                    </span>
                    {char.race_name && (
                      <span className="text-white/50 text-sm truncate">
                        {char.race_name}
                        {char.subrace_name ? ` (${char.subrace_name})` : ''}
                      </span>
                    )}
                    {char.class_name && (
                      <span className="text-white/40 text-xs truncate">
                        {char.class_name}
                      </span>
                    )}
                    {char.level != null && (
                      <span className="text-white/30 text-xs">
                        Уровень {char.level}
                      </span>
                    )}
                  </div>
                </div>

                {/* Switching indicator */}
                {isSwitching && (
                  <div className="absolute inset-0 flex items-center justify-center rounded-card bg-black/40">
                    <div className="w-6 h-6 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default SelectCharacterPage;
