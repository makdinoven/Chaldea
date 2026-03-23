import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion } from 'motion/react';
import DOMPurify from 'dompurify';
import { fetchArticleBySlug, type ArchiveArticle } from '../../../api/archive';
import ArchiveLinkPreview from '../../CommonComponents/ArchiveLinkPreview/ArchiveLinkPreview';

const titleFont = "'MedievalSharp', 'Georgia', serif";
const bodyFont = "'Cormorant Garamond', 'Georgia', serif";

/* ---------- Greek letter decorative effects ---------- */

const GREEK_LETTERS = 'ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩαβγδεζηθικλμνξοπρστυφχψω';

const articleWatermarks = [
  { char: GREEK_LETTERS[7], x: '5%', y: '5%', size: '24px', rotate: -15, delay: '0s' },
  { char: GREEK_LETTERS[20], x: '88%', y: '8%', size: '20px', rotate: 12, delay: '1.5s' },
  { char: GREEK_LETTERS[3], x: '92%', y: '25%', size: '26px', rotate: -8, delay: '2.8s' },
  { char: GREEK_LETTERS[14], x: '3%', y: '30%', size: '22px', rotate: 18, delay: '0.6s' },
  { char: GREEK_LETTERS[23], x: '90%', y: '45%', size: '18px', rotate: -20, delay: '1.9s' },
  { char: GREEK_LETTERS[11], x: '4%', y: '55%', size: '24px', rotate: 10, delay: '3.2s' },
  { char: GREEK_LETTERS[18], x: '91%', y: '65%', size: '22px', rotate: -14, delay: '0.9s' },
  { char: GREEK_LETTERS[6], x: '5%', y: '75%', size: '20px', rotate: 22, delay: '2.4s' },
  { char: GREEK_LETTERS[15], x: '89%', y: '85%', size: '26px', rotate: -6, delay: '1.3s' },
  { char: GREEK_LETTERS[1], x: '6%', y: '92%', size: '18px', rotate: 16, delay: '3.6s' },
];

const articleMarginSymbols = [
  { char: 'Ω', y: '10%', side: 'left' as const, delay: '0s' },
  { char: 'Θ', y: '30%', side: 'right' as const, delay: '1.2s' },
  { char: 'Σ', y: '50%', side: 'left' as const, delay: '2.5s' },
  { char: 'Φ', y: '70%', side: 'right' as const, delay: '0.6s' },
  { char: 'Ψ', y: '90%', side: 'left' as const, delay: '1.8s' },
];

const ArticleGreekWatermarks = () => (
  <div className="absolute inset-0 pointer-events-none z-[2] overflow-hidden">
    {articleWatermarks.map((m, i) => (
      <span
        key={i}
        className="absolute select-none"
        style={{
          left: m.x,
          top: m.y,
          fontSize: m.size,
          fontFamily: "'Cormorant Garamond', serif",
          color: 'rgba(139,105,20,0.15)',
          transform: `rotate(${m.rotate}deg)`,
          animation: 'article-greek-breathe 6s ease-in-out infinite',
          animationDelay: m.delay,
        }}
      >
        {m.char}
      </span>
    ))}
    <style>{`
      @keyframes article-greek-breathe {
        0%, 100% { opacity: 0.25; }
        50% { opacity: 0.7; }
      }
    `}</style>
  </div>
);

const ArticleGreekMargin = () => (
  <div className="absolute inset-0 pointer-events-none z-[5] overflow-hidden">
    {articleMarginSymbols.map((r, i) => (
      <span
        key={i}
        className="absolute text-sm select-none"
        style={{
          top: r.y,
          [r.side]: '10px',
          fontFamily: "'Cormorant Garamond', serif",
          color: 'rgba(139,105,20,0.08)',
          textShadow: '0 0 6px rgba(180,150,60,0.12), 0 0 12px rgba(180,150,60,0.06)',
          animation: 'article-margin-pulse 5s ease-in-out infinite',
          animationDelay: r.delay,
        }}
      >
        {r.char}
      </span>
    ))}
    <style>{`
      @keyframes article-margin-pulse {
        0%, 100% {
          opacity: 0.15;
          text-shadow: 0 0 3px rgba(180,150,60,0.08);
        }
        50% {
          opacity: 0.75;
          text-shadow: 0 0 10px rgba(180,150,60,0.25), 0 0 20px rgba(160,140,80,0.12);
        }
      }
    `}</style>
  </div>
);

/* SVG clip-path for torn-edge parchment effect (simplified from Bestiary) */
const ParchmentDefs = () => (
  <svg className="absolute w-0 h-0" aria-hidden="true">
    <defs>
      <clipPath id="parchmentEdge" clipPathUnits="objectBoundingBox">
        <path
          d="M0,0 L0.995,0
             C0.992,0.03 0.998,0.06 0.994,0.1
             C0.99,0.14 0.997,0.18 0.993,0.22
             C0.989,0.26 0.996,0.3 0.992,0.34
             C0.988,0.38 0.997,0.42 0.993,0.46
             C0.989,0.5 0.996,0.54 0.992,0.58
             C0.988,0.62 0.997,0.66 0.993,0.7
             C0.989,0.74 0.996,0.78 0.992,0.82
             C0.988,0.86 0.997,0.9 0.993,0.94
             C0.989,0.97 0.996,0.99 0.993,1
             L0.007,1
             C0.01,0.97 0.004,0.93 0.008,0.9
             C0.012,0.86 0.003,0.82 0.007,0.78
             C0.011,0.74 0.004,0.7 0.008,0.66
             C0.012,0.62 0.003,0.58 0.007,0.54
             C0.011,0.5 0.004,0.46 0.008,0.42
             C0.012,0.38 0.003,0.34 0.007,0.3
             C0.011,0.26 0.004,0.22 0.008,0.18
             C0.012,0.14 0.003,0.1 0.007,0.06
             C0.011,0.03 0.004,0.01 0.007,0 Z"
        />
      </clipPath>
    </defs>
  </svg>
);

const ArchiveArticlePage = () => {
  const { slug } = useParams<{ slug: string }>();
  const [article, setArticle] = useState<ArchiveArticle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!slug) return;

    const loadArticle = async () => {
      setLoading(true);
      setError(null);
      setNotFound(false);
      try {
        const data = await fetchArticleBySlug(slug);
        setArticle(data);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Неизвестная ошибка';
        if (message.includes('404') || message.includes('Not Found') || message.includes('не найден')) {
          setNotFound(true);
        } else {
          setError(`Не удалось загрузить статью: ${message}`);
        }
      } finally {
        setLoading(false);
      }
    };
    loadArticle();
  }, [slug]);

  const sanitizeContent = (html: string) => {
    return DOMPurify.sanitize(html, {
      ADD_ATTR: ['data-archive-slug'],
    });
  };

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleDateString('ru-RU', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <div className="w-8 h-8 border-2 border-amber-700/30 border-t-amber-600 rounded-full animate-spin" />
      </div>
    );
  }

  // Not found state
  if (notFound) {
    return (
      <div className="max-w-3xl mx-auto text-center py-20">
        <h2
          className="text-2xl sm:text-3xl mb-4"
          style={{ fontFamily: titleFont, color: '#c9a84c' }}
        >
          Статья не найдена
        </h2>
        <p className="text-white/40 mb-6" style={{ fontFamily: bodyFont }}>
          Запрашиваемая страница архива не существует или была удалена.
        </p>
        <Link
          to="/archive"
          className="text-site-blue hover:text-white transition-colors text-sm"
        >
          &larr; Вернуться в Архив
        </Link>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="max-w-3xl mx-auto text-center py-20">
        <p className="text-site-red text-sm mb-4">{error}</p>
        <Link
          to="/archive"
          className="text-site-blue hover:text-white transition-colors text-sm"
        >
          &larr; Вернуться в Архив
        </Link>
      </div>
    );
  }

  if (!article) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="max-w-4xl mx-auto w-full"
    >
      <ParchmentDefs />

      {/* Back link */}
      <Link
        to="/archive"
        className="inline-flex items-center gap-1 text-sm text-white/40 hover:text-site-blue
                   transition-colors duration-200 mb-4"
      >
        &larr; Вернуться в Архив
      </Link>

      {/* Parchment container */}
      <div
        className="relative rounded-card overflow-hidden shadow-card"
        style={{ clipPath: 'url(#parchmentEdge)' }}
      >
        {/* Parchment base layer */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              'linear-gradient(170deg, #f5e6c8 0%, #e8d5a8 20%, #f0e0c0 40%, #e4d4b0 60%, #ecdcc0 80%, #f5e6c8 100%)',
          }}
        />

        {/* Paper texture */}
        <div
          className="absolute inset-0 pointer-events-none opacity-15 mix-blend-multiply"
          style={{
            backgroundImage: 'url(/textures/paper.png)',
            backgroundRepeat: 'repeat',
          }}
        />

        {/* Aged overlay */}
        <div
          className="absolute inset-0 pointer-events-none opacity-15 mix-blend-multiply"
          style={{
            backgroundImage: 'url(/textures/old-wall.png)',
            backgroundRepeat: 'repeat',
          }}
        />

        {/* Edge vignette */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            boxShadow:
              'inset 0 0 50px rgba(140,110,60,0.25), inset 0 0 100px rgba(120,90,40,0.1)',
          }}
        />

        {/* Greek letter decorative effects */}
        <ArticleGreekWatermarks />
        <ArticleGreekMargin />

        {/* Age spots */}
        <div
          className="absolute pointer-events-none w-28 h-24 top-[8%] left-[3%]"
          style={{
            background:
              'radial-gradient(ellipse, rgba(160,130,80,0.1) 0%, rgba(140,110,60,0.05) 40%, transparent 70%)',
            borderRadius: '50% 40% 60% 45% / 55% 45% 50% 40%',
          }}
        />
        <div
          className="absolute pointer-events-none w-32 h-28 top-[55%] right-[5%]"
          style={{
            background:
              'radial-gradient(ellipse, rgba(160,130,80,0.1) 0%, rgba(140,110,60,0.05) 40%, transparent 70%)',
            borderRadius: '45% 55% 50% 40% / 50% 45% 55% 40%',
          }}
        />

        {/* Content area */}
        <div className="relative z-[1] px-5 sm:px-10 md:px-16 py-8 sm:py-12 md:py-16">
          {/* Cover image */}
          {article.cover_image_url && (
            <div className="mb-6 sm:mb-8 -mx-2 sm:mx-0">
              <img
                src={article.cover_image_url}
                alt={article.title}
                className="w-full max-h-[300px] sm:max-h-[400px] object-cover rounded-lg"
                style={{
                  boxShadow: '0 4px 12px rgba(100,70,30,0.3)',
                }}
              />
            </div>
          )}

          {/* Title */}
          <h1
            className="text-2xl sm:text-3xl md:text-4xl tracking-wide mb-2"
            style={{
              fontFamily: titleFont,
              color: '#8b6914',
              textShadow: '0 1px 2px rgba(0,0,0,0.1)',
              lineHeight: 1.3,
            }}
          >
            {article.title}
          </h1>

          {/* Date */}
          <p
            className="text-xs sm:text-sm mb-6 sm:mb-8"
            style={{
              fontFamily: bodyFont,
              color: '#8a7a5a',
              fontStyle: 'italic',
            }}
          >
            {formatDate(article.created_at)}
          </p>

          {/* Ornamental divider */}
          <div className="flex justify-center mb-6 sm:mb-8">
            <div
              className="w-32 sm:w-48 h-px"
              style={{
                background:
                  'linear-gradient(90deg, transparent 0%, #8b6914 50%, transparent 100%)',
                opacity: 0.4,
              }}
            />
          </div>

          {/* Article content */}
          {article.content && (
            <ArchiveLinkPreview>
              <div
                className="prose-rules"
                style={{
                  fontFamily: bodyFont,
                  color: '#3a2e1a',
                  fontSize: '1.05rem',
                  lineHeight: 1.7,
                }}
                dangerouslySetInnerHTML={{
                  __html: sanitizeContent(article.content),
                }}
              />
            </ArchiveLinkPreview>
          )}

          {/* Bottom divider */}
          <div className="flex justify-center mt-8 sm:mt-10 mb-4">
            <div
              className="w-32 sm:w-48 h-px"
              style={{
                background:
                  'linear-gradient(90deg, transparent 0%, #8b6914 50%, transparent 100%)',
                opacity: 0.4,
              }}
            />
          </div>

          {/* Categories */}
          {article.categories.length > 0 && (
            <div className="flex flex-wrap gap-2 justify-center">
              {article.categories.map((cat) => (
                <Link
                  key={cat.id}
                  to={`/archive?category=${cat.slug}`}
                  className="text-xs sm:text-sm px-3 py-1 rounded-full transition-colors duration-200"
                  style={{
                    fontFamily: bodyFont,
                    background: 'rgba(139,105,20,0.12)',
                    color: '#6b5020',
                  }}
                >
                  {cat.name}
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Bottom back link */}
      <div className="mt-6 text-center">
        <Link
          to="/archive"
          className="inline-flex items-center gap-1 text-sm text-white/40 hover:text-site-blue
                     transition-colors duration-200"
        >
          &larr; Вернуться в Архив
        </Link>
      </div>
    </motion.div>
  );
};

export default ArchiveArticlePage;
