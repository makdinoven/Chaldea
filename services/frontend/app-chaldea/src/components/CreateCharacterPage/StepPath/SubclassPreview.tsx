import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { motion } from 'motion/react';
import { fetchSubclasses, type Subclass } from '../../../api/subclasses';

/**
 * FEAT-154 (task #17) — rule 13.
 *
 * Shows where the chosen class can grow: its subclasses, read live from
 * `GET /skills/subclasses?class_id=…`. This is a PREVIEW — nothing is picked
 * here, the subclass is chosen much later in the game.
 */

interface SubclassPreviewProps {
  classId: number;
  className: string;
}

const SubclassPreview = ({ classId, className }: SubclassPreviewProps) => {
  const [subclasses, setSubclasses] = useState<Subclass[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openKey, setOpenKey] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchSubclasses(classId);
        if (!cancelled) setSubclasses(data);
      } catch (err) {
        if (cancelled) return;
        const message =
          err instanceof Error && err.message ? err.message : 'Не удалось загрузить подклассы.';
        setError(message);
        toast.error(message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [classId]);

  return (
    <section className="gray-bg rounded-card p-4 sm:p-6 flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h4 className="gold-text text-lg font-medium uppercase">Куда ведёт путь</h4>
        <p className="field-hint">
          Ветви развития класса «{className}». Выбирать сейчас ничего не нужно — это то, кем
          вы сможете стать позже.
        </p>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-white/50 text-sm">
          <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          <span>Загрузка подклассов…</span>
        </div>
      )}

      {error && !loading && <p className="text-site-red text-sm">{error}</p>}

      {!loading && !error && subclasses.length === 0 && (
        <p className="text-white/45 text-sm">Для этого класса подклассы ещё не заведены.</p>
      )}

      {subclasses.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {subclasses.map((subclass) => {
            const isOpen = openKey === subclass.key;
            return (
              <motion.button
                key={subclass.key}
                type="button"
                layout
                onClick={() => setOpenKey(isOpen ? null : subclass.key)}
                aria-expanded={isOpen}
                className="flex flex-col gap-1 p-3 rounded-card text-left bg-white/[0.04]
                  hover:bg-white/[0.08] transition-colors duration-200 ease-site"
              >
                <span className="text-white text-sm font-medium">{subclass.name}</span>
                <span
                  className={`text-white/55 text-xs leading-snug ${isOpen ? '' : 'line-clamp-2'}`}
                >
                  {subclass.description || 'Описание пока не заполнено.'}
                </span>
              </motion.button>
            );
          })}
        </div>
      )}
    </section>
  );
};

export default SubclassPreview;
