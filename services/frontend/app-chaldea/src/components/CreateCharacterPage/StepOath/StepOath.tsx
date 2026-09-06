import type { StartingPoint } from '../../../api/startingPoints';
import LawsOfTheOrder from './LawsOfTheOrder';
import StartingPointPicker from './StartingPointPicker';

/**
 * FEAT-154 — step 5, «Присяга».
 *
 * Split out of «Контракт»: the posting and the law of the organisation are what
 * the player has to *read and decide on*, while the passport is what he checks
 * and signs. On one page the two fought for attention and the law lost — the
 * passport is the eye-catching part of that screen.
 *
 * Nothing here blocks the way forward: the point of first assignment is
 * optional on the wire and a default is assigned at approval (§3.6), and the
 * law is read, not filled in. The step is still a real step — it is where the
 * terms are stated before the signature on step 6.
 */

interface StepOathProps {
  startLocation: StartingPoint | null;
  onSelectStartLocation: (point: StartingPoint | null) => void;
}

const StepOath = ({ startLocation, onSelectStartLocation }: StepOathProps) => (
  <div className="w-full flex flex-col gap-8 px-4 md:px-[60px]">
    {/* Point of first assignment (rules 19-20) */}
    <section className="flex flex-col gap-3">
      <h3 className="gold-text text-lg sm:text-xl font-semibold">Точка первого назначения</h3>
      <p className="field-hint max-w-[720px]">
        Координатор отправит вас туда, где вы сойдёте на берег впервые. Список утверждён
        организацией — позже мир открыт целиком. Можно ничего не выбирать: тогда точку
        назначит Координатор при одобрении заявки.
      </p>
      <StartingPointPicker
        selectedId={startLocation?.id ?? null}
        onSelect={onSelectStartLocation}
      />
    </section>

    {/* What the player signs up to — the offences and what they cost (rule 26) */}
    <section className="flex flex-col gap-3">
      <h3 className="gold-text text-lg sm:text-xl font-semibold">Устав организации</h3>
      <p className="field-hint field-hint-strong max-w-[720px]">
        Прочтите, за что Скитальцы исключают и что означают Анафема и Домнацио Мемориае.
        Подписав контракт, вы соглашаетесь с этим правом — незнание от него не избавляет.
      </p>
      <LawsOfTheOrder />
    </section>
  </div>
);

export default StepOath;
