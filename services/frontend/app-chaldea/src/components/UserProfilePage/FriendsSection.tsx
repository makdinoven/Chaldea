import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { User, UserPlus, UserX, X, MessageSquare } from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  selectFriends,
  selectFriendsLoading,
  selectIncomingRequests,
  selectOutgoingRequests,
  selectUserProfile,
  acceptRequest,
  rejectRequest,
  removeFriendThunk,
  type Friend,
  type FriendRequest,
} from '../../redux/slices/userProfileSlice';
import { formatLastActive, isOnline } from '../../utils/formatLastActive';
import { buildColorEffectStyle } from './ProfileSettingsModal';

interface FriendsSectionProps {
  profileUserId: number;
  isOwnProfile: boolean;
}

const FriendCard = ({
  friend,
  isOwnProfile,
  profileUserId,
}: {
  friend: Friend;
  isOwnProfile: boolean;
  profileUserId: number;
}) => {
  const dispatch = useAppDispatch();

  const handleRemove = async () => {
    try {
      await dispatch(removeFriendThunk({ friendId: friend.id, userId: profileUserId })).unwrap();
      toast.success('Друг удалён');
    } catch {
      toast.error('Не удалось удалить друга');
    }
  };

  const online = isOnline(friend.last_active_at ?? null);
  const statusText = formatLastActive(friend.last_active_at ?? null);

  const handleMessage = () => {
    toast('Скоро будет доступно', { icon: '✉️' });
  };

  return (
    <div className="gray-bg p-4 flex items-center gap-3 group">
      <Link to={`/user-profile/${friend.id}`} className="flex-shrink-0 relative">
        <div className="w-12 h-12 rounded-full overflow-hidden bg-white/10 flex items-center justify-center">
          {friend.avatar ? (
            <img
              src={friend.avatar}
              alt={friend.username}
              className="w-full h-full object-cover"
            />
          ) : (
            <User size={20} className="text-white/40" />
          )}
        </div>
        {/* Online/offline indicator dot */}
        <span
          className={`absolute bottom-0 right-0 w-3 h-3 rounded-full ring-2 ring-white/20 ${
            online ? 'bg-green-500' : 'bg-gray-500'
          }`}
        />
      </Link>
      <div className="flex-1 min-w-0">
        <Link
          to={`/user-profile/${friend.id}`}
          className="text-white font-medium hover:text-site-blue transition-colors truncate block"
        >
          {friend.username}
        </Link>
        <span
          className={`text-xs ${
            online ? 'text-green-400' : 'text-white/40'
          }`}
        >
          {statusText}
        </span>
      </div>
      <div className="flex items-center gap-1">
        <button
          onClick={handleMessage}
          className="text-white/30 hover:text-site-blue transition-colors p-1"
          title="Написать сообщение"
        >
          <MessageSquare size={16} />
        </button>
        {isOwnProfile && (
          <button
            onClick={handleRemove}
            className="text-white/20 hover:text-site-red transition-colors opacity-0 group-hover:opacity-100 p-1"
            title="Удалить из друзей"
          >
            <UserX size={16} />
          </button>
        )}
      </div>
    </div>
  );
};

const IncomingRequestCard = ({
  request,
  profileUserId,
}: {
  request: FriendRequest;
  profileUserId: number;
}) => {
  const dispatch = useAppDispatch();

  const handleAccept = async () => {
    try {
      await dispatch(acceptRequest({ friendshipId: request.id, userId: profileUserId })).unwrap();
      toast.success(`${request.user.username} добавлен в друзья`);
    } catch {
      toast.error('Не удалось принять запрос');
    }
  };

  const handleReject = async () => {
    try {
      await dispatch(rejectRequest(request.id)).unwrap();
      toast.success('Запрос отклонён');
    } catch {
      toast.error('Не удалось отклонить запрос');
    }
  };

  return (
    <div className="gray-bg p-3 flex items-center gap-3">
      <Link to={`/user-profile/${request.user.id}`} className="flex-shrink-0">
        <div className="w-10 h-10 rounded-full overflow-hidden bg-white/10 flex items-center justify-center">
          {request.user.avatar ? (
            <img
              src={request.user.avatar}
              alt={request.user.username}
              className="w-full h-full object-cover"
            />
          ) : (
            <User size={16} className="text-white/40" />
          )}
        </div>
      </Link>
      <Link
        to={`/user-profile/${request.user.id}`}
        className="flex-1 text-white text-sm font-medium hover:text-site-blue transition-colors truncate"
      >
        {request.user.username}
      </Link>
      <div className="flex gap-1">
        <button
          onClick={handleAccept}
          className="p-1.5 text-white/50 hover:text-green-400 transition-colors"
          title="Принять"
        >
          <UserPlus size={16} />
        </button>
        <button
          onClick={handleReject}
          className="p-1.5 text-white/50 hover:text-site-red transition-colors"
          title="Отклонить"
        >
          <X size={16} />
        </button>
      </div>
    </div>
  );
};

const OutgoingRequestCard = ({ request }: { request: FriendRequest }) => {
  const dispatch = useAppDispatch();

  const handleCancel = async () => {
    try {
      await dispatch(rejectRequest(request.id)).unwrap();
      toast.success('Запрос отменён');
    } catch {
      toast.error('Не удалось отменить запрос');
    }
  };

  return (
    <div className="gray-bg p-3 flex items-center gap-3">
      <Link to={`/user-profile/${request.user.id}`} className="flex-shrink-0">
        <div className="w-10 h-10 rounded-full overflow-hidden bg-white/10 flex items-center justify-center">
          {request.user.avatar ? (
            <img
              src={request.user.avatar}
              alt={request.user.username}
              className="w-full h-full object-cover"
            />
          ) : (
            <User size={16} className="text-white/40" />
          )}
        </div>
      </Link>
      <Link
        to={`/user-profile/${request.user.id}`}
        className="flex-1 text-white text-sm font-medium hover:text-site-blue transition-colors truncate"
      >
        {request.user.username}
      </Link>
      <button
        onClick={handleCancel}
        className="p-1.5 text-white/30 hover:text-site-red transition-colors"
        title="Отменить запрос"
      >
        <X size={16} />
      </button>
    </div>
  );
};

const FriendsSection = ({ profileUserId, isOwnProfile }: FriendsSectionProps) => {
  const friends = useAppSelector(selectFriends);
  const friendsLoading = useAppSelector(selectFriendsLoading);
  const incomingRequests = useAppSelector(selectIncomingRequests);
  const outgoingRequests = useAppSelector(selectOutgoingRequests);
  const profile = useAppSelector(selectUserProfile);

  const postColor = profile?.post_color ?? '';
  const containerStyle = useMemo(() => {
    if (!postColor) return undefined;
    const style = buildColorEffectStyle(postColor, 'post_color', profile?.profile_style_settings);
    return { backgroundColor: style.backgroundColor } as React.CSSProperties;
  }, [postColor, profile?.profile_style_settings]);

  return (
    <div className={postColor ? 'rounded-card p-5 flex flex-col gap-6' : 'gray-bg p-5 flex flex-col gap-6'} style={containerStyle}>
      {/* Incoming requests (own profile only) */}
      {isOwnProfile && incomingRequests.length > 0 && (
        <div>
          <h3 className="gold-text text-sm font-medium uppercase mb-3">
            Входящие запросы ({incomingRequests.length})
          </h3>
          <div className="flex flex-col gap-2">
            {incomingRequests.map((req) => (
              <IncomingRequestCard
                key={req.id}
                request={req}
                profileUserId={profileUserId}
              />
            ))}
          </div>
        </div>
      )}

      {/* Outgoing requests (own profile only) */}
      {isOwnProfile && outgoingRequests.length > 0 && (
        <div>
          <h3 className="text-white/50 text-sm font-medium uppercase mb-3">
            Исходящие запросы ({outgoingRequests.length})
          </h3>
          <div className="flex flex-col gap-2">
            {outgoingRequests.map((req) => (
              <OutgoingRequestCard key={req.id} request={req} />
            ))}
          </div>
        </div>
      )}

      {/* Friends list */}
      <div>
        <h3 className="gold-text text-sm font-medium uppercase mb-3">
          Друзья ({friends.length})
        </h3>
        {friendsLoading ? (
          <div className="flex justify-center py-8">
            <div className="w-8 h-8 border-2 border-white/20 border-t-white rounded-full animate-spin" />
          </div>
        ) : friends.length === 0 ? (
          <p className="text-white/30 text-sm text-center py-8">
            {isOwnProfile ? 'У вас пока нет друзей' : 'Нет друзей'}
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {friends.map((friend) => (
              <FriendCard
                key={friend.id}
                friend={friend}
                isOwnProfile={isOwnProfile}
                profileUserId={profileUserId}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default FriendsSection;
