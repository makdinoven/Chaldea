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
    <section className="bg-black/60 rounded-card p-4 sm:p-6">
      <h2 className="gold-text text-lg sm:text-xl font-medium uppercase mb-3">
        Отряды здесь
      </h2>
      <div className="flex flex-col gap-3">
        {parties.map((p) => (
          <div key={p.id} className="flex items-center gap-3 bg-white/5 rounded-lg p-3">
            <div className="w-11 h-11 rounded-lg bg-white/5 border border-gold/20 flex items-center justify-center overflow-hidden shrink-0">
              {p.avatar ? (
                <img src={p.avatar} alt="" className="w-full h-full object-cover" />
              ) : (
                <span className="text-gold text-lg">⚔</span>
              )}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-white truncate">{p.name}</p>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {p.members.map((m) => (
                  <span
                    key={m.character_id}
                    className={`text-[11px] px-2 py-0.5 rounded-full ${
                      m.is_leader ? "bg-gold/20 text-gold" : "bg-white/10 text-white/70"
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
