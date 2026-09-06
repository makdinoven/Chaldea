import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import ClassCard from './ClassCard';
import SubclassPreview from './SubclassPreview';
import StarterKitPreview from './StarterKitPreview';
import { fetchClasses, type GameClass } from '../../../api/characterRequests';
import type { PassportKit } from '../../CommonComponents/CharacterPassport';

/**
 * FEAT-154 (task #17) — step 3, «Путь». Replaces `ClassPage.jsx` and the mock
 * `INITIAL_CLASSES` entirely: classes come from `GET /characters/classes`, the
 * subclasses from skills-service and the starter kit from the resolver for the
 * pair (class × origin chosen on step 2).
 */

interface StepPathProps {
  selectedClassId: number | null;
  /** The name is handed up too, so the wizard does not have to re-fetch classes. */
  onSelectClass: (classId: number, className: string) => void;
  /** Origin picked on step 2 — the second half of the starter-kit key. */
  selectedOriginId: number | null;
  selectedOriginName: string | null;
  /** Lets the wizard carry the kit preview into the passport on step 5. */
  onKitResolved?: (kit: PassportKit | null) => void;
}

const StepPath = ({
  selectedClassId,
  onSelectClass,
  selectedOriginId,
  selectedOriginName,
  onKitResolved,
}: StepPathProps) => {
  const [classes, setClasses] = useState<GameClass[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchClasses();
        if (!cancelled) setClasses(data);
      } catch (err) {
        if (cancelled) return;
        const message =
          err instanceof Error && err.message ? err.message : 'Не удалось загрузить классы.';
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
  }, []);

  const selectedClass = classes.find((item) => item.id_class === selectedClassId) ?? null;

  if (loading && classes.length === 0) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-10 h-10 border-4 border-white/30 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  if (error && classes.length === 0) {
    return (
      <p className="text-site-red text-sm text-center py-10 px-4">{error}</p>
    );
  }

  if (classes.length === 0) {
    return (
      <p className="text-white/60 text-sm text-center py-10">
        Список классов пуст. Обратитесь к администрации.
      </p>
    );
  }

  return (
    <div className="w-full flex flex-col gap-6 px-4 md:px-[60px]">
      <p className="field-hint max-w-[720px]">
        Класс определяет, чем вы решаете задачи, и какое снаряжение выдаст склад Цитадели.
        Подкласс выбирать сейчас не нужно — это дело будущего.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {classes.map((gameClass) => (
          <ClassCard
            key={gameClass.id_class}
            gameClass={gameClass}
            isSelected={gameClass.id_class === selectedClassId}
            onSelect={(classId) => onSelectClass(classId, gameClass.name)}
          />
        ))}
      </div>

      {selectedClass ? (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <SubclassPreview classId={selectedClass.id_class} className={selectedClass.name} />
          <StarterKitPreview
            classId={selectedClass.id_class}
            originId={selectedOriginId}
            originName={selectedOriginName}
            onResolved={onKitResolved}
          />
        </div>
      ) : (
        <div className="gray-bg rounded-card p-6">
          <p className="text-white/50 text-sm text-center">
            Выберите класс — тогда станут видны ветви развития и стартовый набор.
          </p>
        </div>
      )}
    </div>
  );
};

export default StepPath;
