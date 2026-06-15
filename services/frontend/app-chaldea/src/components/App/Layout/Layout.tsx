import { useEffect } from 'react';
import Header from '../../CommonComponents/Header/Header';
import Footer from '../../CommonComponents/Footer/Footer';
import { Outlet } from 'react-router-dom';
import { useWebSocket } from '../../../hooks/useWebSocket';
import { useAppSelector } from '../../../redux/store';
import ChatWidget from '../../Chat/ChatWidget';
import ConnectionStatus from '../../common/ConnectionStatus';

const Layout = () => {
  const { connected } = useWebSocket();
  const userId = useAppSelector((state) => state.user.id) as number | null;

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
