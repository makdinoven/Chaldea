import type { TicketMessageItem } from '../../types/ticket';

interface TicketMessageProps {
  message: TicketMessageItem;
  isOwn: boolean;
}

const formatTime = (dateStr: string): string => {
  try {
    const date = new Date(dateStr);
    const day = date.getDate().toString().padStart(2, '0');
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${day}.${month} ${hours}:${minutes}`;
  } catch {
    return '';
  }
};

const TicketMessage = ({ message, isOwn }: TicketMessageProps) => {
  return (
    <div className={`flex gap-3 px-3 py-2 ${isOwn ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div className="w-9 h-9 rounded-full overflow-hidden bg-white/10 flex-shrink-0">
        {message.sender_avatar ? (
          <img
            src={message.sender_avatar}
            alt={message.sender_username}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-white/40 text-sm font-medium">
            {message.sender_username.charAt(0).toUpperCase()}
          </div>
        )}
      </div>

      {/* Message content */}
      <div className={`flex flex-col max-w-[75%] ${isOwn ? 'items-end' : 'items-start'}`}>
        {/* Sender name + admin badge + time */}
        <div className={`flex items-baseline gap-2 mb-1 ${isOwn ? 'flex-row-reverse' : ''}`}>
          <span className={`text-xs font-medium truncate ${message.is_admin ? 'text-site-blue' : 'gold-text'}`}>
            {message.sender_username}
          </span>
          {message.is_admin && (
            <span className="text-[10px] font-medium uppercase tracking-wider bg-site-blue/20 text-site-blue px-1.5 py-0.5 rounded">
              Поддержка
            </span>
          )}
          <span className="text-white/30 text-xs flex-shrink-0">
            {formatTime(message.created_at)}
          </span>
        </div>

        {/* Bubble */}
        <div
          className={`px-3 py-2 inline-block max-w-full ${
            isOwn
              ? 'rounded-lg rounded-tr-none bg-site-blue/10 border border-site-blue/15'
              : message.is_admin
                ? 'rounded-lg rounded-tl-none bg-site-blue/[0.06] border border-site-blue/10'
                : 'rounded-lg rounded-tl-none bg-white/[0.06] border border-white/[0.08]'
          }`}
        >
          <p className="text-white text-sm break-words whitespace-pre-wrap">
            {message.content}
          </p>
        </div>

        {/* Attachment image */}
        {message.attachment_url && (
          <a
            href={message.attachment_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 block max-w-[280px] sm:max-w-[360px] rounded-lg overflow-hidden border border-white/10 hover:border-site-blue/30 transition-colors duration-200 ease-site"
          >
            <img
              src={message.attachment_url}
              alt="Вложение"
              className="w-full h-auto object-contain max-h-[300px]"
              loading="lazy"
            />
          </a>
        )}
      </div>
    </div>
  );
};

export default TicketMessage;
