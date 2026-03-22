import { Link } from 'react-router-dom';
import { motion } from 'motion/react';

const CharactersHubPage = () => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col items-center gap-8 py-12 sm:py-20"
    >
      <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-wide text-center">
        Персонажи
      </h1>
      <p className="text-white/60 text-sm sm:text-base text-center max-w-md">
        Создайте нового персонажа или просмотрите все игровые роли
      </p>

      <div className="flex flex-col sm:flex-row gap-4 sm:gap-6 w-full max-w-lg">
        <Link
          to="/createCharacter"
          className="
            flex-1 flex flex-col items-center gap-3 p-6 sm:p-8
            bg-black/40 rounded-card border border-gold/30
            hover:bg-black/50 hover:border-gold/60
            transition-all duration-200 group
          "
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-10 h-10 sm:w-12 sm:h-12 text-gold/70 group-hover:text-gold transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
          </svg>
          <span className="gold-text text-base sm:text-lg font-medium uppercase tracking-wide">
            Создать персонажа
          </span>
          <span className="text-white/40 text-xs sm:text-sm text-center">
            Заполните анкету и отправьте на рассмотрение
          </span>
        </Link>

        <Link
          to="/characters/list"
          className="
            flex-1 flex flex-col items-center gap-3 p-6 sm:p-8
            bg-black/40 rounded-card border border-white/20
            hover:bg-black/50 hover:border-white/40
            transition-all duration-200 group
          "
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-10 h-10 sm:w-12 sm:h-12 text-white/50 group-hover:text-white/80 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
          </svg>
          <span className="text-white text-base sm:text-lg font-medium uppercase tracking-wide">
            Все персонажи
          </span>
          <span className="text-white/40 text-xs sm:text-sm text-center">
            Просмотр всех игровых ролей
          </span>
        </Link>
      </div>
    </motion.div>
  );
};

export default CharactersHubPage;
