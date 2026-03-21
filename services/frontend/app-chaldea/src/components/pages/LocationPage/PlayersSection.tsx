import { Player } from './types';

interface PlayersSectionProps {
  players: Player[];
}

const PlayersSection = ({ players }: PlayersSectionProps) => {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="gold-text text-lg sm:text-xl font-medium uppercase">
        Игроки в локации
      </h2>

      {players.length === 0 ? (
        <p className="text-white/50 text-sm">На локации никого нет</p>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-3 sm:gap-4">
          {players.map((player) => (
            <div
              key={player.id}
              className="flex flex-col items-center gap-2 p-2 rounded-card hover:bg-white/5 transition-colors"
            >
              <div className="gold-outline relative w-12 h-12 rounded-full overflow-hidden bg-black/40 shrink-0">
                {player.avatar ? (
                  <img
                    src={player.avatar}
                    alt={player.name}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-white/20">
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                  </div>
                )}
              </div>
              <span className="text-white text-xs text-center truncate w-full">
                {player.name}
              </span>
              <span className="gold-text text-[10px] font-medium">
                LVL {player.level}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

export default PlayersSection;
