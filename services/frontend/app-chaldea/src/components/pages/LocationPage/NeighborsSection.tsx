import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { NeighborLocation } from './types';

interface NeighborsSectionProps {
  neighbors: NeighborLocation[];
}

/**
 * «Соседние локации» — mock-style image cards in a 2-column grid
 * (FEAT-152 §3.5). Collapsible behavior kept (decision B15); the parent
 * dims this section via `actionsLocked` while in battle / gathering.
 */
const NeighborsSection = ({ neighbors }: NeighborsSectionProps) => {
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(true);

  return (
    <section className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 shadow-card overflow-hidden">
      {/* Collapsible header */}
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className={`w-full flex items-center gap-2.5 px-4 sm:px-5 py-3.5 cursor-pointer ${
          isOpen ? 'border-b border-white/[0.07]' : ''
        }`}
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="w-[18px] h-[18px] text-gold shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 11l19-9-9 19-2-8-8-2z" />
        </svg>
        <h2 className="gold-text text-[13px] font-medium uppercase tracking-[0.08em]">
          Соседние локации
        </h2>
        {neighbors.length > 0 && (
          <span className="bg-white/10 text-white/60 text-[10px] font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">
            {neighbors.length}
          </span>
        )}
        <svg
          className={`w-4 h-4 text-gold ml-auto shrink-0 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Collapsible content */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            className="overflow-hidden"
          >
            {neighbors.length === 0 ? (
              <p className="text-white/50 text-sm px-4 sm:px-5 pb-4">
                Нет соседних локаций
              </p>
            ) : (
              <div className="grid grid-cols-2 gap-2.5 px-3 sm:px-4 pb-4 pt-3 max-h-[320px] lg:max-h-[400px] overflow-y-auto gold-scrollbar content-start">
                {neighbors.map((neighbor) => (
                  <button
                    key={neighbor.id}
                    type="button"
                    onClick={() => navigate(`/location/${neighbor.id}`)}
                    className="group flex flex-col rounded-card overflow-hidden bg-white/[0.03] border border-white/[0.06] hover:border-gold-dark/40 hover:bg-white/[0.06] transition-all duration-200 ease-site text-left"
                  >
                    {/* Image */}
                    <div className="w-full h-[104px] bg-black/40 overflow-hidden shrink-0">
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
                    <div className="flex flex-col gap-1.5 p-2.5 pb-3">
                      <span className="text-white text-[13px] font-medium truncate">
                        {neighbor.name}
                      </span>
                      <div className="flex items-center justify-between gap-2">
                        {neighbor.recommended_level > 0 ? (
                          <span className="text-gold text-[11px] font-medium">
                            {neighbor.recommended_level}+ LVL
                          </span>
                        ) : (
                          <span />
                        )}
                        <span className="text-stat-energy text-[11px] flex items-center gap-1">
                          <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.4}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                          </svg>
                          {neighbor.energy_cost}
                        </span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
};

export default NeighborsSection;
