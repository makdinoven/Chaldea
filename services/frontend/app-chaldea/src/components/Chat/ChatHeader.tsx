import { Link } from 'react-router-dom';
import type { ChatChannel } from '../../types/chat';

interface ChatHeaderProps {
  activeChannel: ChatChannel;
  onChannelChange: (channel: ChatChannel) => void;
}

const CHANNEL_LABELS: Record<ChatChannel, string> = {
  general: 'Общий',
  trade: 'Торговля',
  help: 'Помощь',
};

const CHANNELS: ChatChannel[] = ['general', 'trade', 'help'];

const ChatHeader = ({ activeChannel, onChannelChange }: ChatHeaderProps) => {
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
      <Link
        to="/chat/history"
        className="text-xs text-site-blue hover:text-white transition-colors duration-200 ease-site"
      >
        История
      </Link>
    </div>
  );
};

export default ChatHeader;
