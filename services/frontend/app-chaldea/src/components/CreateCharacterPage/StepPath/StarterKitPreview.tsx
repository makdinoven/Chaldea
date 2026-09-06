import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { motion } from 'motion/react';
import { resolveStarterKit } from '../../../api/starterKits';
import { fetchItemsBulk, fetchSkillsBulk, indexById } from '../../../api/bulk';
import type { PassportKit, ResolvedItem, ResolvedSkill } from '../../CommonComponents/CharacterPassport';

/**
 * FEAT-154 (task #17) — rules 12, 12a-12c.
 *
 * The real starter kit for the pair (class × origin), resolved live:
 *   1. `GET /characters/starter-kits/resolve` → id-only contents
 *   2. `GET /inventory/items/bulk` ┐ in parallel — names, icons, rarity
 *   3. `GET /skills/bulk`          ┘
 * Exactly three requests, re-run whenever the class OR the origin changes, so
 * going back to «Родина» and picking another country really does change the kit.
 *
 * ⚠️ Note N17: `resolveStarterKit` omits `origin_id` when it is 0/null, so a
 * player who has not picked an origin is honestly told the kit is the class
 * default instead of being shown a country-specific label.
 */

/** Static map so Tailwind keeps the rarity classes (they are built dynamically). */
const RARITY_CLASS: Record<string, string> = {
  common: 'rarity-common',
  rare: 'rarity-rare',
  epic: 'rarity-epic',
  mythical: 'rarity-mythical',
  legendary: 'rarity-legendary',
};

interface StarterKitPreviewProps {
  classId: number;
  /** Chosen on step 2. `null` → the class default is shown. */
  originId: number | null;
  originName: string | null;
  /** Lets the wizard carry the preview into the passport on step 5. */
  onResolved?: (kit: PassportKit | null) => void;
}

const StarterKitPreview = ({
  classId,
  originId,
  originName,
  onResolved,
}: StarterKitPreviewProps) => {
  const [kit, setKit] = useState<PassportKit | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Kept in a ref so a caller passing an inline lambda cannot re-trigger the load.
  const onResolvedRef = useRef(onResolved);
  onResolvedRef.current = onResolved;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resolved = await resolveStarterKit(classId, originId);

      const [items, skills] = await Promise.all([
        fetchItemsBulk(resolved.items.map((line) => line.item_id)),
        fetchSkillsBulk(resolved.skills.map((line) => line.skill_id)),
      ]);

      const itemsById = indexById(items);
      const skillsById = indexById(skills);

      const resolvedItems: ResolvedItem[] = resolved.items.map((line) => {
        const found = itemsById.get(line.item_id);
        return {
          id: line.item_id,
          name: found?.name ?? `Предмет #${line.item_id}`,
          quantity: line.quantity,
          imageUrl: found?.image_url ?? null,
          rarity: found?.rarity ?? null,
        };
      });

      const resolvedSkills: ResolvedSkill[] = resolved.skills.map((line) => {
        const found = skillsById.get(line.skill_id);
        return {
          id: line.skill_id,
          name: found?.name ?? `Навык #${line.skill_id}`,
          iconUrl: found?.icon_url ?? null,
        };
      });

      const next: PassportKit = {
        items: resolvedItems,
        skills: resolvedSkills,
        currency: resolved.currency_amount,
        resolvedFrom: resolved.resolved_from,
      };

      setKit(next);
      onResolvedRef.current?.(next);
    } catch (err) {
      const message =
        err instanceof Error && err.message
          ? err.message
          : 'Не удалось загрузить стартовый набор.';
      setError(message);
      setKit(null);
      onResolvedRef.current?.(null);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [classId, originId]);

  // `load` is memoised on (classId, originId) — this re-runs exactly when the
  // player changes the class or goes back and picks another origin.
  useEffect(() => {
    load();
  }, [load]);

  const sourceNote = (() => {
    if (!kit) return null;
    if (kit.resolvedFrom === 'exact' && originName) {
      return `Набор собран специально для страны «${originName}».`;
    }
    if (kit.resolvedFrom === 'class_default') {
      return originName
        ? `Для страны «${originName}» отдельный набор не задан — выдан набор класса по умолчанию.`
        : 'Показан набор класса по умолчанию. Выберите родину — набор может измениться.';
    }
    return 'Для этого класса стартовый набор ещё не настроен — вы начнёте с пустыми руками.';
  })();

  const isEmptyKit =
    kit && kit.items.length === 0 && kit.skills.length === 0 && kit.currency === 0;

  return (
    <section className="gray-bg rounded-card p-4 sm:p-6 flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h4 className="gold-text text-lg font-medium uppercase">Что выдадут на складе</h4>
        {sourceNote && <p className="field-hint">{sourceNote}</p>}
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-white/50 text-sm">
          <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          <span>Собираем набор…</span>
        </div>
      )}

      {error && !loading && (
        <div className="flex flex-col items-start gap-3">
          <p className="text-site-red text-sm">{error}</p>
          <button type="button" className="btn-line" onClick={load}>
            Повторить
          </button>
        </div>
      )}

      {!loading && !error && isEmptyKit && (
        <p className="text-white/45 text-sm">
          Набор для этой пары «класс × родина» пуст. Это не ошибка регистрации — снаряжение
          можно будет купить в городе.
        </p>
      )}

      {!loading && !error && kit && !isEmptyKit && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          className="flex flex-col gap-5"
        >
          {kit.items.length > 0 && (
            <div className="flex flex-col gap-2">
              <span className="text-white/50 text-xs uppercase tracking-[0.08em]">Снаряжение</span>
              <div className="flex flex-wrap gap-4">
                {kit.items.map((item) => (
                  <div key={item.id} className="flex flex-col items-center gap-1 w-[84px]">
                    <div
                      className={`item-cell ${
                        item.rarity ? RARITY_CLASS[item.rarity] ?? '' : ''
                      } relative`}
                    >
                      {item.imageUrl ? (
                        <img
                          src={item.imageUrl}
                          alt={item.name}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <span className="text-white/30 text-xs">—</span>
                      )}
                      {item.quantity > 1 && (
                        <span className="absolute bottom-0 right-0 px-1 rounded bg-black/70 text-white text-[11px]">
                          ×{item.quantity}
                        </span>
                      )}
                    </div>
                    <span className="text-white text-[11px] text-center leading-tight break-words">
                      {item.name}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {kit.skills.length > 0 && (
            <div className="flex flex-col gap-2">
              <span className="text-white/50 text-xs uppercase tracking-[0.08em]">
                Стартовые навыки
              </span>
              <div className="flex flex-wrap gap-3">
                {kit.skills.map((skill) => (
                  <div
                    key={skill.id}
                    className="flex items-center gap-2 px-3 py-2 rounded-card bg-white/[0.04]"
                  >
                    {skill.iconUrl && (
                      <img
                        src={skill.iconUrl}
                        alt=""
                        className="w-8 h-8 rounded object-cover shrink-0"
                      />
                    )}
                    <span className="text-white text-sm">{skill.name}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {kit.currency > 0 && (
            <p className="text-white text-sm">
              Подъёмные:{' '}
              <span className="text-gold font-medium">{kit.currency}</span> монет.
            </p>
          )}
        </motion.div>
      )}
    </section>
  );
};

export default StarterKitPreview;
