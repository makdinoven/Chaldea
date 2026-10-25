import { lazy, Suspense, useCallback, useRef, useState } from 'react';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import type {
  ChallengeResult,
  ChallengeStart,
  ChallengeStep,
  GateParams,
  LockpickParams,
  MechanismParams,
  RubbleParams,
  RunesParams,
  SealParams,
  SearchParams,
  ShadowParams,
  ShieldParams,
  StarsParams,
  WiresParams,
} from '../../../api/dungeons';
import LockpickGame from './LockpickGame';
import { OUTCOME_HOLD_MS } from './three/holds';
import RuneGame from './RuneGame';
import MechanismGame from './MechanismGame';
import RubbleGame from './RubbleGame';
import ShieldGame from './ShieldGame';
import GateGame from './GateGame';
import SealGame from './SealGame';
import SearchGame from './SearchGame';
import ShadowGame from './ShadowGame';
import WiresGame from './WiresGame';
import StarsGame from './StarsGame';

// The 3D games pull in three.js: loaded only when one is played.
const Lockpick3DGame = lazy(() => import('./Lockpick3DGame'));
const Rune3DGame = lazy(() => import('./Rune3DGame'));
const Mechanism3DGame = lazy(() => import('./Mechanism3DGame'));
const Rubble3DGame = lazy(() => import('./Rubble3DGame'));
const Shield3DGame = lazy(() => import('./Shield3DGame'));
const Gate3DGame = lazy(() => import('./Gate3DGame'));
const Seal3DGame = lazy(() => import('./Seal3DGame'));
const Search3DGame = lazy(() => import('./Search3DGame'));
const Shadow3DGame = lazy(() => import('./Shadow3DGame'));
const Wires3DGame = lazy(() => import('./Wires3DGame'));
const Stars3DGame = lazy(() => import('./Stars3DGame'));
/** A stepped game's last move shows this long before its outcome. */
const STEP_HOLD_MS = 700;
/** Games that have a 3D picture (the rest stay 2D everywhere). */
const GAMES_3D = new Set([
  'lockpick',
  'illusion',
  'mechanism',
  'rubble',
  'shield',
  'gate',
  'seal',
  'search',
  'scout',
  'disarm',
  'insight',
]);

/*
  A class challenge in its own window over the table: the game, then how it
  went. Closing it mid-game gives up (the server settles what was done).
*/

export const CHALLENGE_TITLES: Record<string, string> = {
  lockpick: 'Взлом замка',
  mechanism: 'Скрытый механизм',
  illusion: 'Иллюзорная стена',
  rubble: 'Завал',
  shield: 'Щит отряда',
  gate: 'Удержать проход',
  seal: 'Магическая печать',
  search: 'Обыск комнаты',
  scout: 'Разведка',
  disarm: 'Обезвредить ловушку',
  insight: 'Распознать знаки',
};

interface ChallengeModalProps {
  challenge: ChallengeStart | null;
  /** Sends what was done in a one-go game; the server's verdict comes back. `outcome` is the browser's view. */
  onFinish: (presses: number[], outcome?: string) => Promise<ChallengeResult | null>;
  /** One move of a game played with the server (the mechanism, the cave-in). */
  onStep?: (move: { x?: number; y?: number; index?: number }) => Promise<ChallengeStep | null>;
  onClose: () => void;
  /** Graphics to spare: the games that have one are drawn in 3D (same switch as the 3D dungeon). */
  use3D?: boolean;
}

const spinner = (
  <div className="flex justify-center py-8">
    <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
  </div>
);

const ChallengeModal = ({ challenge, onFinish, onStep, onClose, use3D = false }: ChallengeModalProps) => {
  const [result, setResult] = useState<ChallengeResult | null>(null);
  const shows3D = use3D && !!challenge && GAMES_3D.has(challenge.kind);
  const [sending, setSending] = useState(false);
  const sent = useRef(false);
  const latestPresses = useRef<number[]>([]);

  const settle = useCallback(
    async (presses: number[], outcome?: string) => {
      if (sent.current) return;
      sent.current = true;
      setSending(true);
      const verdict = await onFinish(presses, outcome);
      setSending(false);
      if (!verdict) {
        // The server could not settle it (the error is already shown): nothing left to play.
        sent.current = false;
        onClose();
        return;
      }
      setResult(verdict);
    },
    [onFinish, onClose],
  );

  /** A move of a stepped game; its last one carries the outcome. */
  const step = useCallback(
    async (move: { x?: number; y?: number; index?: number }) => {
      if (!onStep) return null;
      const answer = await onStep(move);
      if (answer?.result) {
        sent.current = true;
        // Let the last stone show (in 3D, the end play out) before the outcome covers the game.
        setTimeout(() => setResult(answer.result ?? null), shows3D ? OUTCOME_HOLD_MS : STEP_HOLD_MS);
      }
      return answer;
    },
    [onStep, shows3D],
  );

  const close = () => {
    // Walking away mid-game: give up with what has been done (the window is gone; nothing to show).
    if (!sent.current) void onFinish(latestPresses.current);
    sent.current = false;
    latestPresses.current = [];
    setResult(null);
    setSending(false);
    onClose();
  };

  const params = challenge?.params;
  const key = challenge?.challenge_id ?? '';
  const remember = (presses: number[]) => {
    latestPresses.current = presses;
  };

  const game = (() => {
    if (!challenge || !params) return null;
    switch (challenge.kind) {
      case 'lockpick':
        return use3D ? (
          <Suspense fallback={spinner}>
            <Lockpick3DGame
              key={key}
              params={params as LockpickParams}
              offClass={challenge.off_class}
              onDone={(presses, outcome) => void settle(presses, outcome)}
              onPress={remember}
            />
          </Suspense>
        ) : (
          <LockpickGame
            key={key}
            params={params as LockpickParams}
            offClass={challenge.off_class}
            onDone={(presses, outcome) => void settle(presses, outcome)}
            onPress={remember}
          />
        );
      case 'illusion':
        return use3D ? (
          <Suspense fallback={spinner}>
            <Rune3DGame
              key={key}
              params={params as RunesParams}
              offClass={challenge.off_class}
              onDone={(inputs, outcome) => void settle(inputs, outcome)}
              onPress={remember}
            />
          </Suspense>
        ) : (
          <RuneGame
            key={key}
            params={params as RunesParams}
            offClass={challenge.off_class}
            onDone={(inputs, outcome) => void settle(inputs, outcome)}
            onPress={remember}
          />
        );
      case 'shield':
        return use3D ? (
          <Suspense fallback={spinner}>
            <Shield3DGame
              key={key}
              params={params as ShieldParams}
              offClass={challenge.off_class}
              onDone={(presses, outcome) => void settle(presses, outcome)}
              onPress={remember}
            />
          </Suspense>
        ) : (
          <ShieldGame
            key={key}
            params={params as ShieldParams}
            offClass={challenge.off_class}
            onDone={(presses, outcome) => void settle(presses, outcome)}
            onPress={remember}
          />
        );
      case 'gate':
        return use3D ? (
          <Suspense fallback={spinner}>
            <Gate3DGame
              key={key}
              params={params as GateParams}
              offClass={challenge.off_class}
              onDone={(toggles, outcome) => void settle(toggles, outcome)}
              onPress={remember}
            />
          </Suspense>
        ) : (
          <GateGame
            key={key}
            params={params as GateParams}
            offClass={challenge.off_class}
            onDone={(toggles, outcome) => void settle(toggles, outcome)}
            onPress={remember}
          />
        );
      case 'seal':
        return use3D ? (
          <Suspense fallback={spinner}>
            <Seal3DGame key={key} params={params as SealParams} offClass={challenge.off_class} onStep={step} />
          </Suspense>
        ) : (
          <SealGame key={key} params={params as SealParams} offClass={challenge.off_class} onStep={step} />
        );
      case 'search':
        return use3D ? (
          <Suspense fallback={spinner}>
            <Search3DGame key={key} params={params as SearchParams} offClass={challenge.off_class} onStep={step} />
          </Suspense>
        ) : (
          <SearchGame key={key} params={params as SearchParams} offClass={challenge.off_class} onStep={step} />
        );
      case 'scout':
        return use3D ? (
          <Suspense fallback={spinner}>
            <Shadow3DGame
              key={key}
              params={params as ShadowParams}
              offClass={challenge.off_class}
              onDone={(steps, outcome) => void settle(steps, outcome)}
              onPress={remember}
            />
          </Suspense>
        ) : (
          <ShadowGame
            key={key}
            params={params as ShadowParams}
            offClass={challenge.off_class}
            onDone={(steps, outcome) => void settle(steps, outcome)}
            onPress={remember}
          />
        );
      case 'disarm':
        return use3D ? (
          <Suspense fallback={spinner}>
            <Wires3DGame key={key} params={params as WiresParams} offClass={challenge.off_class} onStep={step} />
          </Suspense>
        ) : (
          <WiresGame key={key} params={params as WiresParams} offClass={challenge.off_class} onStep={step} />
        );
      case 'insight':
        return use3D ? (
          <Suspense fallback={spinner}>
            <Stars3DGame
              key={key}
              params={params as StarsParams}
              offClass={challenge.off_class}
              onDone={(turns, outcome) => void settle(turns, outcome)}
              onPress={remember}
            />
          </Suspense>
        ) : (
          <StarsGame
            key={key}
            params={params as StarsParams}
            offClass={challenge.off_class}
            onDone={(turns, outcome) => void settle(turns, outcome)}
            onPress={remember}
          />
        );
      case 'mechanism':
        return use3D ? (
          <Suspense fallback={spinner}>
            <Mechanism3DGame key={key} params={params as MechanismParams} offClass={challenge.off_class} onStep={step} />
          </Suspense>
        ) : (
          <MechanismGame key={key} params={params as MechanismParams} offClass={challenge.off_class} onStep={step} />
        );
      case 'rubble':
        return use3D ? (
          <Suspense fallback={spinner}>
            <Rubble3DGame key={key} params={params as RubbleParams} offClass={challenge.off_class} onStep={step} />
          </Suspense>
        ) : (
          <RubbleGame key={key} params={params as RubbleParams} offClass={challenge.off_class} onStep={step} />
        );
      default:
        return null;
    }
  })();

  return (
    <ModalShell
      open={!!challenge && !!params}
      onClose={close}
      title={challenge ? CHALLENGE_TITLES[challenge.kind] ?? 'Испытание' : ''}
      size={shows3D ? 'lg' : 'sm'}
      closeOnBackdrop={false}
      dismissible={!sending}
    >
      {result ? (
        <div className="flex flex-col items-center gap-4 text-center py-2">
          <p className={`text-base ${result.passed ? 'gold-text' : 'text-site-red'}`}>{result.message}</p>
          <button type="button" onClick={close} className="btn-blue text-sm px-8 py-2 w-full sm:w-auto">
            {result.passed ? 'Дальше' : 'Закрыть'}
          </button>
        </div>
      ) : sending ? (
        spinner
      ) : (
        game
      )}
    </ModalShell>
  );
};

export default ChallengeModal;
