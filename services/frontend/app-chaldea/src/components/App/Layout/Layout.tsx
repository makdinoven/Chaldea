import { useCallback } from 'react';
import Header from '../../CommonComponents/Header/Header';
import { Outlet } from 'react-router-dom';
import { useSSE } from '../../../hooks/useSSE';
import { addNotification, NotificationItem } from '../../../redux/slices/notificationSlice';
import { useAppDispatch } from '../../../redux/store';
import toast from 'react-hot-toast';

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

  return (
    <>
      <Header />
      <div className="max-w-[1240px] mx-auto px-5 mb-[100px]">
        <Outlet />
      </div>
    </>
  );
};

export default Layout;
