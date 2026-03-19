import { useEffect } from 'react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  toggleChat,
  selectChatIsOpen,
  selectChatIsBanned,
  checkBan,
} from '../../redux/slices/chatSlice';
import ChatPanel from './ChatPanel';

const ChatWidget = () => {
  const dispatch = useAppDispatch();
  const isOpen = useAppSelector(selectChatIsOpen);
  const isBanned = useAppSelector(selectChatIsBanned);
  const userId = useAppSelector((state) => state.user.id) as number | null;
  const isAuthenticated = userId !== null;

  useEffect(() => {
    if (isAuthenticated && userId) {
      dispatch(checkBan(userId));
    }
  }, [dispatch, isAuthenticated, userId]);

  const handleToggle = () => {
    dispatch(toggleChat());
  };

  return (
    <div className="fixed top-0 left-0 z-40 h-screen flex pointer-events-none">
      {/* Panel — uses negative margin to slide off-screen, CSS transition for smooth animation */}
      <div
        className={`h-full w-[85vw] sm:w-[360px] md:w-[400px] flex flex-col
          pointer-events-auto
          transition-[margin] duration-300 ease-out
          ${isOpen ? 'ml-0' : '-ml-[85vw] sm:-ml-[360px] md:-ml-[400px]'}`}
      >
        <ChatPanel isAuthenticated={isAuthenticated} isBanned={isBanned} />
      </div>

      {/* Tab button — always visible, glued to panel's right edge */}
      <button
        onClick={handleToggle}
        className="self-start mt-20 w-10 h-10 sm:w-11 sm:h-11
          flex items-center justify-center cursor-pointer flex-shrink-0
          pointer-events-auto
          bg-site-bg/90 backdrop-blur-sm border border-l-0 border-white/15
          rounded-r-lg shadow-card
          hover:bg-white/10 hover:border-gold/40
          transition-colors duration-200 ease-site"
        aria-label={isOpen ? 'Закрыть чат' : 'Открыть чат'}
      >
        {isOpen ? (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="w-5 h-5 text-gold"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        ) : (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="w-5 h-5 text-gold"
          >
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        )}
      </button>
    </div>
  );
};

export default ChatWidget;
