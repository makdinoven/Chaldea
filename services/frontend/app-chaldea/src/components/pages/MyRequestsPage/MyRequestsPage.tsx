import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  fetchMyCharacterRequests,
  type MyCharacterRequest,
} from '../../../api/characterRequests';
import { fetchStartingPoints } from '../../../api/startingPoints';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { fetchRaces } from '../../../redux/slices/racesSlice';
import { fetchOriginsThunk, selectOrigins } from '../../../redux/slices/originsSlice';
import { selectCurrentGameYear, selectGameTimeError } from '../../../redux/slices/gameTimeSlice';
import { fetchGameTime } from '../../../redux/actions/gameTimeActions';
import CharacterPassport, {
  fromModerationRequest,
} from '../../CommonComponents/CharacterPassport';
import RequestEditor from './RequestEditor';

/**
 * FEAT-154 (task #20) — «Мои заявки» (rules 28-30).
 *
 * The player finally has somewhere to look after signing the contract: every
 * application they filed, its status, and — when the Coordinator refused — the
 * reason he wrote, verbatim.
 *
 * The list is COLLAPSED: one `variant="compact"` card per application, the
 * same card the characters grid uses (rule 26), opening the full passport in a
 * modal. A full sheet per row cost ~2000px each — seventeen applications made a
 * 34000px page on which the older ones were simply unreachable. Collapsed, the
 * page is a fixed grid and the reader chooses what to unfold.
 *
 * Compact, not a third view: the card already carries the portrait, the name,
 * the lineage and — the two things the player comes here for — the status badge
 * and (added for this page) a two-line preview of the Coordinator's reason.
 *
 * A modal rather than in-place expansion, because in-place expansion IS the
 * problem: an unfolded passport is taller than the viewport, so it would push
 * every following card off the screen and put the reader back to scrolling
 * thousands of pixels. The modal keeps the list stationary and reuses exactly
 * the overlay `CharactersListPage` opens the same passport in.
 *
 * The status badge and the rejection block are already part of the passport, so
 * this page adds only what the passport cannot know: what the player may *do*
 * with each application.
 *
 * ⚠️ Rule 30a — only a `rejected` application can be edited and resubmitted.
 * A pending or approved one shows no edit button at all; the backend would
 * answer 409, and offering the button would be a lie.
 *
 * The moderator's reason is player-visible free text written by another human:
 * it is rendered through `whitespace-pre-wrap` inside the passport and never
 * through `dangerouslySetInnerHTML` (R9).
 */

const STATUS_HINTS: Record<string, string> = {
  pending: 'Заявка у Координатора. Пока она рассматривается, изменить её нельзя.',
  approved: 'Заявка одобрена — персонаж внесён в реестр Цитадели.',
  rejected: 'Координатор вернул заявку. Исправьте указанное и отправьте её заново.',
};

/** Newest first: `created_at` when both rows have it, id otherwise. */
const byNewest = (a: MyCharacterRequest, b: MyCharacterRequest): number => {
  if (a.created_at && b.created_at) {
    const diff = new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    if (Number.isFinite(diff) && diff !== 0) return diff;
  }
  return b.id - a.id;
};

export default function MyRequestsPage() {
  const dispatch = useAppDispatch();

  const [requests, setRequests] = useState<MyCharacterRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  /** Which application is unfolded in the modal. `null` = the list only. */
  const [openId, setOpenId] = useState<number | null>(null);

  /** `start_location_id` → name, from the curated list (the row carries only the id). */
  const [locationNames, setLocationNames] = useState<Map<number, string>>(new Map());

  const origins = useAppSelector(selectOrigins);
  const races = useAppSelector((state) => state.races.races);
  const racesLoading = useAppSelector((state) => state.races.loading);
  const racesError = useAppSelector((state) => state.races.error);
  // ⚠️ The current in-game year is read at runtime and never hardcoded (§3.5).
  const currentGameYear = useAppSelector(selectCurrentGameYear);
  // Shown by the tenure field: a dead clock must not read as a slow one.
  const gameTimeError = useAppSelector(selectGameTimeError);
  const gameTimeLoaded = useAppSelector((state) => state.gameTime.computed !== null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchMyCharacterRequests();
      setRequests([...data].sort(byNewest));
    } catch (err) {
      // Never swallowed: the page shows it and offers a retry.
      const message =
        err instanceof Error && err.message
          ? err.message
          : 'Не удалось загрузить ваши заявки.';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Reference data — one request each, for the whole page.
  useEffect(() => {
    if (origins.length === 0) dispatch(fetchOriginsThunk());
    if (races.length === 0) dispatch(fetchRaces());
    if (!gameTimeLoaded) dispatch(fetchGameTime());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch]);

  useEffect(() => {
    fetchStartingPoints()
      .then((points) => setLocationNames(new Map(points.map((point) => [point.id, point.name]))))
      .catch((err: unknown) => {
        toast.error(
          err instanceof Error ? err.message : 'Не удалось загрузить стартовые точки.',
        );
      });
  }, []);

  useEffect(() => {
    if (racesError) toast.error(racesError);
  }, [racesError]);

  /** subrace id → `typical_origin_ids`, for the «редкий выбор» badge (rule 11). */
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

  /**
   * One adapter call site for both the collapsed card and the modal, so the two
   * can never drift apart — the modal must show the same application the card
   * summarises, only in full.
   */
  const toPassport = useCallback(
    (request: MyCharacterRequest) =>
      fromModerationRequest(request, {
        origins,
        typicalOriginIds: request.id_subrace
          ? typicalBySubrace.get(request.id_subrace) ?? null
          : null,
        startLocationName: request.start_location_id
          ? locationNames.get(request.start_location_id) ?? null
          : null,
      }),
    [origins, typicalBySubrace, locationNames],
  );

  const editing = useMemo(
    () => requests.find((request) => request.id === editingId) ?? null,
    [requests, editingId],
  );

  const opened = useMemo(
    () => requests.find((request) => request.id === openId) ?? null,
    [requests, openId],
  );

  // Escape closes the unfolded application — the modal is a reading view.
  useEffect(() => {
    if (!opened) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpenId(null);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [opened]);

  /**
   * Rule 30a — ONLY a rejected application may be reworked. Rendered on the
   * collapsed card (so the player can act without opening it) and again inside
   * the modal (where the reason he is acting on is being read).
   */
  const editButton = (request: MyCharacterRequest) =>
    request.status === 'rejected' ? (
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          setOpenId(null);
          setEditingId(request.id);
        }}
        className="font-lore rounded-card border border-ink/40 px-4 py-1.5 text-sm text-ink transition-colors duration-200 ease-site hover:bg-ink/10 sm:px-5 sm:py-2 sm:text-base"
      >
        Исправить и отправить заново
      </button>
    ) : null;

  const handleSaved = (updated: MyCharacterRequest) => {
    setRequests((prev) =>
      prev.map((request) => (request.id === updated.id ? updated : request)).sort(byNewest),
    );
    setEditingId(null);
    setOpenId(null);
  };

  const header = (
    <div className="relative mb-6 flex flex-col items-center gap-3 px-4 text-center">
      <h1 className="gold-text text-2xl font-bold uppercase sm:text-[32px]">Мои заявки</h1>
      <p className="text-white/70 max-w-[720px] text-sm">
        Здесь видно, что происходит с вашими заявками на персонажей: ждут ли они Координатора,
        одобрены или возвращены с замечаниями.
      </p>
    </div>
  );

  if (editing) {
    return (
      <div className="rounded-card bg-site-bg flex flex-col items-center py-[37px] pb-[70px]">
        {header}
        <RequestEditor
          request={editing}
          races={races}
          racesLoading={racesLoading}
          racesError={racesError}
          currentGameYear={currentGameYear}
          gameTimeError={gameTimeError}
          onCancel={() => setEditingId(null)}
          onSaved={handleSaved}
        />
      </div>
    );
  }

  return (
    <div className="rounded-card bg-site-bg flex flex-col items-center py-[37px] pb-[70px]">
      {header}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-white/30 border-t-white" />
        </div>
      ) : error ? (
        <div className="flex flex-col items-center gap-4 px-4 py-12">
          <p className="text-site-red text-center text-sm">{error}</p>
          <button type="button" className="btn-line w-auto px-5" onClick={() => void load()}>
            Попробовать снова
          </button>
        </div>
      ) : requests.length === 0 ? (
        <div className="flex flex-col items-center gap-4 px-4 py-12 text-center">
          <p className="text-white text-base sm:text-lg">
            Вы ещё не подавали заявок Координатору.
          </p>
          <p className="text-white/60 max-w-[520px] text-sm">
            Скитальцы принимают новичков постоянно — заполните анкету, и Координатор внесёт
            вас в реестр Цитадели.
          </p>
          <Link to="/createCharacter" className="btn-blue w-auto px-6">
            Создать персонажа
          </Link>
        </div>
      ) : (
        <div className="grid w-full max-w-container grid-cols-1 gap-4 px-2 sm:grid-cols-2 sm:px-4 lg:grid-cols-3">
          {requests.map((request) => (
            <CharacterPassport
              key={request.id}
              data={toPassport(request)}
              variant="compact"
              currentGameYear={currentGameYear}
              // The player's own request — the posting they chose stays visible.
              audience="self"
              onClick={() => setOpenId(request.id)}
              footer={
                <div className="mt-3 flex flex-col gap-2 border-t border-ink/15 pt-3">
                  <p className="lore-body text-ink-muted text-xs">
                    {STATUS_HINTS[request.status] ?? ''}
                  </p>
                  {editButton(request)}
                </div>
              }
            />
          ))}
        </div>
      )}

      {/*
        The unfolded application. Portalled to `document.body` on purpose, the
        same fix `CharactersListPage` and `AdminOrigins` carry: this page sits
        inside a transformed ancestor, which becomes the containing block for
        `position: fixed` children — `.modal-overlay`'s `inset: 0` would then
        resolve against the scrolling page instead of the viewport and the sheet
        would climb out of the top of the screen, under the site header.
      */}
      {opened &&
        createPortal(
          <div className="modal-overlay" onClick={() => setOpenId(null)}>
            {/*
              Two boxes, as on the characters grid: the outer one is the frame,
              so «Закрыть» stays pinned while the inner one scrolls the passport
              inside 90vh instead of growing off the display.
            */}
            <div
              className="relative mx-4 my-auto w-full max-w-4xl"
              onClick={(event) => event.stopPropagation()}
            >
              <button
                type="button"
                onClick={() => setOpenId(null)}
                aria-label="Закрыть"
                className="absolute right-3 top-3 z-10 text-ink/60 transition-colors hover:text-ink"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-6 w-6"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              <div className="gold-scrollbar max-h-[90vh] overflow-y-auto overflow-x-hidden rounded-card">
                <CharacterPassport
                  data={toPassport(opened)}
                  variant="full"
                  currentGameYear={currentGameYear}
                  audience="self"
                  footer={
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <p className="lore-body text-ink-muted text-sm">
                        {STATUS_HINTS[opened.status] ?? ''}
                      </p>
                      {editButton(opened)}
                    </div>
                  }
                />
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
