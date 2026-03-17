import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { fetchRules, GameRule } from '../../api/rules';
import RuleOverlay from './RuleOverlay';

const RulesPage = () => {
  const [rules, setRules] = useState<GameRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRule, setSelectedRule] = useState<GameRule | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await fetchRules();
        setRules(data);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Не удалось загрузить правила';
        setError(message);
        toast.error(message);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) {
    return (
      <div className="w-full max-w-[1240px] mx-auto">
        <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em] mb-8">
          Правила
        </h1>
        <p className="text-white/60 text-base">Загрузка...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full max-w-[1240px] mx-auto">
        <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em] mb-8">
          Правила
        </h1>
        <p className="text-site-red text-base">{error}</p>
      </div>
    );
  }

  return (
    <div className="w-full max-w-[1240px] mx-auto">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em] mb-8">
        Правила
      </h1>

      {rules.length === 0 ? (
        <p className="text-white/60 text-base">Правила пока не добавлены</p>
      ) : (
        <motion.div
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6"
          initial="hidden"
          animate="visible"
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.05 } },
          }}
        >
          {rules.map((rule) => (
            <motion.div
              key={rule.id}
              variants={{
                hidden: { opacity: 0, y: 10 },
                visible: { opacity: 1, y: 0 },
              }}
            >
              <button
                onClick={() => setSelectedRule(rule)}
                className="w-full text-left image-card rounded-card shadow-card hover:shadow-hover
                           transition-shadow duration-200 cursor-pointer
                           aspect-[16/9] relative overflow-hidden group"
                style={{
                  backgroundImage: rule.image_url
                    ? `url(${rule.image_url})`
                    : undefined,
                }}
              >
                {/* Dark gradient overlay */}
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-transparent" />

                {/* Title */}
                <div className="absolute inset-0 flex items-center justify-center p-4">
                  <h3 className="gold-text text-xl font-medium uppercase text-center relative z-10">
                    {rule.title}
                  </h3>
                </div>
              </button>
            </motion.div>
          ))}
        </motion.div>
      )}

      <RuleOverlay rule={selectedRule} onClose={() => setSelectedRule(null)} />
    </div>
  );
};

export default RulesPage;
