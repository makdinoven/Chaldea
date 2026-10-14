import { useEffect, useRef } from "react";

interface BattleLogEntry {
  id: string;
  timestamp: number;
  message: string;
  type: "damage" | "heal" | "buff" | "debuff" | "special" | "system";
  actor?: string;
  value?: number;
}

interface BattleLogProps {
  logs: BattleLogEntry[];
}

const getLogColor = (type: string) => {
  switch (type) {
    case "damage":
      return "text-red-400";
    case "heal":
      return "text-green-400";
    case "buff":
      return "text-blue-400";
    case "debuff":
      return "text-orange-400";
    case "special":
      return "text-purple-400";
    case "system":
      return "text-gray-400";
    default:
      return "text-white";
  }
};

const getLogIcon = (type: string) => {
  switch (type) {
    case "damage":
      return "⚔️";
    case "heal":
      return "💚";
    case "buff":
      return "✨";
    case "debuff":
      return "💔";
    case "special":
      return "⭐";
    case "system":
      return "ℹ️";
    default:
      return "•";
  }
};

const BattleLog = ({ logs }: BattleLogProps) => {
  const logContainerRef = useRef<HTMLDivElement>(null);

  // Автоскролл вниз при новых логах
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="absolute top-4 left-4 w-72 h-96 rounded-lg bg-black/70 border border-gold/30 backdrop-blur-sm shadow-lg overflow-hidden flex flex-col">
      {/* Заголовок */}
      <div className="px-4 py-2 border-b border-gold/30 bg-black/40">
        <p className="text-xs uppercase tracking-wider text-gold font-semibold">
          Логи боя
        </p>
      </div>

      {/* Логи */}
      <div
        ref={logContainerRef}
        className="flex-1 overflow-y-auto px-3 py-2 text-xs space-y-1"
      >
        {logs.length === 0 ? (
          <p className="text-gray-500 text-center py-4">Ожидание события...</p>
        ) : (
          logs.slice(-20).map((log) => (
            <div
              key={log.id}
              className={`${getLogColor(log.type)} font-mono flex items-start gap-2`}
            >
              <span className="text-lg flex-shrink-0 w-4 h-4 flex items-center justify-center">
                {getLogIcon(log.type)}
              </span>
              <span className="flex-1 break-words">{log.message}</span>
              {log.value !== undefined && (
                <span className="text-gold font-bold flex-shrink-0">
                  {log.value > 0 ? "+" : ""}{log.value}
                </span>
              )}
            </div>
          ))
        )}
      </div>

      {/* Индикатор прокрутки */}
      {logs.length > 20 && (
        <div className="px-3 py-1 text-[10px] text-gray-500 border-t border-gold/20 bg-black/40">
          Показаны последние 20 событий
        </div>
      )}
    </div>
  );
};

export default BattleLog;
