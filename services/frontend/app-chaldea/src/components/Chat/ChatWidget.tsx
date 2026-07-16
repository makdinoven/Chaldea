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

  const handleClose = () => {
    dispatch(toggleChat());
  };

  return (
    <>
      {/* Overlay backdrop — click to close (per reference mock) */}
      <div
        onClick={handleClose}
        aria-hidden="true"
        className={`fixed inset-0 z-[70] bg-black/50 backdrop-blur-[2px]
          transition-opacity duration-300 ease-out
          ${isOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}`}
      />

      {/* Panel — slides in from the left; full width below md, 400px on desktop */}
      <div
        className={`fixed top-0 left-0 z-[80] h-screen w-full md:w-[400px] flex flex-col
          transition-transform duration-300 ease-out
          ${isOpen ? 'translate-x-0' : '-translate-x-full pointer-events-none'}`}
      >
        <ChatPanel
          isAuthenticated={isAuthenticated}
          isBanned={isBanned}
          onClose={handleClose}
        />
      </div>
    </>
  );
};

export default ChatWidget;
