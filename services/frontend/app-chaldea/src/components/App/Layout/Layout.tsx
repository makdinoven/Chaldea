import { useCallback } from 'react';
import Header from '../../CommonComponents/Header/Header';
import Footer from '../../CommonComponents/Footer/Footer';
import { Outlet } from 'react-router-dom';
import { useSSE } from '../../../hooks/useSSE';
import { useChatSSE } from '../../../hooks/useChatSSE';
import { addNotification, NotificationItem } from '../../../redux/slices/notificationSlice';
import { useAppDispatch } from '../../../redux/store';
import toast from 'react-hot-toast';
import ChatWidget from '../../Chat/ChatWidget';

const Layout = () => {
  const dispatch = useAppDispatch();

  const handleSSEEvent = useCallback(
    (data: unknown) => {
      const notification = data as NotificationItem;
      dispatch(addNotification(notification));
      if (notification.message) {
        toast(notification.message);
      }
    },
    [dispatch],
  );

  useSSE('/notifications/stream', handleSSEEvent);

  // Chat SSE — connects only when auth token is present (checked inside the hook)
  useChatSSE();

  return (
    <>
      <Header />
      <div className="max-w-[1240px] mx-auto px-5 mb-[100px]">
        <Outlet />
      </div>
      <Footer />
      <ChatWidget />
    </>
  );
};

export default Layout;
