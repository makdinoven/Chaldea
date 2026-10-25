import { useEffect, useRef } from 'react';
import Header from '../../CommonComponents/Header/Header';
import Footer from '../../CommonComponents/Footer/Footer';
import { Outlet } from 'react-router-dom';
import { useWebSocket } from '../../../hooks/useWebSocket';
import { useAppSelector, useAppDispatch } from '../../../redux/store';
import { fetchUnreadCount, selectTotalUnread } from '../../../redux/slices/messengerSlice';
import { selectSiteBackgroundUrl } from '../../../redux/slices/userSlice';
import { fetchNotificationPreferences } from '../../../redux/slices/notificationSlice';
import ChatWidget from '../../Chat/ChatWidget';
import ConnectionStatus from '../../common/ConnectionStatus';
import ActivityLockBanner from '../../CommonComponents/ActivityLockBanner';

const Layout = () => {
  const { connected } = useWebSocket();
  const dispatch = useAppDispatch();
  const userId = useAppSelector((state) => state.user.id) as number | null;
  const totalUnread = useAppSelector(selectTotalUnread);
  const baseTitleRef = useRef('');

  // For logged-in users: load the unread count and how they want to be notified.
  // System notifications are asked for from the settings page, not on arrival.
  useEffect(() => {
    if (userId !== null) {
      dispatch(fetchUnreadCount());
      dispatch(fetchNotificationPreferences());
    }
  }, [userId, dispatch]);

  // Reflect the unread message count in the browser tab title.
  useEffect(() => {
    if (!baseTitleRef.current) {
      baseTitleRef.current = document.title.replace(/^\(\d+\)\s*/, '') || 'Chaldea';
    }
    document.title = totalUnread > 0
      ? `(${totalUnread}) ${baseTitleRef.current}`
      : baseTitleRef.current;
  }, [totalUnread]);

  // The site background lives in the account; a background saved in this
  // browser before that (localStorage) still shows until the account has one.
  const accountBg = useAppSelector(selectSiteBackgroundUrl);
  useEffect(() => {
    const bg = accountBg ?? localStorage.getItem('site_bg_url');
    document.body.style.backgroundImage = bg ? `url(${bg})` : '';
    return () => {
      document.body.style.backgroundImage = '';
    };
  }, [accountBg]);

  return (
    <>
      <Header />
      <div className="relative z-0 max-w-container mx-auto px-5 mb-[100px]">
        {userId !== null && <ActivityLockBanner />}
        <Outlet />
      </div>
      <Footer />
      <ChatWidget />
      {userId !== null && <ConnectionStatus connected={connected} />}
    </>
  );
};

export default Layout;
