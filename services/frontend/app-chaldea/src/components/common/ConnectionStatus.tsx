import { useEffect, useState } from 'react';

interface ConnectionStatusProps {
  connected: boolean;
}

// Only surface the banner after the socket has been down for a moment, so a
// brief reconnect (e.g. a deploy restarting notification-service) doesn't flash.
const SHOW_DELAY_MS = 2500;

const ConnectionStatus = ({ connected }: ConnectionStatusProps) => {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (connected) {
      setVisible(false);
      return;
    }
    const timer = setTimeout(() => setVisible(true), SHOW_DELAY_MS);
    return () => clearTimeout(timer);
  }, [connected]);

  if (!visible) return null;

  return (
    <div
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50
        flex items-center gap-2
        bg-site-bg/95 backdrop-blur-sm border border-site-red/40
        text-white/80 text-xs rounded-full px-3 py-1.5 shadow-card"
      role="status"
    >
      <span className="w-3 h-3 border-2 border-white/30 border-t-white/80 rounded-full animate-spin" />
      Переподключение к серверу…
    </div>
  );
};

export default ConnectionStatus;
