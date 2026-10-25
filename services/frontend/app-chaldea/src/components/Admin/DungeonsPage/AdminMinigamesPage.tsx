import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { ChallengeKind, ChallengeStart } from '../../../api/dungeons';
import ChallengeModal from '../../DungeonPage/minigames/ChallengeModal';
import {
  makeSketchChallenge,
  settleSketch,
  stepSketch,
  type SketchSecret,
} from '../../DungeonPage/minigames/sketchChallenges';

/*
  A testing ground for the class minigames (FEAT-176): every game one click
  away, in 3D or 2D. Offline — the games are made and settled in the browser
  by the server's rules; nothing is sent, nothing is spent.
*/

interface GameCard {
  kind: ChallengeKind;
  title: string;
  craft: string;
  about: string;
}

const GAMES: GameCard[] = [
  { kind: 'lockpick', title: 'Взлом замка', craft: 'Плут · ловкость', about: 'Поймать момент, когда штифт у линии среза.' },
  { kind: 'mechanism', title: 'Скрытый механизм', craft: 'Плут · ловкость', about: 'Найти рычаг в стене по расстояниям.' },
  { kind: 'scout', title: 'Разведка', craft: 'Плут · ловкость', about: 'Прокрасться по коридору в тени фонарей.' },
  { kind: 'disarm', title: 'Обезвредить ловушку', craft: 'Плут · ловкость', about: 'Перерезать свободные тяги, не тронув натянутых.' },
  { kind: 'search', title: 'Обыск комнаты', craft: 'Плут · ловкость', about: 'Пройти по следам под плитами к тайнику.' },
  { kind: 'illusion', title: 'Иллюзорная стена', craft: 'Маг · интеллект', about: 'Повторить порядок вспышек рун.' },
  { kind: 'seal', title: 'Магическая печать', craft: 'Маг · интеллект', about: 'Провести знак по отзывающимся кристаллам.' },
  { kind: 'insight', title: 'Распознать знаки', craft: 'Маг · интеллект', about: 'Свести сцепленные кольца звёздной карты.' },
  { kind: 'rubble', title: 'Завал', craft: 'Воин · сила', about: 'Вынуть камни, не тронув несущие.' },
  { kind: 'shield', title: 'Щит отряда', craft: 'Воин · сила', about: 'Повернуть щит навстречу каждой стреле.' },
  { kind: 'gate', title: 'Удержать решётку', craft: 'Воин · сила', about: 'Держать решётку в золотой полосе.' },
];

const AdminMinigamesPage = () => {
  const navigate = useNavigate();
  const [use3D, setUse3D] = useState(true);
  const [tryout, setTryout] = useState<ChallengeStart | null>(null);
  const secret = useRef<SketchSecret | null>(null);

  const start = (kind: ChallengeKind) => {
    const made = makeSketchChallenge(kind);
    secret.current = made.secret;
    setTryout(made.start);
  };

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-6">
      <div className="flex flex-col sm:flex-row sm:items-end gap-3">
        <div className="flex-1">
          <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">Мини-игры</h1>
          <p className="text-white/80 text-sm mt-1">
            Проба без забега: игры собираются и считаются прямо в браузере по правилам сервера. Ничего не отправляется
            и не тратится.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex rounded-card bg-black/40 p-1" role="group" aria-label="Вид игр">
            {[true, false].map((v) => (
              <button
                key={String(v)}
                type="button"
                onClick={() => setUse3D(v)}
                className={`px-4 py-1.5 rounded-card text-sm transition-colors duration-150 ease-site ${
                  use3D === v ? 'bg-white/10 text-white' : 'text-white/50 hover:text-white/80'
                }`}
              >
                {v ? '3D' : '2D'}
              </button>
            ))}
          </div>
          <button type="button" className="btn-line !text-sm !px-4 !py-1.5" onClick={() => navigate('/admin/dungeons')}>
            К подземельям
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {GAMES.map((g) => (
          <div key={g.kind} className="gray-bg rounded-card p-4 flex flex-col gap-2">
            <p className="gold-text text-base font-medium">{g.title}</p>
            <p className="text-white/50 text-xs uppercase tracking-[0.06em]">{g.craft}</p>
            <p className="text-white/70 text-sm flex-1">{g.about}</p>
            <button type="button" onClick={() => start(g.kind)} className="btn-blue !text-sm !py-2 mt-2">
              Запустить
            </button>
          </div>
        ))}
      </div>

      <ChallengeModal
        challenge={tryout}
        onFinish={async (presses, ended) => (tryout ? settleSketch(tryout, presses, ended) : null)}
        onStep={async (move) => (tryout && secret.current ? stepSketch(tryout, secret.current, move) : null)}
        onClose={() => setTryout(null)}
        use3D={use3D}
      />
    </div>
  );
};

export default AdminMinigamesPage;
