import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Calendar, FileText, UserPlus, UserCheck, UserX, Activity, MessageSquare, Slash, Lock } from 'react-feather';
import { createConversation, blockUser, unblockUser } from '../../redux/slices/messengerSlice';
import { checkBlock } from '../../api/messengerApi';
import type { BlockCheckResponse } from '../../types/messenger';
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
import { buildColorEffectStyle, buildNicknameTextShadow } from './profileStyle';
import AvatarWithFrame from '../common/AvatarWithFrame';
import AvatarEditor from '../CommonComponents/AvatarEditor/AvatarEditor';
import { formatServerDate } from '../../utils/serverDate';


type Tab = 'wall' | 'characters' | 'friends';

const TABS: { key: Tab; label: string }[] = [
  { key: 'wall', label: 'Стена' },
  { key: 'characters', label: 'Персонажи' },
  { key: 'friends', label: 'Друзья' },
];

const AVATAR_SIZE_DESKTOP = 180;

const HiddenNotice = ({ text }: { text: string }) => (
  <div className="gray-bg p-8 flex flex-col items-center gap-2 text-center">
    <Lock size={20} className="text-white/30" />
    <p className="text-white/50 text-sm">{text}</p>
  </div>
);
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
  const [blockState, setBlockState] = useState<BlockCheckResponse | null>(null);
  const [blockBusy, setBlockBusy] = useState(false);
  const [messageSending, setMessageSending] = useState(false);
  const [avatarEditor, setAvatarEditor] = useState(false);

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
    // The wall and the friends list load only when the owner lets this viewer see them.
    dispatch(loadUserProfile(profileUserId))
      .unwrap()
      .then((loaded) => {
        const can = loaded.viewer_permissions;
        if (can?.can_view_wall ?? true) dispatch(loadWallPosts({ userId: profileUserId, page: 1 }));
        if (can?.can_view_friends ?? true) dispatch(loadFriends(profileUserId));
      })
      .catch(() => {});

    if (isOwnProfile) {
      dispatch(loadIncomingRequests());
      dispatch(loadOutgoingRequests());
    }

    return () => {
      dispatch(resetUserProfile());
    };
  }, [profileUserId, dispatch, isOwnProfile]);

  useEffect(() => {
    setBlockState(null);
    if (!profileUserId || isOwnProfile || currentUserId === null) return undefined;
    let cancelled = false;
    checkBlock(profileUserId)
      .then(({ data }) => {
        if (!cancelled) setBlockState(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [profileUserId, isOwnProfile, currentUserId]);

  const handleToggleBlock = async () => {
    if (!profileUserId || !blockState || blockBusy) return;
    setBlockBusy(true);
    try {
      if (blockState.blocked_by_me) {
        await dispatch(unblockUser(profileUserId)).unwrap();
        toast.success('Пользователь разблокирован');
      } else {
        await dispatch(blockUser(profileUserId)).unwrap();
        toast.success('Пользователь заблокирован');
      }
      const { data } = await checkBlock(profileUserId);
      setBlockState(data);
      dispatch(loadUserProfile(profileUserId));
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось изменить блокировку');
    } finally {
      setBlockBusy(false);
    }
  };

  const handleAvatarClick = () => {
    if (!isOwnProfile) return;
    setAvatarEditor(true);
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
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось выполнить действие');
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
    ? formatServerDate(profile.registered_at, {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      })
    : null;

  const friendshipStatus = profile.friendship_status;
  const permissions = profile.viewer_permissions;
  const canSendFriendRequest = (permissions?.can_send_friend_request ?? true) && !blockState?.is_blocked;
  const canPostOnWall = (permissions?.can_post_wall ?? true) && !blockState?.is_blocked;

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
        {/* Message + block (other profiles only) */}
        {!isOwnProfile && currentUserId && (
          <div className="absolute bottom-4 right-4 z-10 flex items-center gap-2">
            {blockState && (
              <button
                onClick={handleToggleBlock}
                disabled={blockBusy}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-card text-sm bg-black/40 backdrop-blur-sm transition-colors duration-200 ease-site disabled:opacity-50 ${
                  blockState.blocked_by_me ? 'text-white/70 hover:text-white' : 'text-white/50 hover:text-site-red'
                }`}
                title={blockState.blocked_by_me ? 'Разблокировать' : 'Заблокировать'}
              >
                <Slash size={16} />
                <span className="hidden sm:inline">
                  {blockState.blocked_by_me ? 'Разблокировать' : 'Заблокировать'}
                </span>
              </button>
            )}
            {!blockState?.is_blocked && (
              <button
                onClick={handleMessage}
                disabled={messageSending}
                className="btn-blue flex items-center gap-2 !px-3 !py-1.5 !text-sm disabled:opacity-50"
                title="Написать сообщение"
              >
                <MessageSquare size={16} />
                <span className="hidden sm:inline">Написать</span>
              </button>
            )}
          </div>
        )}

        {/* Avatars row */}
        <div className="flex items-end gap-5 flex-shrink-0">
          {/* User avatar */}
          {avatarEditor && profileUserId && (
            <AvatarEditor
              title="Аватар профиля"
              currentUrl={profile.avatar}
              onClose={() => setAvatarEditor(false)}
              onUpload={(file, crop) => dispatch(uploadAvatar({ userId: profileUserId, file, crop })).unwrap()}
              onReframe={(crop) => dispatch(uploadAvatar({ userId: profileUserId, file: null, crop })).unwrap()}
            />
          )}
          <div className="relative mb-8" style={{ width: avatarSize, minWidth: avatarSize }}>
            <div
              className={`relative ${isOwnProfile ? 'cursor-pointer group' : ''}`}
              onClick={handleAvatarClick}
            >
              <AvatarWithFrame
                avatarUrl={profile.avatar}
                frameSlug={profile.avatar_frame ?? null}
                username={profile.username}
                rounded="rounded"
                className={profile.avatar_frame ? '' : 'gold-outline'}
                pixelSize={avatarSize}
              />

              {isOwnProfile && !avatarUploading && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity rounded-[12px]">
                  <span className="text-white text-xs font-medium text-center px-2">
                    Изменить фото
                  </span>
                </div>
              )}

              {avatarUploading && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/60 rounded-[12px]">
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

          {/* Post count — absent when the owner hides the wall */}
          {profile.post_stats && (
          <div
            className={`flex items-center gap-1.5 text-white/90 text-sm justify-center sm:justify-start ${hasBgImage ? 'w-fit rounded-md px-2 py-0.5 mx-auto sm:mx-0' : ''}`}
            style={hasBgImage ? { ...textShadowStyle, backgroundColor: 'rgba(0,0,0,0.35)', backdropFilter: 'blur(4px)' } : textShadowStyle}
          >
            <FileText size={14} />
            <span>Записей: {profile.post_stats.total_posts}</span>
          </div>
          )}

          {/* Activity stub */}
          <div
            className={`flex items-center gap-1.5 text-white/90 text-sm justify-center sm:justify-start ${hasBgImage ? 'w-fit rounded-md px-2 py-0.5 mx-auto sm:mx-0' : ''}`}
            style={hasBgImage ? { ...textShadowStyle, backgroundColor: 'rgba(0,0,0,0.35)', backdropFilter: 'blur(4px)' } : textShadowStyle}
          >
            <Activity size={14} />
            <span>Активность: {profile.activity_points ?? 0}</span>
          </div>

          {/* Friend action button — a new request only where the owner accepts them */}
          {!isOwnProfile && currentUserId && (friendshipStatus === 'accepted' || friendshipStatus === 'pending_sent' || friendshipStatus === 'pending_received' || canSendFriendRequest) && (
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
            permissions?.can_view_wall === false ? (
              <HiddenNotice text="Пользователь скрыл свою стену" />
            ) : (
              <WallSection
                profileUserId={profileUserId}
                isOwnProfile={isOwnProfile}
                canPost={isOwnProfile || canPostOnWall}
              />
            )
          )}
          {activeTab === 'characters' && (
            <CharactersSection profileUserId={profileUserId} />
          )}
          {activeTab === 'friends' && (
            permissions?.can_view_friends === false ? (
              <HiddenNotice text="Пользователь скрыл список друзей" />
            ) : (
              <FriendsSection
                profileUserId={profileUserId}
                isOwnProfile={isOwnProfile}
              />
            )
          )}
        </div>
      </div>

    </div>
  );
};

export default UserProfilePage;
