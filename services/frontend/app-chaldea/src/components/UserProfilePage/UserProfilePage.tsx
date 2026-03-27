import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { User, Calendar, FileText, UserPlus, UserCheck, UserX, Settings, Activity, MessageSquare } from 'react-feather';
import { createConversation } from '../../redux/slices/messengerSlice';
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
import CharactersSection from './CharactersSection';
import ProfileSettingsModal, { buildColorEffectStyle, buildNicknameTextShadow } from './ProfileSettingsModal';
import { AVATAR_FRAMES } from '../../utils/avatarFrames';

const MAX_FILE_SIZE = 15 * 1024 * 1024;

type Tab = 'wall' | 'characters' | 'friends';

const TABS: { key: Tab; label: string }[] = [
  { key: 'wall', label: 'Стена' },
  { key: 'characters', label: 'Персонажи' },
  { key: 'friends', label: 'Друзья' },
];

const AVATAR_SIZE_DESKTOP = 180;
const AVATAR_SIZE_MOBILE = 120;

const UserProfilePage = () => {
  const { userId: paramUserId } = useParams<{ userId: string }>();
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const profile = useAppSelector(selectUserProfile);
  const loading = useAppSelector(selectProfileLoading);
  const avatarUploading = useAppSelector(selectAvatarUploading);
  const currentUserId = useAppSelector((state) => state.user.id) as number | null;

  const profileUserId = paramUserId ? Number(paramUserId) : currentUserId;
  const isOwnProfile = profileUserId !== null && profileUserId === currentUserId;

  const [activeTab, setActiveTab] = useState<Tab>('wall');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [messageSending, setMessageSending] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Responsive avatar size
  const [avatarSize, setAvatarSize] = useState(
    typeof window !== 'undefined' && window.innerWidth < 640 ? AVATAR_SIZE_MOBILE : AVATAR_SIZE_DESKTOP,
  );

  useEffect(() => {
    const handleResize = () => {
      setAvatarSize(window.innerWidth < 640 ? AVATAR_SIZE_MOBILE : AVATAR_SIZE_DESKTOP);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

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

  const handleMessage = async () => {
    if (!profileUserId || messageSending) return;
    setMessageSending(true);
    try {
      await dispatch(
        createConversation({ type: 'direct', participant_ids: [profileUserId], title: null }),
      ).unwrap();
      navigate('/messages');
    } catch {
      toast.error('Не удалось открыть диалог');
    } finally {
      setMessageSending(false);
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

  const friendshipStatus = profile.friendship_status;

  // Compute avatar frame styles
  const activeFrame = AVATAR_FRAMES.find((f) => f.id === profile?.avatar_frame);
  const avatarFrameStyle: React.CSSProperties = activeFrame
    ? { border: activeFrame.borderStyle, boxShadow: activeFrame.shadow }
    : {};
  const avatarEffectStyle: React.CSSProperties = profile?.avatar_effect_color
    ? { boxShadow: `0 0 16px ${profile.avatar_effect_color}` }
    : {};
  const combinedAvatarStyle: React.CSSProperties = {
    width: avatarSize,
    height: avatarSize,
    ...avatarFrameStyle,
    ...(avatarEffectStyle.boxShadow
      ? {
          boxShadow: [avatarFrameStyle.boxShadow, avatarEffectStyle.boxShadow]
            .filter(Boolean)
            .join(', ') || undefined,
        }
      : {}),
  };

  // Compute header background styles
  const headerBgStyle: React.CSSProperties = {};
  if (profile?.profile_bg_image) {
    headerBgStyle.backgroundImage = `url(${profile.profile_bg_image})`;
    headerBgStyle.backgroundSize = 'cover';
    headerBgStyle.backgroundPosition = profile.profile_bg_position || '50% 50%';
  }

  // Whether profile has a background image (used for text readability enhancements)
  const hasBgImage = !!profile?.profile_bg_image;

  // Text shadow style for readability over background images
  const textShadowStyle: React.CSSProperties = hasBgImage
    ? { textShadow: '0 2px 4px rgba(0,0,0,0.8), 0 0 8px rgba(0,0,0,0.5)' }
    : {};

  // Compute content section background style (tabs + tab content) using slider effects
  const contentBgStyle: React.CSSProperties = profile?.profile_bg_color
    ? buildColorEffectStyle(profile.profile_bg_color, 'bg_color', profile.profile_style_settings)
    : {};

  return (
    <div className="w-full max-w-[900px] mx-auto flex flex-col gap-6">
      {/* ── Profile Header ── */}
      <div
        className={`${!profile.profile_bg_image ? 'gray-bg' : 'rounded-card'} p-6 flex flex-col sm:flex-row items-center sm:items-start gap-6 relative`}
        style={headerBgStyle}
      >
        {/* Settings gear (own profile only) */}
        {isOwnProfile && (
          <button
            onClick={() => setSettingsOpen(true)}
            className="absolute top-4 right-4 text-white/40 hover:text-white transition-colors z-10"
            title="Настройки профиля"
          >
            <Settings size={20} />
          </button>
        )}

        {/* Message button (other profiles only) */}
        {!isOwnProfile && currentUserId && (
          <button
            onClick={handleMessage}
            disabled={messageSending}
            className="btn-blue absolute bottom-4 right-4 z-10 flex items-center gap-2 !px-3 !py-1.5 !text-sm disabled:opacity-50"
            title="Написать сообщение"
          >
            <MessageSquare size={16} />
            <span className="hidden sm:inline">Написать</span>
          </button>
        )}

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
          <div className="relative mb-8" style={{ width: avatarSize, minWidth: avatarSize }}>
            <div
              className={`gold-outline relative rounded-[12px] overflow-hidden bg-black/30 flex items-center justify-center ${
                isOwnProfile ? 'cursor-pointer group' : ''
              }`}
              style={combinedAvatarStyle}
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
            {/* Status text — absolutely positioned, flows horizontally to the right */}
            <div
              className="absolute left-0 mt-2"
              style={{ top: '100%', width: 'calc(100vw - 4rem)', maxWidth: 'calc(900px - 3rem)' }}
            >
              <span
                className={`text-white/90 text-[10px] uppercase tracking-wider block overflow-hidden text-ellipsis whitespace-nowrap ${hasBgImage ? 'rounded-md px-1.5 py-0.5' : ''}`}
                style={hasBgImage ? { backgroundColor: 'rgba(0,0,0,0.35)', backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)' } : undefined}
              >
                {profile.status_text || 'Игрок'}
              </span>
            </div>
          </div>

        </div>

        {/* User info — compact, each line has its own subtle highlight */}
        <div className="flex-1 flex flex-col gap-2 text-center sm:text-left min-w-0">
          {/* Nickname with optional background highlight */}
          <div
            className={hasBgImage ? 'w-fit rounded-lg px-3 py-1 mx-auto sm:mx-0' : ''}
            style={hasBgImage ? { backgroundColor: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(6px)', WebkitBackdropFilter: 'blur(6px)' } : undefined}
          >
            <h1
              className={`gold-text text-2xl font-semibold uppercase ${
                profile.profile_style_settings?.nickname_shimmer && profile.nickname_color
                  ? 'nickname-shimmer'
                  : ''
              } ${
                profile.profile_style_settings?.nickname_pulse && !profile.profile_style_settings?.nickname_shimmer
                  ? 'nickname-pulse'
                  : ''
              }`}
              style={(() => {
                const pss = profile.profile_style_settings;
                const color1 = profile.nickname_color;
                const br = pss?.nickname_brightness ?? 1.0;
                const ct = pss?.nickname_contrast ?? 1.0;
                const filterVal =
                  br !== 1.0 || ct !== 1.0
                    ? `brightness(${br}) contrast(${ct})`
                    : undefined;

                const glowVal = pss?.nickname_glow ?? 0;
                const textShadowVal = pss?.nickname_text_shadow ?? 0;
                const extraShadow = hasBgImage ? '0 2px 4px rgba(0,0,0,0.8), 0 0 8px rgba(0,0,0,0.5)' : undefined;
                const combinedTextShadow = buildNicknameTextShadow(color1, glowVal, textShadowVal, extraShadow);
                const fontFamily = pss?.nickname_font || undefined;

                if (color1) {
                  return {
                    color: color1,
                    backgroundImage: 'none',
                    WebkitTextFillColor: color1,
                    filter: filterVal,
                    textShadow: combinedTextShadow,
                    fontFamily,
                  };
                }

                // Default gold-text (no override)
                return {
                  ...textShadowStyle,
                  ...(combinedTextShadow ? { textShadow: combinedTextShadow } : {}),
                  fontFamily,
                };
              })()}
            >
              {profile.username}
            </h1>
          </div>

          {registeredDate && (
            <div
              className={`flex items-center gap-2 text-white/90 text-sm justify-center sm:justify-start ${hasBgImage ? 'w-fit rounded-md px-2 py-0.5 mx-auto sm:mx-0' : ''}`}
              style={hasBgImage ? { ...textShadowStyle, backgroundColor: 'rgba(0,0,0,0.35)', backdropFilter: 'blur(4px)' } : textShadowStyle}
            >
              <Calendar size={14} />
              <span>На сайте с {registeredDate}</span>
            </div>
          )}

          {/* Post count */}
          <div
            className={`flex items-center gap-1.5 text-white/90 text-sm justify-center sm:justify-start ${hasBgImage ? 'w-fit rounded-md px-2 py-0.5 mx-auto sm:mx-0' : ''}`}
            style={hasBgImage ? { ...textShadowStyle, backgroundColor: 'rgba(0,0,0,0.35)', backdropFilter: 'blur(4px)' } : textShadowStyle}
          >
            <FileText size={14} />
            <span>Записей: {profile.post_stats.total_posts}</span>
          </div>

          {/* Activity stub */}
          <div
            className={`flex items-center gap-1.5 text-white/90 text-sm justify-center sm:justify-start ${hasBgImage ? 'w-fit rounded-md px-2 py-0.5 mx-auto sm:mx-0' : ''}`}
            style={hasBgImage ? { ...textShadowStyle, backgroundColor: 'rgba(0,0,0,0.35)', backdropFilter: 'blur(4px)' } : textShadowStyle}
          >
            <Activity size={14} />
            <span>Активность: {profile.activity_points ?? 0}</span>
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

      {/* ── Tabs + Tab Content ── */}
      <div
        className={profile.profile_bg_color ? 'rounded-card' : ''}
        style={contentBgStyle}
      >
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
        <div className="px-3 sm:px-4 md:px-6 pt-4 pb-4 md:pb-6">
          {activeTab === 'wall' && (
            <WallSection
              profileUserId={profileUserId}
              isOwnProfile={isOwnProfile}
            />
          )}
          {activeTab === 'characters' && (
            <CharactersSection profileUserId={profileUserId} />
          )}
          {activeTab === 'friends' && (
            <FriendsSection
              profileUserId={profileUserId}
              isOwnProfile={isOwnProfile}
            />
          )}
        </div>
      </div>

      {/* ── Profile Settings Modal ── */}
      {isOwnProfile && profile && (
        <ProfileSettingsModal
          isOpen={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          profile={profile}
        />
      )}
    </div>
  );
};

export default UserProfilePage;
