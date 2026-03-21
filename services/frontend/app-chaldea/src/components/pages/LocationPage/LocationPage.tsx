import { useEffect, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import axios from 'axios';
import { BASE_URL } from '../../../api/api';
import { useBodyBackground } from '../../../hooks/useBodyBackground';
import { useAppSelector } from '../../../redux/store';
import { LocationData } from './types';
import LocationHeader from './LocationHeader';
import PlayersSection from './PlayersSection';
import PostCard from './PostCard';
import PostCreateForm from './PostCreateForm';
import NeighborsSection from './NeighborsSection';
import LootSection from './LootSection';
import PlaceholderSection from './PlaceholderSection';

const LocationPage = () => {
  const navigate = useNavigate();
  const { locationId } = useParams<{ locationId: string }>();
  const [location, setLocation] = useState<LocationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const character = useAppSelector((state) => state.user.character);
  const userId = useAppSelector((state) => state.user.id);

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
        toast.success('Пост отправлен');
        await fetchLocationData();
      } catch {
        toast.error('Не удалось отправить пост');
      }
    },
    [locationId, character?.id, fetchLocationData]
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

  const isCharacterHere = character?.current_location?.id === location.id;

  return (
    <div className="flex flex-col gap-6 sm:gap-8 pb-10 bg-black/40 rounded-card p-4 sm:p-6 backdrop-blur-sm">
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

      {/* Header */}
      <LocationHeader
        location={location}
        isFavorited={location.is_favorited ?? false}
        onToggleFavorite={handleToggleFavorite}
      />

      <div className="gradient-divider-h relative pb-2" />

      {/* Players */}
      <section className="bg-black/50 rounded-card p-4 sm:p-6">
        <PlayersSection players={location.players} />
      </section>

      <div className="gradient-divider-h relative pb-2" />

      {/* Loot */}
      <LootSection
        loot={location.loot ?? []}
        currentCharacterId={isCharacterHere ? (character?.id ?? null) : null}
        locationId={location.id}
        onPickup={handlePickupLoot}
      />

      <div className="gradient-divider-h relative pb-2" />

      {/* Posts */}
      <section className="bg-black/50 rounded-card p-4 sm:p-6 flex flex-col gap-4">
        <h2 className="gold-text text-lg sm:text-xl font-medium uppercase">
          Посты
        </h2>

        {/* Create form — shown if character exists */}
        {character && (
          <PostCreateForm
            onSubmit={handleSubmitPost}
            disabled={!isCharacterHere && !character}
          />
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
                currentUserId={userId}
                players={location.players}
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

      <div className="gradient-divider-h relative pb-2" />

      {/* Neighbors */}
      <section className="bg-black/50 rounded-card p-4 sm:p-6">
        <NeighborsSection neighbors={location.neighbors} />
      </section>

      <div className="gradient-divider-h relative pb-2" />

      {/* Placeholder sections */}
      <div className="flex flex-col gap-4 sm:flex-row sm:gap-4">
        <div className="flex-1">
          <PlaceholderSection title="НПС" message="Скоро здесь появятся неигровые персонажи" />
        </div>
        <div className="flex-1">
          <PlaceholderSection title="Враги" message="Скоро здесь появятся враги для сражений" />
        </div>
        <div className="flex-1">
          <PlaceholderSection title="Бой на локации" message="Скоро здесь можно будет сражаться" />
        </div>
      </div>
    </div>
  );
};

export default LocationPage;
