import { Link } from 'react-router-dom';
import type { ChatChannel } from '../../types/chat';

interface ChatHeaderProps {
  activeChannel: ChatChannel;
  onChannelChange: (channel: ChatChannel) => void;
  onClose: () => void;
}

const CHANNEL_LABELS: Record<ChatChannel, string> = {
  general: 'Общий',
  trade: 'Торговля',
  help: 'Помощь',
};

const CHANNELS: ChatChannel[] = ['general', 'trade', 'help'];

const ChatHeader = ({ activeChannel, onChannelChange, onClose }: ChatHeaderProps) => {
  return (
    <div className="flex items-center justify-between border-b border-white/10 px-3 py-2">
      <div className="flex gap-1">
        {CHANNELS.map((channel) => (
          <button
            key={channel}
            onClick={() => onChannelChange(channel)}
            className={`px-3 py-1.5 text-sm font-medium rounded-card transition-colors duration-200 ease-site cursor-pointer
              ${
                activeChannel === channel
                  ? 'gold-text bg-white/10'
                  : 'text-white/60 hover:text-white hover:bg-white/5'
              }`}
          >
            {CHANNEL_LABELS[channel]}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <Link
          to="/chat/history"
          className="text-xs text-site-blue hover:text-white transition-colors duration-200 ease-site"
        >
          История
        </Link>
        <button
          onClick={onClose}
          aria-label="Закрыть чат"
          className="w-8 h-8 flex items-center justify-center rounded-card cursor-pointer
            text-white/60 hover:text-gold hover:bg-white/5
            transition-colors duration-200 ease-site"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="w-4 h-4"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
    </div>
  );
};

export default ChatHeader;
