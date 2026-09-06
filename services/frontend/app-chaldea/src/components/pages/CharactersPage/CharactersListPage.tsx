import { useEffect, useState, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../../api/api';
import { apiErrorMessage } from '../../../api/errors';
import { fetchItemsBulk, fetchSkillsBulk } from '../../../api/bulk';
import type { ItemBulk, SkillBulk } from '../../../api/bulk';
import {
  fetchCharacterPublic,
  fetchCharactersList,
} from '../../../api/charactersPublic';
import type { CharacterListItem, CharacterPublic } from '../../../api/charactersPublic';
import {
  NO_CHARACTER_LIMIT,
  fetchMyCharacterCount,
  isCharacterLimitReached,
} from '../../../api/characterRequests';
import type { MyCharacterCount } from '../../../api/characterRequests';
import { fetchOrigins } from '../../../api/origins';
import type { OriginCountry } from '../../../api/origins';
import { fetchGameTime } from '../../../redux/actions/gameTimeActions';
import { selectCurrentGameYear } from '../../../redux/slices/gameTimeSlice';
import { fetchRaces } from '../../../redux/slices/racesSlice';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import CharacterPassport, {
  fromCharacterListItem,
  fromCharacterPublic,
} from '../../CommonComponents/CharacterPassport';

/**
 * FEAT-154 (task #22) — the public character list.
 *
 * The grid renders the COMPACT passport, the detail modal the FULL one
 * (rule 26). The reference data every card needs — the origin registry and the
 * subraces' typical origins — is loaded ONCE per page, so the grid costs zero
 * requests per card. The old `page_size: 1` refetch-by-name hack is replaced by
 * `GET /characters/{id}/public`, which is also the only source of the frozen
 * `granted_kit` snapshot (rule 12d).
 */

const CLASS_OPTIONS = [
  { value: 1, label: 'Воин' },
  { value: 2, label: 'Плут' },
  { value: 3, label: 'Маг' },
];

interface CharacterDetail {
  character: CharacterPublic;
  items: ItemBulk[];
  skills: SkillBulk[];
}

const CharactersListPage = () => {
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const userId = useAppSelector((state) => state.user.id);
  const isAuthenticated = userId !== null;

  const races = useAppSelector((state) => state.races.races);
  const racesError = useAppSelector((state) => state.races.error);
  const currentGameYear = useAppSelector(selectCurrentGameYear);
  const gameTimeLoaded = useAppSelector((state) => state.gameTime.computed !== null);

  const [characters, setCharacters] = useState<CharacterListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [classFilter, setClassFilter] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;

  // Origin registry — one request for the whole page (rule 26).
  const [origins, setOrigins] = useState<OriginCountry[]>([]);

  // Detail modal
  const [detail, setDetail] = useState<CharacterDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Claim functionality
  const [claimTarget, setClaimTarget] = useState<CharacterListItem | null>(null);
  const [claimLoading, setClaimLoading] = useState(false);
  // `limit: null` — no cap is configured; claiming stays open (see
  // `isCharacterLimitReached`).
  const [characterCount, setCharacterCount] =
    useState<MyCharacterCount>(NO_CHARACTER_LIMIT);

  const fetchCharacters = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const data = await fetchCharactersList({
        page,
        page_size: pageSize,
        ...(search ? { q: search } : {}),
        ...(classFilter ? { id_class: Number(classFilter) } : {}),
      });
      setCharacters(data.items ?? []);
      setTotal(data.total ?? 0);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Не удалось загрузить список персонажей';
      setListError(message);
      toast.error(message);
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

  useEffect(() => {
    fetchOrigins()
      .then(setOrigins)
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Не удалось загрузить происхождения.');
      });
  }, []);

  // Typical origins live on the subrace — one cached request, not one per card.
  useEffect(() => {
    if (races.length === 0) dispatch(fetchRaces());
  }, [dispatch, races.length]);

  useEffect(() => {
    if (racesError) toast.error(racesError);
  }, [racesError]);

  /** subrace id → `typical_origin_ids` (rule 11 — the «редкий выбор» badge). */
  const typicalBySubrace = useMemo(() => {
    const map = new Map<number, number[]>();
    races.forEach((race) => {
      race.subraces?.forEach((subrace) => {
        if (subrace.typical_origin_ids?.length) {
          map.set(subrace.id_subrace, subrace.typical_origin_ids);
        }
      });
    });
    return map;
  }, [races]);

  // Fetch character count for limit check
  useEffect(() => {
    if (!isAuthenticated) return;
    let cancelled = false;
    fetchMyCharacterCount()
      .then((info) => {
        if (!cancelled) setCharacterCount(info);
      })
      .catch((err) => {
        toast.error(
          err instanceof Error ? err.message : 'Не удалось проверить лимит персонажей.'
        );
      });
    return () => {
      cancelled = true;
    };
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
      toast.error(apiErrorMessage(err, 'Ошибка при подаче заявки'));
    } finally {
      setClaimLoading(false);
    }
  };

  const isAtCharacterLimit = isCharacterLimitReached(characterCount);

  const openDetail = async (charId: number) => {
    setDetailLoading(true);
    // The in-game year is only needed by the full passport («в строю N лет»).
    if (!gameTimeLoaded) dispatch(fetchGameTime());
    try {
      const character = await fetchCharacterPublic(charId);
      let items: ItemBulk[] = [];
      let skills: SkillBulk[] = [];
      const kit = character.granted_kit;
      if (kit) {
        // The kit is stored id-only (D19) — names and icons are resolved live.
        // A bulk failure must not hide the passport, so it is reported and the
        // kit degrades to «Предмет #id».
        try {
          [items, skills] = await Promise.all([
            fetchItemsBulk((kit.items ?? []).map((line) => line.item_id)),
            fetchSkillsBulk((kit.skills ?? []).map((line) => line.skill_id)),
          ]);
        } catch (err) {
          toast.error(
            err instanceof Error ? err.message : 'Не удалось загрузить стартовый набор.'
          );
        }
      }
      setDetail({ character, items, skills });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Не удалось загрузить анкету');
    } finally {
      setDetailLoading(false);
    }
  };

  const detailPassport = useMemo(() => {
    if (!detail) return null;
    return fromCharacterPublic(detail.character, {
      origins,
      typicalOriginIds: detail.character.id_subrace
        ? typicalBySubrace.get(detail.character.id_subrace) ?? null
        : null,
      // `null` when character-attributes-service was unreachable (N31) — the
      // passport then just omits the stat block.
      stats: detail.character.stats,
      items: detail.items,
      skills: detail.skills,
    });
  }, [detail, origins, typicalBySubrace]);

  const totalPages = Math.ceil(total / pageSize);

  /** Owner link / claim button — rendered inside the compact passport card. */
  const cardFooter = (char: CharacterListItem) => {
    if (char.is_npc) return null;
    return (
      <div className="mt-1 flex w-full flex-col items-center gap-1 border-t border-ink/15 pt-2">
        {char.user_id && char.username ? (
          <Link
            to={`/user-profile/${char.user_id}`}
            onClick={(e) => e.stopPropagation()}
            className="max-w-full truncate text-xs text-ink-muted underline decoration-ink/40 underline-offset-2 hover:decoration-ink"
          >
            {char.username}
          </Link>
        ) : (
          <>
            <span className="text-xs italic text-ink-muted">Свободен</span>
            {isAuthenticated && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  if (!isAtCharacterLimit) setClaimTarget(char);
                }}
                disabled={isAtCharacterLimit}
                title={
                  isAtCharacterLimit
                    ? `Достигнут лимит персонажей (${characterCount.limit})`
                    : undefined
                }
                className={`
                  font-lore rounded-card border px-3 py-1 text-xs
                  transition-colors duration-200 ease-site
                  ${
                    isAtCharacterLimit
                      ? 'cursor-not-allowed border-ink/20 text-ink-muted/60'
                      : 'border-ink/40 text-ink hover:bg-ink/10'
                  }
                `}
              >
                Подать заявку
              </button>
            )}
          </>
        )}
      </div>
    );
  };

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

      {/* Character grid — compact passports (rule 26) */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      ) : listError ? (
        <div className="flex flex-col items-center gap-3 py-8">
          <p className="text-site-red text-sm text-center">{listError}</p>
          <button onClick={fetchCharacters} className="btn-line !text-sm">
            Повторить
          </button>
        </div>
      ) : characters.length === 0 ? (
        <p className="text-white/50 text-sm text-center py-8">Персонажи не найдены</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 sm:gap-4">
          {characters.map((char) => (
            <CharacterPassport
              key={char.id}
              variant="compact"
              onClick={() => openDetail(char.id)}
              currentGameYear={currentGameYear}
              data={fromCharacterListItem(char, {
                origins,
                typicalOriginIds: char.id_subrace
                  ? typicalBySubrace.get(char.id_subrace) ?? null
                  : null,
              })}
              footer={cardFooter(char)}
            />
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

      {/*
        Every overlay on this page is portalled to `document.body`, following
        `ItemDetailModal` / `ConfirmationModal`. It is not cosmetic: this page's
        root is a `motion.div` that animates `y`, and a transformed ancestor
        becomes the containing block for `position: fixed` descendants — so
        `.modal-overlay`'s `inset: 0` would resolve against the whole scrolling
        page instead of the viewport. That is what let the passport modal grow
        past the top of the screen and hide under the site header.
      */}
      {createPortal(
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
        </AnimatePresence>,
        document.body,
      )}

      {/* Loading indicator while the full passport is fetched */}
      {detailLoading &&
        createPortal(
          <div className="modal-overlay">
            <div className="w-10 h-10 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
          </div>,
          document.body,
        )}

      {/* Character detail modal — the FULL passport */}
      {detail &&
        detailPassport &&
        createPortal(
          <div className="modal-overlay" onClick={() => setDetail(null)}>
            {/*
              Two boxes on purpose. The outer one is the modal frame: it never
              scrolls, so «Закрыть» stays pinned to its corner no matter how far
              down the chronicle the reader is. The inner one is the viewport
              cap — the passport is now tall enough (identity band + ledger +
              full-width chronicle) to outgrow any screen, so it scrolls
              INSIDE 90vh instead of growing off the top of the display. The
              overlay centres it, which leaves ~5vh of clearance top and bottom
              and puts the identity band on screen the moment it opens.
            */}
            <div
              className="relative mx-4 my-auto w-full max-w-4xl"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={() => setDetail(null)}
                aria-label="Закрыть"
                className="absolute right-3 top-3 z-10 text-ink/60 hover:text-ink transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              <div className="max-h-[90vh] overflow-y-auto overflow-x-hidden gold-scrollbar rounded-card">
                <CharacterPassport
                  data={detailPassport}
                  variant="full"
                  currentGameYear={currentGameYear}
                />
              </div>
            </div>
          </div>,
          document.body,
        )}
    </motion.div>
  );
};

export default CharactersListPage;
