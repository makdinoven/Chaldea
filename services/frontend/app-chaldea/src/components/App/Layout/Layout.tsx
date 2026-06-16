import { useEffect, useRef } from 'react';
import Header from '../../CommonComponents/Header/Header';
import Footer from '../../CommonComponents/Footer/Footer';
import { Outlet } from 'react-router-dom';
import { useWebSocket } from '../../../hooks/useWebSocket';
import { useAppSelector, useAppDispatch } from '../../../redux/store';
import { fetchUnreadCount, selectTotalUnread } from '../../../redux/slices/messengerSlice';
import ChatWidget from '../../Chat/ChatWidget';
import ConnectionStatus from '../../common/ConnectionStatus';

const Layout = () => {
  const { connected } = useWebSocket();
  const dispatch = useAppDispatch();
  const userId = useAppSelector((state) => state.user.id) as number | null;
  const totalUnread = useAppSelector(selectTotalUnread);
  const baseTitleRef = useRef('');

  // For logged-in users: load the unread count and ask for notification permission.
  useEffect(() => {
    if (userId !== null) {
      dispatch(fetchUnreadCount());
      if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
        Notification.requestPermission().catch(() => {});
      }
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

  // Apply saved site background from localStorage on mount
  useEffect(() => {
    const savedBg = localStorage.getItem('site_bg_url');
    if (savedBg) {
      document.body.style.backgroundImage = `url(${savedBg})`;
    }
    return () => {
      document.body.style.backgroundImage = '';
    };
  }, []);

  return (
    <>
      <Header />
      <div className="relative z-0 max-w-[1240px] mx-auto px-5 mb-[100px]">
        <Outlet />
      </div>
      <Footer />
      <ChatWidget />
      {userId !== null && <ConnectionStatus connected={connected} />}
    </>
  );
};

export default Layout;
