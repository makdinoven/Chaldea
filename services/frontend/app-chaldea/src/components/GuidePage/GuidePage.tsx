import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { GUIDE_SECTIONS } from '../../constants/guideSections';

const GuidePage = () => (
  <div className="w-full max-w-container mx-auto">
    <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em] mb-8">
      Руководство
    </h1>

    <motion.div
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6"
      initial="hidden"
      animate="visible"
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: 0.05 } },
      }}
    >
      {GUIDE_SECTIONS.map((section) => (
        <motion.div
          key={section.slug}
          variants={{
            hidden: { opacity: 0, y: 10 },
            visible: { opacity: 1, y: 0 },
          }}
        >
          <Link
            to={`/guide/${section.slug}`}
            className="block h-full gray-bg rounded-card shadow-card hover:shadow-hover
                       transition-shadow duration-200 p-6"
          >
            <h2 className="gold-text text-xl font-medium uppercase mb-2">
              {section.label}
            </h2>
            <p className="text-white/60 text-sm">{section.description}</p>
          </Link>
        </motion.div>
      ))}
    </motion.div>
  </div>
);

export default GuidePage;
