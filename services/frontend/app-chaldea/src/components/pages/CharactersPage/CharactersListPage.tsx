import { useEffect, useState, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../../api/api';
import { useAppSelector } from '../../../redux/store';

interface CharacterItem {
  id: number;
  name: string;
  avatar: string | null;
  level: number;
  class_name: string | null;
  race_name: string | null;
  subrace_name: string | null;
  sex: string | null;
  age: number | null;
  is_npc: boolean;
  user_id: number | null;
  username: string | null;
}

interface CharacterDetail extends CharacterItem {
  biography: string | null;
  personality: string | null;
  appearance: string | null;
  background: string | null;
}

const SEX_LABELS: Record<string, string> = {
  male: 'Мужской',
  female: 'Женский',
  genderless: 'Бесполый',
};

const CLASS_OPTIONS = [
  { value: 1, label: 'Воин' },
  { value: 2, label: 'Плут' },
  { value: 3, label: 'Маг' },
];

const CharactersListPage = () => {
  const navigate = useNavigate();
  const userId = useAppSelector((state) => state.user.id);
  const isAuthenticated = userId !== null;

  const [characters, setCharacters] = useState<CharacterItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [classFilter, setClassFilter] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;

  // Detail modal
  const [selectedChar, setSelectedChar] = useState<CharacterDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Claim functionality
  const [claimTarget, setClaimTarget] = useState<CharacterItem | null>(null);
  const [claimLoading, setClaimLoading] = useState(false);
  const [characterCount, setCharacterCount] = useState(0);
  const [characterLimit, setCharacterLimit] = useState(5);

  const fetchCharacters = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = { page, page_size: pageSize };
      if (search) params.q = search;
      if (classFilter) params.id_class = Number(classFilter);
      const res = await axios.get(`${BASE_URL}/characters/list`, { params });
      const data = res.data;
      setCharacters(data.items ?? []);
      setTotal(data.total ?? 0);
    } catch {
      toast.error('Не удалось загрузить список персонажей');
    } finally {
      setLoading(false);
    }
  }, [page, search, classFilter]);

  useEffect(() => {
    fetchCharacters();
  }, [fetchCharacters]);

  useEffect(() => {
    setPage(1);
  }, [search, classFilter]);

  // Fetch character count for limit check
  useEffect(() => {
    if (!isAuthenticated) return;
    const token = localStorage.getItem('accessToken');
    if (!token) return;
    axios
      .get(`${BASE_URL}/characters/my-character-count`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      .then((res) => {
        setCharacterCount(res.data.count ?? 0);
        setCharacterLimit(res.data.limit ?? 5);
      })
      .catch(() => {
        // silently fail — button will remain enabled by default
      });
  }, [isAuthenticated]);

  const handleClaimConfirm = async () => {
    if (!claimTarget) return;
    setClaimLoading(true);
    try {
      const token = localStorage.getItem('accessToken');
      await axios.post(
        `${BASE_URL}/characters/requests/claim`,
        { character_id: claimTarget.id },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success('Заявка успешно подана');
      setClaimTarget(null);
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      toast.error(error.response?.data?.detail || 'Ошибка при подаче заявки');
    } finally {
      setClaimLoading(false);
    }
  };

  const isAtCharacterLimit = characterCount >= characterLimit;

  const openDetail = async (charId: number) => {
    setDetailLoading(true);
    try {
      const params: Record<string, string | number> = { page: 1, page_size: 1 };
      // Fetch full data — the list already has it, find in current list or re-fetch
      const found = characters.find((c) => c.id === charId);
      if (found) {
        // Re-fetch single character for full biography/personality
        const res = await axios.get(`${BASE_URL}/characters/list`, {
          params: { q: found.name, page: 1, page_size: 1 },
        });
        const items = res.data.items ?? [];
        const full = items.find((c: CharacterDetail) => c.id === charId) ?? found;
        setSelectedChar(full as CharacterDetail);
      }
    } catch {
      toast.error('Не удалось загрузить анкету');
    } finally {
      setDetailLoading(false);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col gap-6"
    >
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/characters')}
            className="text-white/60 hover:text-white transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <h1 className="gold-text text-xl sm:text-2xl font-semibold uppercase tracking-wide">
            Все персонажи
          </h1>
          <span className="text-white/40 text-sm">({total})</span>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <input
          type="text"
          placeholder="Поиск по имени..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input-underline flex-1 !text-sm"
        />
        <select
          value={classFilter}
          onChange={(e) => setClassFilter(e.target.value)}
          className="input-underline !text-sm sm:w-40"
        >
          <option value="">Все классы</option>
          {CLASS_OPTIONS.map((c) => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </select>
      </div>

      {/* Character grid */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      ) : characters.length === 0 ? (
        <p className="text-white/50 text-sm text-center py-8">Персонажи не найдены</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 sm:gap-4">
          {characters.map((char) => (
            <button
              key={char.id}
              onClick={() => openDetail(char.id)}
              className="
                flex flex-col items-center gap-2 p-3 sm:p-4
                bg-black/40 rounded-card border border-white/10
                hover:bg-black/50 hover:border-gold/40
                transition-all duration-200 text-left
              "
            >
              <div className="gold-outline relative w-16 h-16 sm:w-20 sm:h-20 rounded-full overflow-hidden bg-black/40 shrink-0">
                {char.avatar ? (
                  <img src={char.avatar} alt={char.name} className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-white/20">
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                  </div>
                )}
              </div>
              <span className="text-white text-xs sm:text-sm font-medium text-center truncate w-full">
                {char.name}
              </span>
              <div className="flex items-center gap-1.5 flex-wrap justify-center">
                <span className="gold-text text-[10px] sm:text-xs font-medium">
                  LVL {char.level}
                </span>
                {char.class_name && (
                  <span className="text-white/40 text-[10px]">•</span>
                )}
                {char.class_name && (
                  <span className="text-white/50 text-[10px] sm:text-xs">
                    {char.class_name}
                  </span>
                )}
              </div>
              {char.race_name && (
                <span className="text-white/40 text-[10px] sm:text-xs">
                  {char.race_name}{char.subrace_name ? ` (${char.subrace_name})` : ''}
                </span>
              )}

              {/* Owner / claim section */}
              {!char.is_npc && (
                <div className="w-full mt-1 flex flex-col items-center gap-1">
                  {char.user_id && char.username ? (
                    <Link
                      to={`/user-profile/${char.user_id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="text-site-blue text-[10px] sm:text-xs hover:underline transition-colors truncate max-w-full"
                    >
                      {char.username}
                    </Link>
                  ) : (
                    <>
                      <span className="text-white/30 text-[10px] sm:text-xs italic">Свободен</span>
                      {isAuthenticated && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            if (!isAtCharacterLimit) {
                              setClaimTarget(char);
                            }
                          }}
                          disabled={isAtCharacterLimit}
                          title={isAtCharacterLimit ? 'Достигнут лимит персонажей' : undefined}
                          className={`
                            text-[9px] sm:text-[11px] px-2 py-0.5 rounded-card
                            transition-all duration-200
                            ${isAtCharacterLimit
                              ? 'text-white/30 border border-white/10 cursor-not-allowed'
                              : 'text-site-blue border border-site-blue/40 hover:bg-site-blue/10 hover:border-site-blue/60'
                            }
                          `}
                        >
                          Подать заявку
                        </button>
                      )}
                    </>
                  )}
                </div>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-4">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="btn-line !px-3 !py-1 !text-sm disabled:opacity-30"
          >
            ←
          </button>
          <span className="text-white/60 text-sm">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="btn-line !px-3 !py-1 !text-sm disabled:opacity-30"
          >
            →
          </button>
        </div>
      )}

      {/* Claim confirmation modal */}
      <AnimatePresence>
        {claimTarget && (
          <div className="modal-overlay" onClick={() => setClaimTarget(null)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick relative max-w-md w-full mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="gold-text text-lg sm:text-xl font-medium uppercase text-center mb-4">
                Подать заявку
              </h2>
              <p className="text-white text-sm sm:text-base text-center mb-6">
                Вы уверены, что хотите подать заявку на персонажа{' '}
                <span className="text-gold font-medium">{claimTarget.name}</span>?
              </p>
              <div className="flex gap-3 justify-center">
                <button
                  onClick={handleClaimConfirm}
                  disabled={claimLoading}
                  className="btn-blue !text-sm disabled:opacity-50"
                >
                  {claimLoading ? 'Отправка...' : 'Подтвердить'}
                </button>
                <button
                  onClick={() => setClaimTarget(null)}
                  disabled={claimLoading}
                  className="btn-line !text-sm"
                >
                  Отмена
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Character detail modal */}
      {selectedChar && (
        <div className="modal-overlay" onClick={() => setSelectedChar(null)}>
          <div
            className="modal-content gold-outline gold-outline-thick relative max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto gold-scrollbar"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setSelectedChar(null)}
              className="absolute top-4 right-4 text-white/50 hover:text-white transition-colors z-10"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            <div className="flex flex-col items-center gap-4">
              {/* Avatar */}
              <div className="gold-outline relative w-28 h-28 sm:w-36 sm:h-36 rounded-full overflow-hidden bg-black/40">
                {selectedChar.avatar ? (
                  <img src={selectedChar.avatar} alt={selectedChar.name} className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-white/20">
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-14 h-14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                  </div>
                )}
              </div>

              {/* Name */}
              <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase text-center">
                {selectedChar.name}
              </h2>

              {/* Info grid */}
              <div className="w-full grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div className="flex flex-col items-center gap-1 bg-white/5 rounded-card p-3">
                  <span className="text-white/50 text-xs uppercase">Уровень</span>
                  <span className="text-white text-sm font-medium">{selectedChar.level}</span>
                </div>
                {selectedChar.class_name && (
                  <div className="flex flex-col items-center gap-1 bg-white/5 rounded-card p-3">
                    <span className="text-white/50 text-xs uppercase">Класс</span>
                    <span className="text-white text-sm font-medium">{selectedChar.class_name}</span>
                  </div>
                )}
                {selectedChar.race_name && (
                  <div className="flex flex-col items-center gap-1 bg-white/5 rounded-card p-3">
                    <span className="text-white/50 text-xs uppercase">Раса</span>
                    <span className="text-white text-sm font-medium">{selectedChar.race_name}</span>
                  </div>
                )}
                {selectedChar.subrace_name && (
                  <div className="flex flex-col items-center gap-1 bg-white/5 rounded-card p-3">
                    <span className="text-white/50 text-xs uppercase">Подраса</span>
                    <span className="text-white text-sm font-medium">{selectedChar.subrace_name}</span>
                  </div>
                )}
                {selectedChar.sex && (
                  <div className="flex flex-col items-center gap-1 bg-white/5 rounded-card p-3">
                    <span className="text-white/50 text-xs uppercase">Пол</span>
                    <span className="text-white text-sm font-medium">{SEX_LABELS[selectedChar.sex] || selectedChar.sex}</span>
                  </div>
                )}
                {selectedChar.age != null && (
                  <div className="flex flex-col items-center gap-1 bg-white/5 rounded-card p-3">
                    <span className="text-white/50 text-xs uppercase">Возраст</span>
                    <span className="text-white text-sm font-medium">{selectedChar.age}</span>
                  </div>
                )}
              </div>

              {/* Sections */}
              {selectedChar.appearance && (
                <div className="w-full mt-2">
                  <h3 className="text-white/50 text-xs font-medium uppercase tracking-wide mb-2">Внешность</h3>
                  <p className="text-white/80 text-sm leading-relaxed whitespace-pre-wrap">{selectedChar.appearance}</p>
                </div>
              )}

              {selectedChar.biography && (
                <div className="w-full mt-2">
                  <h3 className="text-white/50 text-xs font-medium uppercase tracking-wide mb-2">Биография</h3>
                  <p className="text-white/80 text-sm leading-relaxed whitespace-pre-wrap">{selectedChar.biography}</p>
                </div>
              )}

              {selectedChar.personality && (
                <div className="w-full mt-2">
                  <h3 className="text-white/50 text-xs font-medium uppercase tracking-wide mb-2">Характер</h3>
                  <p className="text-white/80 text-sm leading-relaxed whitespace-pre-wrap">{selectedChar.personality}</p>
                </div>
              )}

              {selectedChar.background && (
                <div className="w-full mt-2">
                  <h3 className="text-white/50 text-xs font-medium uppercase tracking-wide mb-2">Предыстория</h3>
                  <p className="text-white/80 text-sm leading-relaxed whitespace-pre-wrap">{selectedChar.background}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default CharactersListPage;
