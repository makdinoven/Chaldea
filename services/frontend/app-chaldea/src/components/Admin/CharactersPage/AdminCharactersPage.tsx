import { useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchAdminCharacters,
  setSearch,
  setPage,
  setFilters,
  resetFilters,
  selectAdminCharacters,
  selectAdminCharactersTotal,
  selectAdminCharactersPage,
  selectAdminCharactersPageSize,
  selectAdminCharactersSearch,
  selectAdminCharactersFilters,
  selectAdminCharactersListLoading,
  selectAdminCharactersListError,
} from '../../../redux/slices/adminCharactersSlice';
import { CLASS_NAMES } from '../../ProfilePage/constants';
import {
  selectRaceNamesMap,
  fetchRaceNames,
} from '../../../redux/slices/profileSlice';

const DEBOUNCE_MS = 300;

const AdminCharactersPage = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();

  const characters = useAppSelector(selectAdminCharacters);
  const total = useAppSelector(selectAdminCharactersTotal);
  const page = useAppSelector(selectAdminCharactersPage);
  const pageSize = useAppSelector(selectAdminCharactersPageSize);
  const search = useAppSelector(selectAdminCharactersSearch);
  const filters = useAppSelector(selectAdminCharactersFilters);
  const loading = useAppSelector(selectAdminCharactersListLoading);
  const error = useAppSelector(selectAdminCharactersListError);
  const raceNamesMap = useAppSelector(selectRaceNamesMap);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isInitialMount = useRef(true);

  // Fetch race names if not loaded
  useEffect(() => {
    if (Object.keys(raceNamesMap).length === 0) {
      dispatch(fetchRaceNames());
    }
  }, [dispatch, raceNamesMap]);

  // Fetch characters on mount and when page/filters change (not search — that's debounced)
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      dispatch(fetchAdminCharacters());
      return;
    }
    dispatch(fetchAdminCharacters());
  }, [dispatch, page, filters]);

  // Show error via toast when listError changes
  useEffect(() => {
    if (error) {
      toast.error(error);
    }
  }, [error]);

  // Debounced search handler
  const handleSearchChange = useCallback(
    (value: string) => {
      dispatch(setSearch(value));
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        dispatch(fetchAdminCharacters());
      }, DEBOUNCE_MS);
    },
    [dispatch],
  );

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const totalPages = Math.ceil(total / pageSize);

  const handleRowClick = (id: number) => {
    navigate(`/admin/characters/${id}`);
  };

  const raceOptions = Object.entries(raceNamesMap).map(([id, name]) => ({
    value: Number(id),
    label: name,
  }));

  const classOptions = Object.entries(CLASS_NAMES).map(([id, name]) => ({
    value: Number(id),
    label: name,
  }));

  // Build page number buttons
  const pageNumbers: number[] = [];
  const maxVisiblePages = 7;
  if (totalPages <= maxVisiblePages) {
    for (let i = 1; i <= totalPages; i++) pageNumbers.push(i);
  } else {
    pageNumbers.push(1);
    let start = Math.max(2, page - 2);
    let end = Math.min(totalPages - 1, page + 2);
    if (page <= 3) end = Math.min(5, totalPages - 1);
    if (page >= totalPages - 2) start = Math.max(totalPages - 4, 2);
    if (start > 2) pageNumbers.push(-1); // ellipsis marker
    for (let i = start; i <= end; i++) pageNumbers.push(i);
    if (end < totalPages - 1) pageNumbers.push(-2); // ellipsis marker
    pageNumbers.push(totalPages);
  }

  return (
    <div className="w-full max-w-[1240px] mx-auto">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em] mb-8">
        Персонажи
      </h1>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
      >
        {/* Search */}
        <div className="mb-6">
          <input
            type="text"
            className="input-underline w-full max-w-[400px]"
            placeholder="Поиск по имени персонажа..."
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
          />
        </div>

        {/* Filters row */}
        <div className="flex flex-wrap items-end gap-4 mb-6">
          {/* Race filter */}
          <div className="flex flex-col gap-1">
            <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Раса</span>
            <select
              className="input-underline text-sm min-w-[140px]"
              value={filters.raceId ?? ''}
              onChange={(e) =>
                dispatch(setFilters({ raceId: e.target.value ? Number(e.target.value) : null }))
              }
            >
              <option value="">Все</option>
              {raceOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Class filter */}
          <div className="flex flex-col gap-1">
            <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Класс</span>
            <select
              className="input-underline text-sm min-w-[140px]"
              value={filters.classId ?? ''}
              onChange={(e) =>
                dispatch(setFilters({ classId: e.target.value ? Number(e.target.value) : null }))
              }
            >
              <option value="">Все</option>
              {classOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Level min */}
          <div className="flex flex-col gap-1">
            <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Ур. от</span>
            <input
              type="number"
              className="input-underline text-sm w-[80px]"
              placeholder="—"
              min={1}
              value={filters.levelMin ?? ''}
              onChange={(e) =>
                dispatch(setFilters({ levelMin: e.target.value ? Number(e.target.value) : null }))
              }
            />
          </div>

          {/* Level max */}
          <div className="flex flex-col gap-1">
            <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Ур. до</span>
            <input
              type="number"
              className="input-underline text-sm w-[80px]"
              placeholder="—"
              min={1}
              value={filters.levelMax ?? ''}
              onChange={(e) =>
                dispatch(setFilters({ levelMax: e.target.value ? Number(e.target.value) : null }))
              }
            />
          </div>

          {/* Reset button */}
          <button
            className="btn-line text-sm"
            onClick={() => dispatch(resetFilters())}
          >
            Сбросить
          </button>
        </div>

        {/* Table */}
        <div className="gray-bg p-4 overflow-x-hidden">
          {loading ? (
            <div className="flex justify-center items-center py-12">
              <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            </div>
          ) : characters.length === 0 ? (
            <p className="text-white/50 text-center py-8">Персонажи не найдены</p>
          ) : (
            <motion.table
              className="w-full text-left"
              initial="hidden"
              animate="visible"
              variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.03 } } }}
            >
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-white/60 text-xs uppercase tracking-[0.06em] font-medium py-3 px-2">
                    ID
                  </th>
                  <th className="text-white/60 text-xs uppercase tracking-[0.06em] font-medium py-3 px-2">
                    Имя
                  </th>
                  <th className="text-white/60 text-xs uppercase tracking-[0.06em] font-medium py-3 px-2">
                    Уровень
                  </th>
                  <th className="text-white/60 text-xs uppercase tracking-[0.06em] font-medium py-3 px-2">
                    Раса
                  </th>
                  <th className="text-white/60 text-xs uppercase tracking-[0.06em] font-medium py-3 px-2">
                    Класс
                  </th>
                  <th className="text-white/60 text-xs uppercase tracking-[0.06em] font-medium py-3 px-2">
                    Владелец
                  </th>
                  <th className="text-white/60 text-xs uppercase tracking-[0.06em] font-medium py-3 px-2">
                    Баланс
                  </th>
                </tr>
              </thead>
              <tbody>
                {characters.map((char) => (
                  <motion.tr
                    key={char.id}
                    variants={{
                      hidden: { opacity: 0, y: 5 },
                      visible: { opacity: 1, y: 0 },
                    }}
                    onClick={() => handleRowClick(char.id)}
                    className="border-b border-white/5 cursor-pointer hover:bg-white/[0.07] transition-colors duration-200"
                  >
                    <td className="text-white/70 text-sm py-3 px-2">{char.id}</td>
                    <td className="text-white text-sm py-3 px-2 font-medium">{char.name}</td>
                    <td className="text-white text-sm py-3 px-2">{char.level}</td>
                    <td className="text-white/80 text-sm py-3 px-2">
                      {raceNamesMap[char.id_race] ?? `#${char.id_race}`}
                    </td>
                    <td className="text-white/80 text-sm py-3 px-2">
                      {CLASS_NAMES[char.id_class] ?? `#${char.id_class}`}
                    </td>
                    <td className="text-white/70 text-sm py-3 px-2">
                      {char.user_id ?? '—'}
                    </td>
                    <td className="text-gold text-sm py-3 px-2">{char.currency_balance}</td>
                  </motion.tr>
                ))}
              </tbody>
            </motion.table>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex justify-center items-center gap-2 mt-6">
            <button
              className="text-white/60 text-sm px-3 py-1 hover:text-site-blue transition-colors duration-200 disabled:opacity-30 disabled:cursor-not-allowed"
              disabled={page <= 1}
              onClick={() => dispatch(setPage(page - 1))}
            >
              &laquo;
            </button>

            {pageNumbers.map((p, i) =>
              p < 0 ? (
                <span key={`ellipsis-${i}`} className="text-white/40 text-sm px-1">
                  ...
                </span>
              ) : (
                <button
                  key={p}
                  onClick={() => dispatch(setPage(p))}
                  className={`text-sm px-3 py-1 rounded-[8px] transition-colors duration-200 ${
                    p === page
                      ? 'bg-white/10 text-white font-medium'
                      : 'text-white/60 hover:text-site-blue'
                  }`}
                >
                  {p}
                </button>
              ),
            )}

            <button
              className="text-white/60 text-sm px-3 py-1 hover:text-site-blue transition-colors duration-200 disabled:opacity-30 disabled:cursor-not-allowed"
              disabled={page >= totalPages}
              onClick={() => dispatch(setPage(page + 1))}
            >
              &raquo;
            </button>

            <span className="text-white/40 text-xs ml-4">
              Всего: {total}
            </span>
          </div>
        )}
      </motion.div>
    </div>
  );
};

export default AdminCharactersPage;
