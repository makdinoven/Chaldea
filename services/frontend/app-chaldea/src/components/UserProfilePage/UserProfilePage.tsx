import { useEffect, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { User, Calendar, FileText, Clock, UserPlus, UserCheck, UserX } from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  loadUserProfile,
  loadWallPosts,
  loadFriends,
  loadIncomingRequests,
  loadOutgoingRequests,
  sendRequest,
  rejectRequest,
  acceptRequest,
  uploadAvatar,
  resetUserProfile,
  selectUserProfile,
  selectProfileLoading,
  selectAvatarUploading,
} from '../../redux/slices/userProfileSlice';
import WallSection from './WallSection';
import FriendsSection from './FriendsSection';

const MAX_FILE_SIZE = 15 * 1024 * 1024;

type Tab = 'wall' | 'friends';

const TABS: { key: Tab; label: string }[] = [
  { key: 'wall', label: 'Стена' },
  { key: 'friends', label: 'Друзья' },
];

const AVATAR_SIZE = 120;

const UserProfilePage = () => {
  const { userId: paramUserId } = useParams<{ userId: string }>();
  const dispatch = useAppDispatch();
  const profile = useAppSelector(selectUserProfile);
  const loading = useAppSelector(selectProfileLoading);
  const avatarUploading = useAppSelector(selectAvatarUploading);
  const currentUserId = useAppSelector((state) => state.user.id) as number | null;

  const profileUserId = paramUserId ? Number(paramUserId) : currentUserId;
  const isOwnProfile = profileUserId !== null && profileUserId === currentUserId;

  const [activeTab, setActiveTab] = useState<Tab>('wall');
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!profileUserId) return;

    dispatch(resetUserProfile());
    dispatch(loadUserProfile(profileUserId));
    dispatch(loadWallPosts({ userId: profileUserId, page: 1 }));
    dispatch(loadFriends(profileUserId));

    if (isOwnProfile) {
      dispatch(loadIncomingRequests());
      dispatch(loadOutgoingRequests());
    }

    return () => {
      dispatch(resetUserProfile());
    };
  }, [profileUserId, dispatch, isOwnProfile]);

  const handleAvatarClick = () => {
    if (!isOwnProfile) return;
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';

    if (file.size > MAX_FILE_SIZE) {
      toast.error('Файл слишком большой. Максимальный размер: 15 МБ');
      return;
    }

    if (!profileUserId) return;

    try {
      await dispatch(uploadAvatar({ userId: profileUserId, file })).unwrap();
      toast.success('Аватарка обновлена');
    } catch {
      toast.error('Не удалось загрузить аватарку');
    }
  };

  const handleFriendAction = async () => {
    if (!profileUserId || !profile) return;

    const status = profile.friendship_status;
    try {
      if (status === 'none' || status === null) {
        await dispatch(sendRequest(profileUserId)).unwrap();
        dispatch(loadUserProfile(profileUserId));
        toast.success('Запрос на дружбу отправлен');
      } else if (status === 'pending_received' && profile.friendship_id) {
        await dispatch(acceptRequest({ friendshipId: profile.friendship_id, userId: profileUserId })).unwrap();
        dispatch(loadUserProfile(profileUserId));
        toast.success('Запрос на дружбу принят');
      } else if (status === 'pending_sent' && profile.friendship_id) {
        await dispatch(rejectRequest(profile.friendship_id)).unwrap();
        dispatch(loadUserProfile(profileUserId));
        toast.success('Запрос отменён');
      }
    } catch {
      toast.error('Не удалось выполнить действие');
    }
  };

  if (!profileUserId) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-white/50">Войдите, чтобы увидеть профиль</p>
      </div>
    );
  }

  if (loading && !profile) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-10 h-10 border-2 border-white/20 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-white/50">Профиль не найден</p>
      </div>
    );
  }

  const registeredDate = profile.registered_at
    ? new Date(profile.registered_at).toLocaleDateString('ru-RU', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      })
    : null;

  const lastPostDate = profile.post_stats.last_post_date
    ? new Date(profile.post_stats.last_post_date).toLocaleDateString('ru-RU', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      })
    : null;

  const friendshipStatus = profile.friendship_status;

  return (
    <div className="w-full max-w-[900px] mx-auto flex flex-col gap-6">
      {/* ── Profile Header ── */}
      <div className="gray-bg p-6 flex flex-col sm:flex-row items-center sm:items-start gap-6">
        {/* Avatars row */}
        <div className="flex items-end gap-5 flex-shrink-0">
          {/* User avatar */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleFileChange}
          />
          <div className="flex flex-col items-center gap-2">
            <div
              className={`gold-outline relative rounded-full overflow-hidden bg-black/30 flex items-center justify-center ${
                isOwnProfile ? 'cursor-pointer group' : ''
              }`}
              style={{ width: AVATAR_SIZE, height: AVATAR_SIZE }}
              onClick={handleAvatarClick}
            >
              {profile.avatar ? (
                <img
                  src={profile.avatar}
                  alt={profile.username}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-white/20">
                  <User size={48} />
                </div>
              )}

              {isOwnProfile && !avatarUploading && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity">
                  <span className="text-white text-xs font-medium text-center px-2">
                    Изменить фото
                  </span>
                </div>
              )}

              {avatarUploading && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/60">
                  <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                </div>
              )}
            </div>
            <span className="text-white/40 text-[10px] uppercase tracking-wider">
              Игрок
            </span>
          </div>

          {/* Character avatar */}
          {profile.character && (
            <Link to="/profile" className="flex flex-col items-center gap-2 group/char">
              <div
                className="gold-outline relative rounded-full overflow-hidden bg-black/30"
                style={{ width: AVATAR_SIZE, height: AVATAR_SIZE }}
              >
                {profile.character.avatar ? (
                  <img
                    src={profile.character.avatar}
                    alt={profile.character.name}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-white/20">
                    <User size={48} />
                  </div>
                )}

                {/* Level badge */}
                {profile.character.level != null && (
                  <div
                    className="absolute bottom-1 left-1/2 -translate-x-1/2 flex items-center justify-center"
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: '50%',
                      background: 'linear-gradient(180deg, #FFF9B8 0%, #BCAB4C 100%)',
                      boxShadow: '0 2px 8px rgba(0,0,0,0.5)',
                    }}
                  >
                    <span className="text-black text-xs font-bold leading-none">
                      {profile.character.level}
                    </span>
                  </div>
                )}

                {/* Hover overlay */}
                <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 group-hover/char:opacity-100 transition-opacity">
                  <span className="text-white text-xs font-medium text-center px-2">
                    Персонаж
                  </span>
                </div>
              </div>
              <span className="text-white/40 text-[10px] uppercase tracking-wider group-hover/char:text-site-blue transition-colors">
                {profile.character.name}
              </span>
            </Link>
          )}
        </div>

        {/* User info */}
        <div className="flex-1 flex flex-col gap-3 text-center sm:text-left min-w-0">
          <h1 className="gold-text text-2xl font-semibold uppercase">
            {profile.username}
          </h1>

          {registeredDate && (
            <div className="flex items-center gap-2 text-white/50 text-sm justify-center sm:justify-start">
              <Calendar size={14} />
              <span>На сайте с {registeredDate}</span>
            </div>
          )}

          {/* Post stats */}
          <div className="flex items-center gap-4 text-white/50 text-sm justify-center sm:justify-start">
            <div className="flex items-center gap-1.5">
              <FileText size={14} />
              <span>Записей: {profile.post_stats.total_posts}</span>
            </div>
            {lastPostDate && (
              <div className="flex items-center gap-1.5">
                <Clock size={14} />
                <span>Последний: {lastPostDate}</span>
              </div>
            )}
          </div>

          {/* Friend action button */}
          {!isOwnProfile && currentUserId && (
            <div className="flex justify-center sm:justify-start mt-1">
              {friendshipStatus === 'accepted' ? (
                <div className="flex items-center gap-2 text-green-400 text-sm">
                  <UserCheck size={16} />
                  <span>Вы друзья</span>
                </div>
              ) : friendshipStatus === 'pending_sent' ? (
                <button
                  onClick={handleFriendAction}
                  className="flex items-center gap-2 text-white/50 hover:text-site-red text-sm transition-colors"
                >
                  <UserX size={16} />
                  <span>Запрос отправлен (отменить)</span>
                </button>
              ) : friendshipStatus === 'pending_received' ? (
                <button
                  onClick={handleFriendAction}
                  className="flex items-center gap-2 text-site-blue hover:text-white text-sm transition-colors"
                >
                  <UserPlus size={16} />
                  <span>Принять запрос в друзья</span>
                </button>
              ) : (
                <button
                  onClick={handleFriendAction}
                  className="flex items-center gap-2 text-site-blue hover:text-white text-sm transition-colors"
                >
                  <UserPlus size={16} />
                  <span>Добавить в друзья</span>
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Tabs ── */}
      <div className="flex gap-0">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 py-3 text-sm font-medium uppercase tracking-wider transition-colors relative ${
              activeTab === tab.key
                ? 'text-white'
                : 'text-white/40 hover:text-white/70'
            }`}
          >
            {tab.label}
            {activeTab === tab.key && (
              <div
                className="absolute bottom-0 left-1/2 -translate-x-1/2 h-[2px] w-3/4"
                style={{
                  background: 'linear-gradient(90deg, rgba(255,249,184,0) 0%, #FFF9B8 50%, rgba(188,171,76,0) 100%)',
                }}
              />
            )}
          </button>
        ))}
      </div>

      {/* ── Tab Content ── */}
      <div>
        {activeTab === 'wall' && (
          <WallSection
            profileUserId={profileUserId}
            isOwnProfile={isOwnProfile}
          />
        )}
        {activeTab === 'friends' && (
          <FriendsSection
            profileUserId={profileUserId}
            isOwnProfile={isOwnProfile}
          />
        )}
      </div>
    </div>
  );
};

export default UserProfilePage;
