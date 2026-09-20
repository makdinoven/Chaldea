import { useEffect, useState } from 'react';
import { Link, Navigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { fetchRules, GameRule } from '../../api/rules';
import RulesGrid from '../RulesPage/RulesGrid';
import { GUIDE_SECTIONS, GuideSection, isGuideSection } from '../../constants/guideSections';

interface GuideSectionContentProps {
  section: GuideSection;
}

const GuideSectionContent = ({ section }: GuideSectionContentProps) => {
  const [rules, setRules] = useState<GameRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const meta = GUIDE_SECTIONS.find((item) => item.slug === section);
  const title = meta ? meta.label : 'Руководство';

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await fetchRules(section);
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
  }, [section]);

  return (
    <div className="w-full max-w-container mx-auto">
      <Link to="/guide" className="site-link text-sm inline-block mb-4">
        ← Руководство
      </Link>

      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em] mb-8">
        {title}
      </h1>

      {loading && <p className="text-white/60 text-base">Загрузка...</p>}

      {!loading && error && <p className="text-site-red text-base">{error}</p>}

      {!loading && !error && (
        rules.length === 0 ? (
          <p className="text-white/60 text-base">В этом разделе пока нет материалов</p>
        ) : (
          <RulesGrid rules={rules} />
        )
      )}
    </div>
  );
};

const GuideSectionPage = () => {
  const { section } = useParams<{ section: string }>();

  if (!isGuideSection(section)) {
    return <Navigate to="/guide" replace />;
  }

  return <GuideSectionContent key={section} section={section} />;
};

export default GuideSectionPage;
