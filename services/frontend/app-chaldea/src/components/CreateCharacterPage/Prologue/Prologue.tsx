import { motion } from 'motion/react';

/**
 * FEAT-154 (task #17) — the wizard's opening beat.
 *
 * A Coordinator of the Скитальцы meets the newcomer on the Цитадель and
 * explains, in three sentences, what the next five steps actually are: an
 * enrolment file, not a character sheet. Purely presentational — it holds no
 * data and blocks nothing.
 */

interface PrologueProps {
  /** Moves the player to step 1 («Кровь»). */
  onBegin: () => void;
}

const Prologue = ({ onBegin }: PrologueProps) => (
  <motion.section
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.35, ease: 'easeOut' }}
    className="w-full max-w-[720px] mx-auto px-4 sm:px-0 flex flex-col items-center gap-6 text-center"
  >
    <p className="text-white/50 text-xs uppercase tracking-[0.18em]">
      Цитадель · приёмная Скитальцев
    </p>

    <h3 className="gold-text text-xl sm:text-2xl font-medium uppercase">
      Координатор Скитальцев
    </h3>

    <div className="flex flex-col gap-4 text-white text-base leading-relaxed">
      <p>
        «Ветер донёс тебя до Цитадели — значит, дома тебя больше ничего не держит.
        Здесь не спрашивают, кем ты был; здесь записывают, кем ты станешь.»
      </p>
      <p>
        «Я задам шесть вопросов: кровь, родина, путь, имя, присяга и подпись под
        контрактом. Отвечай честно — реестр Скитальцев не любит переписываний.»
      </p>
      <p>
        «После этого ты получишь УР 1, номер мегалинка и место, откуда начнёшь.
        Дальше — только твоё дело.»
      </p>
    </div>

    <button type="button" onClick={onBegin} className="btn-blue">
      Начать регистрацию
    </button>
  </motion.section>
);

export default Prologue;
