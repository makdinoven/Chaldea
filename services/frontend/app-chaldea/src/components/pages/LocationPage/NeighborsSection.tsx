import { useNavigate } from 'react-router-dom';
import { NeighborLocation } from './types';

interface NeighborsSectionProps {
  neighbors: NeighborLocation[];
}

/**
 * «Соседние локации» — inset panel living on the hero art, passed to
 * `LocationHeader` via its `aside` prop (FEAT-153 §3.2).
 *
 * Arrangement follows the mock: a 330px column stretched to the full hero body
 * height at `lg`, stacked full width below it; neighbours are horizontal rows
 * (thumbnail + name + level/energy + chevron), not image tiles. The collapse
 * toggle is gone — inside a fixed-height hero a collapsed panel would leave a
 * hole, so the header is static. Styling is design-system only.
 */
const NeighborsSection = ({ neighbors }: NeighborsSectionProps) => {
  const navigate = useNavigate();

  return (
    <aside className="w-full lg:w-[330px] lg:shrink-0 lg:self-stretch flex flex-col min-h-0 overflow-hidden rounded-card bg-site-bg backdrop-blur-sm border border-gold-dark/20 shadow-card">
      {/* Static header */}
      <div className="flex items-center gap-2.5 px-4 py-3.5 border-b border-white/[0.07] shrink-0">
        <svg xmlns="http://www.w3.org/2000/svg" className="w-[18px] h-[18px] text-gold shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 11l19-9-9 19-2-8-8-2z" />
        </svg>
        <h2 className="gold-text text-[13px] font-medium uppercase tracking-[0.08em]">
          Соседние локации
        </h2>
        {neighbors.length > 0 && (
          <span className="ml-auto bg-white/10 text-white/60 text-[10px] font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center shrink-0">
            {neighbors.length}
          </span>
        )}
      </div>

      {neighbors.length === 0 ? (
        <p className="flex-1 min-h-0 flex items-center justify-center p-5 text-white/50 text-sm text-center">
          Нет соседних локаций
        </p>
      ) : (
        <div className="flex-1 min-h-0 flex flex-col gap-2 p-3 max-h-[300px] lg:max-h-none overflow-y-auto gold-scrollbar">
          {neighbors.map((neighbor) => (
            <button
              key={neighbor.id}
              type="button"
              onClick={() => navigate(`/location/${neighbor.id}`)}
              className="group flex items-center gap-3 p-2 shrink-0 rounded-card text-left bg-white/[0.03] border border-white/[0.06] hover:border-gold-dark/40 hover:bg-white/[0.06] transition-all duration-200 ease-site"
            >
              {/* Thumbnail */}
              <span className="w-14 h-14 shrink-0 rounded-[10px] overflow-hidden bg-black/40 flex items-center justify-center">
                {neighbor.image_url ? (
                  <img
                    src={neighbor.image_url}
                    alt={neighbor.name}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  />
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6 text-white/20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                )}
              </span>

              {/* Info */}
              <span className="flex-1 min-w-0 flex flex-col gap-1.5">
                <span className="text-white text-[13px] font-medium truncate">
                  {neighbor.name}
                </span>
                <span className="flex items-center gap-3">
                  {neighbor.recommended_level > 0 && (
                    <span className="text-gold text-[11px] font-medium shrink-0">
                      {neighbor.recommended_level}+ LVL
                    </span>
                  )}
                  <span className="text-stat-energy text-[11px] flex items-center gap-1 shrink-0">
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.4}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    {neighbor.energy_cost}
                  </span>
                </span>
              </span>

              {/* Chevron */}
              <svg xmlns="http://www.w3.org/2000/svg" className="w-[15px] h-[15px] shrink-0 text-white/35 group-hover:text-site-blue transition-colors duration-200 ease-site" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 18l6-6-6-6" />
              </svg>
            </button>
          ))}
        </div>
      )}
    </aside>
  );
};

export default NeighborsSection;
