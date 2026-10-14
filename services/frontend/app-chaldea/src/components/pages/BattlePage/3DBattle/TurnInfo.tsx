import { useEffect, useState } from "react";

interface TurnInfoProps {
  currentCharacterName: string;
  turnNumber: number;
  totalTurns: number;
  timeLeft: number; // в секундах
  isMyTurn: boolean;
  isAutoBattle: boolean;
  onToggleAutoBattle?: (enabled: boolean) => void;
  onMakeTurn?: () => void;
  energy?: number;
  maxEnergy?: number;
  isPaused?: boolean;
}

const TurnInfo = ({
  currentCharacterName,
  turnNumber,
  totalTurns,
  timeLeft,
  isMyTurn,
  isAutoBattle,
  onToggleAutoBattle,
  onMakeTurn,
  energy = 0,
  maxEnergy = 100,
  isPaused = false,
}: TurnInfoProps) => {
  const [displayTime, setDisplayTime] = useState(timeLeft);

  useEffect(() => {
    setDisplayTime(Math.max(0, Math.ceil(timeLeft)));
  }, [timeLeft]);

  const timeColor =
    displayTime <= 5 ? "text-red-400" : displayTime <= 10 ? "text-yellow-400" : "text-gold";

  return (
    <div className="absolute top-4 right-4 w-64 rounded-lg bg-black/70 border border-gold/30 backdrop-blur-sm shadow-lg overflow-hidden">
      {/* Заголовок */}
      <div className="px-4 py-2 border-b border-gold/30 bg-black/40">
        <p className="text-xs uppercase tracking-wider text-gold font-semibold">
          Информация хода
        </p>
      </div>

      {/* Содержимое */}
      <div className="px-4 py-3 space-y-3">
        {/* Текущий ход */}
        <div className="space-y-1">
          <p className="text-xs text-gray-400 uppercase tracking-wide">Ходит:</p>
          <p className={`text-lg font-bold ${isMyTurn ? "text-emerald-400" : "text-orange-400"}`}>
            {currentCharacterName}
          </p>
        </div>

        {/* Номер хода */}
        <div className="space-y-1">
          <p className="text-xs text-gray-400 uppercase tracking-wide">Ход / Всего:</p>
          <p className="text-base text-gold font-semibold">
            {turnNumber} / {totalTurns}
          </p>
        </div>

        {/* Время */}
        <div className="space-y-1">
          <p className="text-xs text-gray-400 uppercase tracking-wide">Осталось:</p>
          <div className={`text-3xl font-bold font-mono ${timeColor}`}>
            {displayTime}
            <span className="text-xs ml-1">сек</span>
          </div>
        </div>

        {/* Энергия */}
        {maxEnergy > 0 && (
          <div className="space-y-1">
            <p className="text-xs text-gray-400 uppercase tracking-wide">Энергия:</p>
            <div className="space-y-1">
              <p className="text-sm text-gold font-semibold">
                {energy} / {maxEnergy}
              </p>
              <div className="w-full h-2 rounded-full bg-gray-700 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-purple-400 to-purple-600 transition-all duration-200"
                  style={{ width: `${(energy / maxEnergy) * 100}%` }}
                />
              </div>
            </div>
          </div>
        )}

        {/* Статус автобоя */}
        <div className="flex items-center gap-2 py-2">
          <input
            type="checkbox"
            id="autobattle-toggle"
            checked={isAutoBattle}
            onChange={(e) => onToggleAutoBattle?.(e.target.checked)}
            className="w-4 h-4 cursor-pointer"
          />
          <label htmlFor="autobattle-toggle" className="text-sm text-gray-300 cursor-pointer">
            Автобой
          </label>
        </div>

        {/* Кнопка "Сделать ход" */}
        {isMyTurn && !isPaused && (
          <button
            onClick={onMakeTurn}
            className="w-full py-2 mt-2 rounded-md bg-gradient-to-r from-gold to-gold/70 hover:from-gold/90 hover:to-gold/60 text-black font-bold uppercase text-sm transition-all duration-200 active:scale-95"
          >
            Сделать ход
          </button>
        )}

        {/* Статус паузы */}
        {isPaused && (
          <div className="p-2 rounded-md bg-red-900/30 border border-red-500/50">
            <p className="text-xs text-red-400 font-semibold text-center">
              Бой приостановлен
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default TurnInfo;
