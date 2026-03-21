import { useNavigate } from 'react-router-dom';
import { NeighborLocation } from './types';

interface NeighborsSectionProps {
  neighbors: NeighborLocation[];
}

const NeighborsSection = ({ neighbors }: NeighborsSectionProps) => {
  const navigate = useNavigate();

  if (neighbors.length === 0) return null;

  return (
    <section className="flex flex-col gap-4">
      <h2 className="gold-text text-lg sm:text-xl font-medium uppercase">
        Соседние локации
      </h2>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
        {neighbors.map((neighbor) => (
          <button
            key={neighbor.id}
            onClick={() => navigate(`/location/${neighbor.id}`)}
            className="group bg-black/30 rounded-card overflow-hidden hover:bg-black/50 transition-colors text-left"
          >
            {/* Image */}
            <div className="w-full aspect-[4/3] bg-black/40 overflow-hidden">
              {neighbor.image_url ? (
                <img
                  src={neighbor.image_url}
                  alt={neighbor.name}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-white/20">
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </div>
              )}
            </div>

            {/* Info */}
            <div className="p-2.5 sm:p-3 flex flex-col gap-1.5">
              <span className="text-white text-xs sm:text-sm font-medium truncate">
                {neighbor.name}
              </span>
              <div className="flex items-center justify-between gap-1">
                {neighbor.recommended_level > 0 && (
                  <span className="gold-text text-[10px] sm:text-xs">
                    {neighbor.recommended_level}+ LVL
                  </span>
                )}
                <span className="text-stat-energy text-[10px] sm:text-xs flex items-center gap-1">
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  {neighbor.energy_cost}
                </span>
              </div>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
};

export default NeighborsSection;
