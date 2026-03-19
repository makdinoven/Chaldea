import Header from '../../CommonComponents/Header/Header';
import Footer from '../../CommonComponents/Footer/Footer';
import { Outlet } from 'react-router-dom';
import { useWebSocket } from '../../../hooks/useWebSocket';
import ChatWidget from '../../Chat/ChatWidget';

const Layout = () => {
  useWebSocket();

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
