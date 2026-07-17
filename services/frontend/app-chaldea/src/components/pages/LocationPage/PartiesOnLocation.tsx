import { useEffect, useState } from "react";
import { getPartiesOnLocation, type PartyOnLocation } from "../../../api/squads";

interface PartiesOnLocationProps {
  locationId: number;
}

// Squads present on this location, each with only its co-located members
// (FEAT-144 Ф5). Hidden entirely when no squads are here.
const PartiesOnLocation = ({ locationId }: PartiesOnLocationProps) => {
  const [parties, setParties] = useState<PartyOnLocation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getPartiesOnLocation(locationId)
      .then((data) => {
        if (!cancelled) setParties(data);
      })
      .catch(() => {
        if (!cancelled) setParties([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [locationId]);

  if (loading || parties.length === 0) return null;

  return (
    <section className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 shadow-card overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2.5 px-4 sm:px-5 py-3.5 border-b border-white/[0.07]">
        <svg xmlns="http://www.w3.org/2000/svg" className="w-[18px] h-[18px] text-gold shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
          <circle cx="9" cy="7" r="4" strokeLinecap="round" strokeLinejoin="round" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M23 21v-2a4 4 0 00-3-3.87" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M16 3.13a4 4 0 010 7.75" />
        </svg>
        <h2 className="gold-text text-[13px] font-medium uppercase tracking-[0.08em]">
          Отряды здесь
        </h2>
        <span className="bg-white/10 text-white/60 text-[10px] font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">
          {parties.length}
        </span>
      </div>

      <div className="flex flex-col gap-2 p-3.5 sm:p-4">
        {parties.map((p) => (
          <div
            key={p.id}
            className="flex items-center gap-3 p-2.5 rounded-card bg-white/[0.03] border border-white/[0.06]"
          >
            <div className="w-11 h-11 rounded-[11px] bg-white/5 border border-gold/20 flex items-center justify-center overflow-hidden shrink-0">
              {p.avatar ? (
                <img src={p.avatar} alt="" className="w-full h-full object-cover" />
              ) : (
                <span className="text-gold text-lg">⚔</span>
              )}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-white text-[13px] font-medium truncate">{p.name}</p>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {p.members.map((m) => (
                  <span
                    key={m.character_id}
                    className={`text-[11px] px-2 py-0.5 rounded-full border ${
                      m.is_leader
                        ? "bg-gold/15 border-gold/25 text-gold"
                        : "bg-white/[0.07] border-white/10 text-white/70"
                    }`}
                  >
                    {m.name ?? `#${m.character_id}`}
                    {m.is_leader ? " ★" : ""}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};

export default PartiesOnLocation;
