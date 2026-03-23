import { useEffect } from 'react';
import Header from '../../CommonComponents/Header/Header';
import Footer from '../../CommonComponents/Footer/Footer';
import { Outlet } from 'react-router-dom';
import { useWebSocket } from '../../../hooks/useWebSocket';
import ChatWidget from '../../Chat/ChatWidget';

const Layout = () => {
  useWebSocket();

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
    </>
  );
};

export default Layout;
