import { useEffect, useState, useCallback, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import axios from 'axios';
import { BASE_URL } from '../../../api/api';
import { useBodyBackground } from '../../../hooks/useBodyBackground';
import { useAppSelector, useAppDispatch } from '../../../redux/store';
import { setCharacterLocation, getMe } from '../../../redux/slices/userSlice';
import { isStaff } from '../../../utils/permissions';
import { LocationData } from './types';
import LocationHeader from './LocationHeader';
import PlayersSection from './PlayersSection';
import PostCard from './PostCard';
import PostCreateForm from './PostCreateForm';
import NeighborsSection from './NeighborsSection';
import LootSection from './LootSection';
import PendingInvitationsPanel from './PendingInvitationsPanel';
import PendingPartyInvitesPanel from './PendingPartyInvitesPanel';
import LocationMobs from '../../LocationMobs';
import BattlesSection from './BattlesSection';
import useBattleLock from '../../../hooks/useBattleLock';
import BattleLockBanner from '../../CommonComponents/BattleLockBanner';
import DungeonEntrance from '../../DungeonPage/DungeonEntrance';
import useGatheringLock from '../../../hooks/useGatheringLock';
import GatheringLockBanner from '../../CommonComponents/GatheringLockBanner';
import GatheringSection from './GatheringSection/GatheringSection';

const LocationPage = () => {
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const { locationId } = useParams<{ locationId: string }>();
  const [location, setLocation] = useState<LocationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [quickMoving, setQuickMoving] = useState(false);
  const [showPostForm, setShowPostForm] = useState(false);

  const character = useAppSelector((state) => state.user.character);
  const userId = useAppSelector((state) => state.user.id);
  const userRole = useAppSelector((state) => state.user.role);
  const userIsStaff = isStaff(userRole);
  const { inBattle } = useBattleLock(character?.id);
  const { isGathering } = useGatheringLock(character?.id);
  // Combined "the character cannot take voluntary actions" flag — used to
  // gate the post form, quick-move button and neighbor links so that
  // gathering players can't bypass the lock by pressing UI shortcuts.
  const actionsLocked = inBattle || isGathering;

  // --- Travel cooldown timer ---
  const [cooldownRemaining, setCooldownRemaining] = useState<number>(0);

  // Sync from server value (getMe response)
  useEffect(() => {
    const cooldownUntil = character?.travel_cooldown_until;
    if (!cooldownUntil) return;
    const diff = new Date(cooldownUntil).getTime() - Date.now();
    const remaining = Math.max(0, Math.ceil(diff / 1000));
    if (remaining > 0) {
      setCooldownRemaining(remaining);
    }
  }, [character?.travel_cooldown_until]);

  // Tick down every second when cooldown is active
  useEffect(() => {
    if (cooldownRemaining <= 0) return;
    const interval = setInterval(() => {
      setCooldownRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [cooldownRemaining > 0]); // eslint-disable-line react-hooks/exhaustive-deps

  const isTravelOnCooldown = cooldownRemaining > 0;
  const cooldownMinutes = Math.floor(cooldownRemaining / 60);
  const cooldownSeconds = cooldownRemaining % 60;

  useBodyBackground(location?.image_url);

  const fetchLocationData = useCallback(async () => {
    if (!locationId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get<LocationData>(
        `${BASE_URL}/locations/${locationId}/client/details`
      );
      setLocation(res.data);
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.status === 404
          ? 'Локация не найдена'
          : 'Не удалось загрузить данные локации';
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [locationId]);

  useEffect(() => {
    fetchLocationData();
  }, [fetchLocationData]);

  // --- Favorite handler (optimistic) ---

  const handleToggleFavorite = useCallback(async () => {
    if (!locationId) return;

    const wasFavorited = location?.is_favorited ?? false;

    // Optimistic update
    setLocation((prev) => {
      if (!prev) return prev;
      return { ...prev, is_favorited: !wasFavorited };
    });

    try {
      if (wasFavorited) {
        await axios.delete(`${BASE_URL}/locations/${locationId}/favorite`);
      } else {
        await axios.post(`${BASE_URL}/locations/${locationId}/favorite`);
      }
    } catch {
      // Revert on error
      setLocation((prev) => {
        if (!prev) return prev;
        return { ...prev, is_favorited: wasFavorited };
      });
      toast.error('Не удалось обновить избранное');
    }
  }, [locationId, location?.is_favorited]);

  // --- Like handlers (optimistic) ---

  const handleLike = useCallback(
    async (postId: number) => {
      if (!character?.id) return;

      // Optimistic update
      setLocation((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          posts: prev.posts.map((p) =>
            p.post_id === postId
              ? {
                  ...p,
                  likes_count: p.likes_count + 1,
                  liked_by: [...p.liked_by, character.id],
                }
              : p
          ),
        };
      });

      try {
        await axios.post(`${BASE_URL}/locations/posts/${postId}/like`, {
          character_id: character.id,
        });
      } catch {
        // Revert on error
        setLocation((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            posts: prev.posts.map((p) =>
              p.post_id === postId
                ? {
                    ...p,
                    likes_count: Math.max(0, p.likes_count - 1),
                    liked_by: p.liked_by.filter((id) => id !== character.id),
                  }
                : p
            ),
          };
        });
        toast.error('Не удалось поставить лайк');
      }
    },
    [character?.id]
  );

  const handleUnlike = useCallback(
    async (postId: number) => {
      if (!character?.id) return;

      // Optimistic update
      setLocation((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          posts: prev.posts.map((p) =>
            p.post_id === postId
              ? {
                  ...p,
                  likes_count: Math.max(0, p.likes_count - 1),
                  liked_by: p.liked_by.filter((id) => id !== character.id),
                }
              : p
          ),
        };
      });

      try {
        await axios.delete(
          `${BASE_URL}/locations/posts/${postId}/like?character_id=${character.id}`
        );
      } catch {
        // Revert on error
        setLocation((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            posts: prev.posts.map((p) =>
              p.post_id === postId
                ? {
                    ...p,
                    likes_count: p.likes_count + 1,
                    liked_by: [...p.liked_by, character.id],
                  }
                : p
            ),
          };
        });
        toast.error('Не удалось убрать лайк');
      }
    },
    [character?.id]
  );

  // --- Tag player handler ---

  const handleTagPlayer = useCallback(
    async (targetUserId: number) => {
      if (!character?.id || !locationId) return;

      try {
        await axios.post(`${BASE_URL}/locations/${locationId}/tag-player`, {
          target_user_id: targetUserId,
          sender_character_id: character.id,
        });
        toast.success('Уведомление отправлено');
      } catch (err) {
        const message =
          axios.isAxiosError(err) && err.response?.data?.detail
            ? err.response.data.detail
            : 'Не удалось отправить уведомление';
        toast.error(message);
      }
    },
    [character?.id, locationId]
  );

  // --- Report handler ---

  const handleReport = useCallback(
    async (postId: number, reason: string) => {
      try {
        await axios.post(`${BASE_URL}/locations/posts/${postId}/report`, { reason });
        toast.success('Жалоба отправлена');
      } catch (err) {
        if (axios.isAxiosError(err) && err.response?.status === 409) {
          toast.error('Вы уже отправляли жалобу на этот пост');
        } else {
          toast.error('Не удалось отправить жалобу');
        }
        throw err;
      }
    },
    []
  );

  // --- Request deletion handler ---

  const handleRequestDeletion = useCallback(
    async (postId: number, reason: string) => {
      try {
        await axios.post(`${BASE_URL}/locations/posts/${postId}/request-deletion`, { reason });
        toast.success('Запрос на удаление отправлен');
      } catch (err) {
        const message =
          axios.isAxiosError(err) && err.response?.data?.detail
            ? err.response.data.detail
            : 'Не удалось отправить запрос на удаление';
        toast.error(message);
        throw err;
      }
    },
    []
  );

  // --- Post submit ---

  const handleSubmitPost = useCallback(
    async (content: string) => {
      try {
        await axios.post(`${BASE_URL}/locations/${locationId}/move_and_post`, {
          character_id: character?.id,
          location_id: locationId,
          content,
        });
        // If character moved to this location, update Redux state + refresh cooldown
        if (character?.current_location?.id !== Number(locationId) && location) {
          dispatch(setCharacterLocation({ id: location.id, name: location.name }));
          // Set cooldown immediately so timer appears without waiting for getMe()
          if (neighborEntry?.energy_cost) {
            setCooldownRemaining(neighborEntry.energy_cost * 60);
          }
          dispatch(getMe());
        }
        toast.success('Пост отправлен');
        await fetchLocationData();
      } catch (err) {
        const message =
          axios.isAxiosError(err) && err.response?.data?.detail
            ? err.response.data.detail
            : 'Не удалось отправить пост';
        toast.error(message);
      }
    },
    [locationId, character?.id, character?.current_location?.id, location, dispatch, fetchLocationData]
  );

  // --- NPC post submit (admin only) ---

  const handleSubmitNpcPost = useCallback(
    async (npcId: number, content: string) => {
      if (!locationId) return;
      try {
        await axios.post(`${BASE_URL}/locations/posts/as-npc`, {
          npc_id: npcId,
          location_id: Number(locationId),
          content,
        });
        toast.success('Пост от НПС отправлен');
        await fetchLocationData();
      } catch (err) {
        const message =
          axios.isAxiosError(err) && err.response?.data?.detail
            ? err.response.data.detail
            : 'Не удалось отправить пост от НПС';
        toast.error(message);
      }
    },
    [locationId, fetchLocationData]
  );

  // --- Loot pickup ---

  const handlePickupLoot = useCallback(
    async (lootId: number) => {
      if (!character?.id || !locationId) return;
      try {
        await axios.post(
          `${BASE_URL}/locations/${locationId}/loot/${lootId}/pickup`,
          { character_id: character.id }
        );
        toast.success('Предмет подобран');
        await fetchLocationData();
      } catch (err) {
        const message =
          axios.isAxiosError(err) && err.response?.data?.detail
            ? err.response.data.detail
            : 'Не удалось подобрать предмет';
        toast.error(message);
      }
    },
    [character?.id, locationId, fetchLocationData]
  );

  // Reset post form choice when character arrives at location
  useEffect(() => {
    setShowPostForm(false);
  }, [character?.current_location?.id]);

  // --- Quick move ---

  const handleQuickMove = useCallback(async () => {
    if (!character?.id || !location) return;
    const cost = neighborEntry?.energy_cost ? neighborEntry.energy_cost * 2 : 0;
    if (!window.confirm(`Быстрое перемещение в "${location.name}" стоит ${cost} выносливости. Продолжить?`)) return;
    setQuickMoving(true);
    try {
      await axios.post(`${BASE_URL}/locations/${location.id}/quick_move`, {
        character_id: character.id,
      });
      dispatch(setCharacterLocation({ id: location.id, name: location.name }));
      // Set cooldown immediately so timer appears without waiting for getMe()
      if (neighborEntry?.energy_cost) {
        setCooldownRemaining(neighborEntry.energy_cost * 60);
      }
      dispatch(getMe());
      toast.success(`Вы переместились в ${location.name}`);
      await fetchLocationData();
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось выполнить быстрое перемещение';
      toast.error(message);
    } finally {
      setQuickMoving(false);
    }
  }, [character?.id, location, dispatch, fetchLocationData]);

  const isCharacterHere = character?.current_location?.id === location?.id;

  // Neighbor links are bidirectional with the same energy_cost.
  // If the character's current location appears in this location's neighbor list,
  // then this location is reachable from the character's current location.
  const neighborEntry = useMemo(() => {
    if (!character?.current_location?.id || isCharacterHere || !location) return null;
    return location.neighbors.find((n) => n.id === character.current_location!.id) ?? null;
  }, [character?.current_location?.id, isCharacterHere, location]);

  const isNeighborLocation = neighborEntry !== null;

  // --- Loading state ---
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-10 h-10 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

  // --- Error state ---
  if (error || !location) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <p className="text-white/60 text-lg">{error || 'Локация не найдена'}</p>
        <button
          onClick={() => navigate(-1)}
          className="btn-blue text-sm px-6 py-2"
        >
          Назад
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 sm:gap-6 pb-10">
      {/* Header block */}
      <div className="bg-black/60 rounded-card p-4 sm:p-6 backdrop-blur-sm flex flex-col gap-4">
        {/* Back button */}
        <button
          onClick={() => navigate(-1)}
          className="self-start flex items-center gap-2 text-white/60 hover:text-white transition-colors text-sm"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          Назад
        </button>

        {/* Battle lock banner */}
        {inBattle && (
          <BattleLockBanner message="Вы в бою! Завершите бой, чтобы продолжить." />
        )}

        {/* Gathering lock banner — shown while a resource-gathering session
            is active. Mirrors BattleLockBanner placement so the player
            always sees what is blocking actions on this page. */}
        {character?.id && isGathering && (
          <GatheringLockBanner characterId={character.id} />
        )}

        {/* Header */}
        <LocationHeader
          location={location}
          isFavorited={location.is_favorited ?? false}
          onToggleFavorite={handleToggleFavorite}
        />
      </div>

      {/* Content block */}
      <div className="flex flex-col gap-4 sm:gap-6">
        {/* Players + NPCs */}
        <PlayersSection
          players={location.players}
          npcs={location.npcs ?? []}
          currentUserId={userId}
          currentCharacterId={character?.id ?? null}
          currentCharacterLevel={Number(character?.level) || 0}
          locationId={location.id}
          locationMarkerType={location.marker_type}
          isCharacterHere={isCharacterHere}
        />

        {/* Neighbors */}
        <div className={actionsLocked ? 'pointer-events-none opacity-50' : ''}>
          <NeighborsSection neighbors={location.neighbors} />
        </div>

        {/* Mobs / Enemies */}
        <LocationMobs
          locationId={location.id}
          characterId={isCharacterHere ? (character?.id ?? null) : null}
        />

        {/* Active battles */}
        <BattlesSection
          locationId={location.id}
          characterId={character?.id ?? null}
          inBattle={inBattle}
          players={location.players}
        />

        {/* Resource gathering — shown only when nodes exist on the location.
            Hidden by GatheringSection itself when the array is empty. */}
        <GatheringSection
          locationId={location.id}
          characterId={character?.id ?? null}
          inventoryId={character?.id ?? null}
          isCharacterHere={isCharacterHere}
          actionsLocked={actionsLocked}
          nodes={location.gathering_nodes ?? []}
          onGatherSucceeded={fetchLocationData}
        />

        {/* Dungeon entrance — shown when dungeons exist at this location */}
        {isCharacterHere && !actionsLocked && (
          <DungeonEntrance
            locationId={location.id}
            players={location.players}
            currentCharacterId={character?.id ?? null}
          />
        )}

        {/* PvP Invitations & Trade requests — hidden when empty */}
        {isCharacterHere && character?.id && (
          <PendingInvitationsPanel locationId={location.id} />
        )}

        {/* Party invitations — hidden when empty */}
        {isCharacterHere && character?.id && (
          <PendingPartyInvitesPanel characterId={character.id} locationId={location.id} />
        )}

        {/* Loot — only shown when items exist */}
        {(location.loot ?? []).length > 0 && (
          <LootSection
            loot={location.loot}
            currentCharacterId={isCharacterHere ? (character?.id ?? null) : null}
            locationId={location.id}
            onPickup={handlePickupLoot}
          />
        )}

        {/* Posts */}
        <section className="bg-black/60 rounded-card p-4 sm:p-6 flex flex-col gap-4">
          <h2 className="gold-text text-lg sm:text-xl font-medium uppercase">
            Посты
          </h2>

          {/* Create form — shown if character exists or user is staff */}
          {(character || userIsStaff) && (
            <>
              {inBattle && (
                <p className="text-yellow-400 text-sm font-medium">Вы в бою</p>
              )}
              {!inBattle && isGathering && (
                <p className="text-yellow-400 text-sm font-medium">Идёт добыча — действия заблокированы</p>
              )}

              {/* Movement choice UI for neighbor locations */}
              {!isCharacterHere && isNeighborLocation && !actionsLocked && neighborEntry && (
                isTravelOnCooldown ? (
                  /* Cooldown timer */
                  <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4 flex items-center gap-3">
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5 text-yellow-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <p className="text-yellow-300 text-sm">
                      Перемещение будет доступно через{' '}
                      <span className="font-mono font-bold">
                        {cooldownMinutes > 0
                          ? `${cooldownMinutes} мин ${String(cooldownSeconds).padStart(2, '0')} сек`
                          : `${cooldownSeconds} сек`}
                      </span>
                    </p>
                  </div>
                ) : (
                  <div className="flex flex-col sm:flex-row gap-3">
                    {/* Option 1: Write post to move */}
                    <button
                      onClick={() => setShowPostForm(true)}
                      className={`flex-1 rounded-lg border p-4 text-left transition-colors ${
                        showPostForm
                          ? 'border-stat-energy bg-stat-energy/10'
                          : 'border-white/10 bg-white/5 hover:border-white/20'
                      }`}
                    >
                      <p className="text-white text-sm font-medium mb-1">
                        Написать пост для перемещения
                      </p>
                      <p className="text-stat-energy text-xs flex items-center gap-1">
                        <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                        {neighborEntry.energy_cost} выносливости
                      </p>
                    </button>

                    {/* Option 2: Quick move */}
                    {!location.no_quick_move && (
                      <button
                        onClick={handleQuickMove}
                        disabled={quickMoving}
                        className="flex-1 rounded-lg border border-white/10 bg-white/5 hover:border-white/20 p-4 text-left transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <p className="text-white text-sm font-medium mb-1">
                          {quickMoving ? 'Перемещение...' : 'Быстрое перемещение'}
                        </p>
                        <p className="text-stat-energy text-xs flex items-center gap-1">
                          <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                          </svg>
                          {neighborEntry.energy_cost * 2} выносливости
                        </p>
                        <p className="text-white/40 text-xs mt-1">Без написания поста</p>
                      </button>
                    )}
                  </div>
                )
              )}

              {/* Post form: shown if at current location, staff (always), or user chose "write post" on a neighbor (not during cooldown).
                  Hidden entirely while gathering — the player cannot post during a gather session. */}
              {!isGathering && (isCharacterHere || userIsStaff || (isNeighborLocation && showPostForm && !isTravelOnCooldown)) && (
                <PostCreateForm
                  onSubmit={handleSubmitPost}
                  onSubmitAsNpc={userIsStaff ? handleSubmitNpcPost : undefined}
                  disabled={actionsLocked || (!isCharacterHere && !isNeighborLocation && !userIsStaff)}
                  isStaff={userIsStaff}
                  npcs={location.npcs ?? []}
                />
              )}
            </>
          )}

          {location.posts.length === 0 ? (
            <p className="text-white/50 text-sm">Пока нет постов</p>
          ) : (
            <div className="flex flex-col gap-3">
              {location.posts.map((post) => (
                <PostCard
                  key={post.post_id}
                  post={post}
                  currentCharacterId={character?.id ?? null}
                  currentCharacterLevel={Number(character?.level) || 0}
                  currentUserId={userId}
                  players={location.players}
                  locationId={location.id}
                  locationMarkerType={location.marker_type}
                  isCharacterHere={isCharacterHere}
                  onLike={handleLike}
                  onUnlike={handleUnlike}
                  onTagPlayer={handleTagPlayer}
                  onReport={handleReport}
                  onRequestDeletion={handleRequestDeletion}
                />
              ))}
            </div>
          )}
        </section>

      </div>
    </div>
  );
};

export default LocationPage;
