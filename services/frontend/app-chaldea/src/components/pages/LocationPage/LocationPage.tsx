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
import LocationTopBar from './LocationTopBar';
import PlayersSection from './PlayersSection';
import PostCard from './PostCard';
import PostCreateForm from './PostCreateForm';
import NeighborsSection from './NeighborsSection';
import LootSection from './LootSection';
import PendingInvitationsPanel from './PendingInvitationsPanel';
import PendingPartyInvitesPanel from './PendingPartyInvitesPanel';
import EnemiesSection from './EnemiesSection';
import { fetchMobsByLocation } from '../../../api/mobs';
import { fetchMobPacksByLocation } from '../../../api/mobPacks';
import { getPartiesOnLocation, type PartyOnLocation } from '../../../api/squads';
import { selectDungeonsAtLocation } from '../../../redux/slices/dungeonSlice';
import BattlesSection from './BattlesSection';
import useBattleLock from '../../../hooks/useBattleLock';
import useBattlePreview from '../../../hooks/useBattlePreview';
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
  const { inBattle, battleId } = useBattleLock(character?.id);
  // Enriched banner data (FEAT-152 A4): opponent, round, whose turn.
  // Silent-fail — the banner degrades to its generic variant on error.
  const { preview: battlePreview } = useBattlePreview(inBattle ? battleId : null);
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

  // --- Squads on this location (FEAT-153 §3.5) ---
  // Lifted out of the deleted PartiesOnLocation so the players↔squads join
  // happens in one place, inside «Кто здесь». Unlike the old component, a
  // failed load is NOT swallowed — PlayersSection renders it inline with a
  // «Повторить» button while still showing the players.
  const [parties, setParties] = useState<PartyOnLocation[]>([]);
  const [partiesError, setPartiesError] = useState<string | null>(null);

  const loadParties = useCallback(() => {
    if (!locationId) return;
    setPartiesError(null);
    getPartiesOnLocation(Number(locationId))
      .then((data) => setParties(data))
      .catch(() => {
        setParties([]);
        setPartiesError('Не удалось загрузить отряды');
      });
  }, [locationId]);

  useEffect(() => {
    loadParties();
  }, [loadParties]);

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

  // Mobs on this location — offered as targets for a combat post (FEAT-145).
  const [combatTargets, setCombatTargets] = useState<{ character_id: number; name: string }[]>([]);
  useEffect(() => {
    let cancelled = false;
    // Standalone mobs + packs (a pack is named via its lead mob, FEAT-147) are both
    // offered as combat-post targets.
    Promise.all([
      fetchMobsByLocation(Number(locationId)).catch(() => []),
      fetchMobPacksByLocation(Number(locationId)).catch(() => []),
    ])
      .then(([mobs, packs]) => {
        if (cancelled) return;
        const mobTargets = mobs
          .filter((m) => m.status !== 'in_battle')
          .map((m) => ({ character_id: m.character_id, name: m.name }));
        const packTargets = packs
          .filter((p) => p.status !== 'in_battle')
          .map((p) => ({ character_id: p.lead_character_id, name: `Стая: ${p.name}` }));
        setCombatTargets([...mobTargets, ...packTargets]);
      })
      .catch(() => {
        if (!cancelled) setCombatTargets([]);
      });
    return () => {
      cancelled = true;
    };
  }, [locationId]);

  // Which gated actions the character can currently do here (FEAT-145).
  const [gateStatus, setGateStatus] = useState<Record<string, number[]>>({});
  const refetchGates = useCallback(() => {
    if (!character?.id) {
      setGateStatus({});
      return;
    }
    axios
      .get(`${BASE_URL}/locations/action-gate/status`, {
        params: { character_id: character.id, location_id: locationId },
      })
      .then((r) => setGateStatus(r.data || {}))
      .catch(() => setGateStatus({}));
  }, [character?.id, locationId]);
  useEffect(() => {
    refetchGates();
  }, [refetchGates]);

  // Gate targets available on this location for the post editor (FEAT-145 v2).
  const dungeonsAtLocation = useAppSelector(selectDungeonsAtLocation);
  const gateOptions = useMemo(
    () => ({
      combat: combatTargets.map((m) => ({ id: m.character_id, name: m.name })),
      npc_dialogue: (location?.npcs ?? []).map((n) => ({ id: n.id, name: n.name })),
      gathering: (location?.gathering_nodes ?? []).map((g) => ({ id: g.id, name: g.node_name })),
      dungeon: (dungeonsAtLocation ?? []).map((d) => ({ id: d.id, name: d.name })),
    }),
    [combatTargets, location, dungeonsAtLocation],
  );

  const handleSubmitPost = useCallback(
    async (content: string, gates: { action_type: string; targets: number[] }[] = []) => {
      try {
        await axios.post(`${BASE_URL}/locations/${locationId}/move_and_post`, {
          character_id: character?.id,
          location_id: locationId,
          content,
          gates,
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
        refetchGates();
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
      <div className="flex items-center justify-center min-h-[60vh] px-4">
        <div className="bg-site-bg backdrop-blur-sm rounded-card border border-white/10 shadow-card p-6 sm:p-8 flex flex-col items-center gap-4 max-w-sm w-full text-center">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-8 h-8 text-white/30" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <p className="text-white/60 text-base">{error || 'Локация не найдена'}</p>
          <button
            onClick={() => navigate(-1)}
            className="btn-blue text-sm px-6 py-2"
          >
            Назад
          </button>
        </div>
      </div>
    );
  }

  // FEAT-153 §3.6 — row 3 drops its third track when the location has no
  // gathering nodes (GatheringSection returns null in that case), so the row
  // never carries an empty column.
  const hasGathering = (location.gathering_nodes ?? []).length > 0;
  // FEAT-153 §3.7 — ground loot is the ONLY remaining sidebar block. When there
  // is none, the body grid must collapse to a single track: hiding just the
  // children would leave the hardcoded 400px gutter and keep posts narrow.
  // Anything added back to the sidebar must be OR-ed into this flag.
  const hasSidebar = (location.loot ?? []).length > 0;

  return (
    <div className="flex flex-col gap-4 sm:gap-6 pb-10">
      {/* Top bar: back, breadcrumb, labeled favorite (FEAT-152 A1/A8) */}
      <LocationTopBar
        location={location}
        isFavorited={location.is_favorited ?? false}
        onToggleFavorite={handleToggleFavorite}
        onBack={() => navigate(-1)}
      />

      {/* Battle lock banner — full mock version (A4): opponent, round,
          whose turn, «Вернуться к бою»; degrades gracefully without preview */}
      {inBattle && (
        <BattleLockBanner
          title="Вы в бою!"
          message="Пока бой не завершён, перемещение, добыча и написание постов недоступны."
          battleId={battleId}
          preview={battlePreview}
          currentCharacterId={character?.id ?? null}
          fallbackLocationId={location.id}
        />
      )}

      {/* Gathering lock banner — shown while a resource-gathering session
          is active. Mirrors BattleLockBanner placement so the player
          always sees what is blocking actions on this page. */}
      {character?.id && isGathering && (
        <GatheringLockBanner characterId={character.id} />
      )}

      {/* Time-sensitive alerts next to banners (§3.5 B6) — hidden when empty */}
      {isCharacterHere && character?.id && (
        <PendingInvitationsPanel locationId={location.id} />
      )}
      {isCharacterHere && character?.id && (
        <PendingPartyInvitesPanel characterId={character.id} locationId={location.id} />
      )}

      {/* Hero banner — «Соседние локации» now live inside it (§3.2).
          The dimming wrapper carries the panel's own sizing classes: it is the
          flex child of the hero body, so without them `lg:self-stretch` would
          apply to the wrapper while the panel collapsed to content height. */}
      <LocationHeader
        location={location}
        aside={
          <div
            className={`flex min-h-0 w-full lg:w-[330px] lg:shrink-0 lg:self-stretch ${
              actionsLocked ? 'pointer-events-none opacity-50' : ''
            }`}
          >
            <NeighborsSection neighbors={location.neighbors} />
          </div>
        }
      />

      {/* Row 3 (§3.1/§3.6): Кто здесь | Противники | Добыча ресурсов.
          Equal-height columns; the third track exists only when there are
          gathering nodes. Both templates are written out in full so Tailwind's
          JIT scanner emits them. */}
      <div
        className={`grid grid-cols-1 gap-4 sm:gap-6 items-stretch ${
          hasGathering ? 'lg:grid-cols-[1.5fr_1fr_1fr]' : 'lg:grid-cols-[1.5fr_1fr]'
        }`}
      >
        {/* Players + NPCs + squads — NOT dimmed in battle (A10) */}
        <div className="min-w-0">
          <PlayersSection
            players={location.players}
            npcs={location.npcs ?? []}
            currentUserId={userId}
            currentCharacterId={character?.id ?? null}
            currentCharacterLevel={Number(character?.level) || 0}
            locationId={location.id}
            locationMarkerType={location.marker_type}
            isCharacterHere={isCharacterHere}
            talkableNpcIds={(gateStatus.npc_dialogue as number[]) ?? []}
            parties={parties}
            partiesError={partiesError}
            onRetryParties={loadParties}
          />
        </div>

        {/* Enemies — single mobs AND packs (§3.4); dimmed while locked */}
        <div className={`min-w-0 ${actionsLocked ? 'pointer-events-none opacity-50' : ''}`}>
          <EnemiesSection
            locationId={location.id}
            characterId={isCharacterHere ? (character?.id ?? null) : null}
            gatedMobIds={(gateStatus.combat as number[]) ?? []}
          />
        </div>

        {/* Resource gathering — moved out of the sidebar (§3.3) */}
        {hasGathering && (
          <div className="min-w-0">
            <GatheringSection
              locationId={location.id}
              characterId={character?.id ?? null}
              inventoryId={character?.id ?? null}
              isCharacterHere={isCharacterHere}
              actionsLocked={actionsLocked}
              nodes={location.gathering_nodes ?? []}
              onGatherSucceeded={fetchLocationData}
            />
          </div>
        )}
      </div>

      {/* Active battles — full width. Rendered unconditionally on purpose:
          the visibility guard lives inside the component, which owns the 10s
          poll that discovers battles (§3.9). */}
      <BattlesSection
        locationId={location.id}
        characterId={character?.id ?? null}
        inBattle={inBattle}
        players={location.players}
      />

      {/* Dungeon entrance — shown when dungeons exist at this location */}
      {isCharacterHere && !actionsLocked && (
        <DungeonEntrance
          locationId={location.id}
          players={location.players}
          currentCharacterId={character?.id ?? null}
        />
      )}

      {/* Body grid: chronicle (posts) + sidebar; sidebar above posts on <lg.
          Both the track template and the sidebar wrapper are conditional (§3.7)
          — with no ground loot the posts span the full container width. */}
      <div
        className={`grid grid-cols-1 gap-4 sm:gap-6 items-start ${
          hasSidebar ? 'lg:grid-cols-[1fr_400px]' : 'lg:grid-cols-1'
        }`}
      >
        {/* LEFT: movement, chronicle heading, post form, posts feed */}
        <div className="order-2 lg:order-1 flex flex-col gap-4 min-w-0">
          {/* Movement choice UI for neighbor locations (B1) */}
          {(character || userIsStaff) &&
            !isCharacterHere && isNeighborLocation && !actionsLocked && neighborEntry && (
            isTravelOnCooldown ? (
              /* Cooldown timer */
              <div className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/30 p-4 flex items-center gap-3.5">
                <span className="w-10 h-10 shrink-0 flex items-center justify-center rounded-[10px] bg-gold/10 border border-gold-dark/30 text-gold">
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </span>
                <p className="text-gold-light text-sm">
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
                  className={`flex-1 bg-site-bg backdrop-blur-sm rounded-card border p-4 text-left transition-colors duration-200 ease-site ${
                    showPostForm
                      ? 'border-stat-energy bg-stat-energy/10'
                      : 'border-white/10 hover:border-gold-dark/40'
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
                    className="flex-1 bg-site-bg backdrop-blur-sm rounded-card border border-white/10 hover:border-gold-dark/40 p-4 text-left transition-colors duration-200 ease-site disabled:opacity-50 disabled:cursor-not-allowed"
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

          {/* Chronicle heading */}
          <div className="flex items-center gap-3 sm:gap-4">
            <span className="gold-text text-xs sm:text-sm font-medium uppercase tracking-[0.2em] shrink-0">
              Хроника локации
            </span>
            <span className="flex-1 h-px bg-gradient-to-r from-gold-dark/50 to-transparent" />
            <span className="text-white/40 text-xs shrink-0">
              {location.posts.length} постов
            </span>
          </div>

          {/* Create form — shown if character exists or user is staff.
              While the character is locked (battle / gathering), the form is
              replaced by a mock-style hint card (B16). */}
          {(character || userIsStaff) && (
            inBattle ? (
              <div className="bg-site-bg backdrop-blur-sm rounded-card border border-stat-hp/30 flex items-center gap-3.5 p-4 sm:px-5">
                <span className="w-11 h-11 shrink-0 flex items-center justify-center rounded-[11px] bg-stat-hp/15 border border-stat-hp/35 text-stat-hp">
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-[22px] h-[22px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M14.5 17.5 3 6V3h3l11.5 11.5" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="m13 19 6-6" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="m16 16 4 4" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="m19 21 2-2" />
                  </svg>
                </span>
                <div className="flex flex-col gap-0.5 min-w-0">
                  <span className="text-stat-hp text-sm font-medium">Вы в бою</span>
                  <span className="text-white/55 text-xs">
                    Написание постов будет доступно после завершения боя.
                  </span>
                </div>
              </div>
            ) : isGathering ? (
              <div className="bg-site-bg backdrop-blur-sm rounded-card border border-stat-energy/30 flex items-center gap-3.5 p-4 sm:px-5">
                <span className="w-11 h-11 shrink-0 flex items-center justify-center rounded-[11px] bg-stat-energy/15 border border-stat-energy/35 text-stat-energy">
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-[22px] h-[22px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M11 20A7 7 0 019.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M2 21c0-3 1.85-5.36 5.08-6" />
                  </svg>
                </span>
                <div className="flex flex-col gap-0.5 min-w-0">
                  <span className="text-stat-energy text-sm font-medium">Идёт добыча</span>
                  <span className="text-white/55 text-xs">
                    Написание постов будет доступно после завершения добычи.
                  </span>
                </div>
              </div>
            ) : (
              /* Post form: shown if at current location, staff (always), or user
                 chose "write post" on a neighbor (not during cooldown). */
              (isCharacterHere || userIsStaff || (isNeighborLocation && showPostForm && !isTravelOnCooldown)) && (
                <PostCreateForm
                  onSubmit={handleSubmitPost}
                  onSubmitAsNpc={userIsStaff ? handleSubmitNpcPost : undefined}
                  gateOptions={gateOptions}
                  disabled={actionsLocked || (!isCharacterHere && !isNeighborLocation && !userIsStaff)}
                  isStaff={userIsStaff}
                  npcs={location.npcs ?? []}
                  locationName={location.name}
                />
              )
            )
          )}

          {/* Posts feed */}
          {location.posts.length === 0 ? (
            <div className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] p-6 text-center">
              <p className="text-white/50 text-sm">
                Здесь пока нет постов — станьте первым, кто опишет свои действия.
              </p>
            </div>
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
        </div>

        {/* RIGHT: sidebar — «На земле» only; gathering moved to row 3 (§3.3)
            and squads into «Кто здесь» (§3.5). Above posts on <lg. */}
        {hasSidebar && (
          <div className="order-1 lg:order-2 flex flex-col gap-4 sm:gap-6 min-w-0">
            <LootSection
              loot={location.loot}
              currentCharacterId={isCharacterHere ? (character?.id ?? null) : null}
              locationId={location.id}
              onPickup={handlePickupLoot}
            />
          </div>
        )}
      </div>
    </div>
  );
};

export default LocationPage;
