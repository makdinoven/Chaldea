import { useEffect, useState } from 'react';
import { Link, Navigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import DOMPurify from 'dompurify';
import { fetchRule, GameRule } from '../../api/rules';
import ArchiveLinkPreview from '../CommonComponents/ArchiveLinkPreview/ArchiveLinkPreview';
import { GUIDE_SECTIONS } from '../../constants/guideSections';

// Подложка статьи — та же комбинация токенов дизайн-системы, что у панели профиля
// (ProfilePage/PanelShell). Компонент сознательно НЕ импортируется: его шапка —
// строка «иконка + мелкий заголовок», а здесь нужна обложка с картинкой и крупным
// заголовком. Фиксированной высоты и внутреннего скролла тут нет — статья
// скроллится страницей.
const PANEL_CLASS =
  'gold-outline relative rounded-card bg-site-bg backdrop-blur-[10px] shadow-card overflow-hidden';

const NOT_FOUND_MESSAGE = 'Правило не найдено';

interface RuleArticleProps {
  ruleId: number;
  sectionParam: string | undefined;
}

const RuleArticle = ({ ruleId, sectionParam }: RuleArticleProps) => {
  const [rule, setRule] = useState<GameRule | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    // Глобального ScrollToTop в приложении нет — иначе переход из длинного
    // списка оставил бы игрока в середине страницы.
    window.scrollTo(0, 0);

    let cancelled = false;

    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        setNotFound(false);
        const data = await fetchRule(ruleId);
        if (!cancelled) {
          setRule(data);
        }
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : 'Не удалось загрузить правило';
        if (message.includes('не найден')) {
          setNotFound(true);
        } else {
          setError(message);
          toast.error(message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    load();

    return () => {
      cancelled = true;
    };
  }, [ruleId]);

  if (loading) {
    return (
      <div className="w-full max-w-container mx-auto">
        <p className="text-white/60 text-base">Загрузка...</p>
      </div>
    );
  }

  if (notFound) {
    return <RuleNotFound />;
  }

  if (error || !rule) {
    return (
      <div className="w-full max-w-container mx-auto">
        <Link to="/guide" className="site-link text-sm inline-block mb-4">
          ← Руководство
        </Link>
        <p className="text-site-red text-base">{error || 'Не удалось загрузить правило'}</p>
      </div>
    );
  }

  // Чужой раздел в адресе (или раздел правила сменил админ) — ссылка не умирает,
  // адрес сам чинится каноническим видом. `replace`, чтобы «назад» не зацикливалось.
  if (rule.section !== sectionParam) {
    return <Navigate to={`/guide/${rule.section}/${rule.id}`} replace />;
  }

  const sectionMeta = GUIDE_SECTIONS.find((item) => item.slug === rule.section);
  const sectionLabel = sectionMeta ? sectionMeta.label : 'Руководство';
  const hasContent = Boolean(rule.content && rule.content.trim());

  return (
    <div className="w-full max-w-container mx-auto">
      <Link to={`/guide/${rule.section}`} className="site-link text-sm inline-block mb-4">
        ← {sectionLabel}
      </Link>

      <article className={PANEL_CLASS}>
        {rule.image_url ? (
          <div
            className="relative h-40 sm:h-56 md:h-64 bg-cover bg-center"
            style={{ backgroundImage: `url(${rule.image_url})` }}
          >
            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent" />
            <h1 className="absolute inset-x-0 bottom-0 px-5 py-4 sm:px-6 md:px-8 gold-text text-2xl sm:text-3xl font-medium uppercase break-words">
              {rule.title}
            </h1>
          </div>
        ) : (
          <div className="gradient-divider-h relative px-5 py-4 sm:px-6 md:px-8 bg-black/20">
            <h1 className="gold-text text-2xl sm:text-3xl font-medium uppercase break-words">
              {rule.title}
            </h1>
          </div>
        )}

        <div className="p-4 sm:p-6 md:p-8">
          {hasContent ? (
            <ArchiveLinkPreview>
              <div
                className="prose-rules text-white text-base leading-relaxed break-words"
                dangerouslySetInnerHTML={{
                  __html: DOMPurify.sanitize(rule.content || ''),
                }}
              />
            </ArchiveLinkPreview>
          ) : (
            <p className="text-white/60 text-base">В этом правиле пока нет текста</p>
          )}
        </div>
      </article>
    </div>
  );
};

const RuleNotFound = () => (
  <div className="w-full max-w-container mx-auto">
    <Link to="/guide" className="site-link text-sm inline-block mb-4">
      ← Руководство
    </Link>
    <p className="text-white/60 text-base">{NOT_FOUND_MESSAGE}</p>
  </div>
);

const GuideRulePage = () => {
  const { section, id } = useParams<{ section: string; id: string }>();

  // Нечисловой id — сеть не дёргаем вообще.
  const ruleId = id && /^\d+$/.test(id) ? Number(id) : null;

  if (ruleId === null || ruleId <= 0) {
    return <RuleNotFound />;
  }

  return <RuleArticle key={ruleId} ruleId={ruleId} sectionParam={section} />;
};

export default GuideRulePage;
