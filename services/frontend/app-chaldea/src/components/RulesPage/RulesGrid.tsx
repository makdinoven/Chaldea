import { motion } from 'motion/react';
import { GameRule } from '../../api/rules';

interface RulesGridProps {
  rules: GameRule[];
  onSelect: (rule: GameRule) => void;
}

const RulesGrid = ({ rules, onSelect }: RulesGridProps) => (
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
          onClick={() => onSelect(rule)}
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
);

export default RulesGrid;
