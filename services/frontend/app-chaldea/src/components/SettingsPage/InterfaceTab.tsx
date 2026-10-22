import { useMemo, useState } from 'react';
import {
  getSkillTreeViewPref,
  setClientPrefs,
  setSkillTreeViewPref,
  useClientPrefs,
  type BattleViewPref,
  type GraphicsPref,
  type SkillTreeViewPref,
  type TextSizePref,
} from '../../utils/clientPrefs';
import { isWebGLAvailable } from '../pages/BattlePage/Arena3D/webgl';
import { SettingsCard, ChoiceGroup, Toggle, type Option } from './SettingsControls';

const SKILL_TREE_OPTIONS: Option<SkillTreeViewPref>[] = [
  { value: 'auto', label: 'По устройству' },
  { value: 'books', label: 'Книги' },
  { value: 'wheel', label: 'Схема' },
];

const BATTLE_OPTIONS: Option<BattleViewPref>[] = [
  { value: '2d', label: '2D' },
  { value: '3d', label: '3D-стол' },
];

const GRAPHICS_OPTIONS: Option<GraphicsPref>[] = [
  { value: 'normal', label: 'Обычная' },
  { value: 'low', label: 'Облегчённая' },
];

const TEXT_SIZE_OPTIONS: Option<TextSizePref>[] = [
  { value: 'normal', label: 'Обычный' },
  { value: 'large', label: 'Крупный' },
  { value: 'xlarge', label: 'Очень крупный' },
];

/**
 * «Игра и интерфейс»: how the game is drawn on this device. Kept in the
 * browser, not the account — a phone and a computer want different things —
 * and applied the moment it is chosen.
 */
const InterfaceTab = () => {
  const prefs = useClientPrefs();
  const webgl = useMemo(() => isWebGLAvailable(), []);
  const [skillTreeView, setSkillTreeView] = useState<SkillTreeViewPref>(getSkillTreeViewPref);

  const noWebglHint = 'Ваше устройство не умеет рисовать 3D (нет WebGL), поэтому всегда показывается 2D.';

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 sm:gap-6 items-start">
      <SettingsCard title="Игра" description="Только для этого браузера — применяется сразу.">
        <ChoiceGroup
          label="Дерево навыков открывается"
          hint={
            webgl
              ? '«По устройству» — книги на компьютере, схема на телефоне.'
              : noWebglHint
          }
          options={SKILL_TREE_OPTIONS}
          value={skillTreeView}
          disabled={!webgl}
          onChange={(value) => {
            setSkillTreeView(value);
            setSkillTreeViewPref(value);
          }}
        />

        <ChoiceGroup
          label="Бой открывается"
          hint={webgl ? 'Переключиться можно и в самом бою.' : noWebglHint}
          options={BATTLE_OPTIONS}
          value={webgl ? prefs.battleView : '2d'}
          disabled={!webgl}
          onChange={(battleView) => setClientPrefs({ battleView })}
        />

        <Toggle
          label="Спрашивать перед необратимыми действиями"
          hint="Продажа торговцу, выброс и удаление предметов, выкуп лота на аукционе."
          checked={prefs.confirmDangerous}
          onChange={(confirmDangerous) => setClientPrefs({ confirmDangerous })}
        />
      </SettingsCard>

      <SettingsCard title="Интерфейс" description="Только для этого браузера — применяется сразу.">
        <ChoiceGroup
          label="Графика"
          hint="Облегчённая — для слабых устройств: 3D рисуется проще и без летающих частиц, анимации сайта почти мгновенные."
          options={GRAPHICS_OPTIONS}
          value={prefs.graphics}
          onChange={(graphics) => setClientPrefs({ graphics })}
        />

        <ChoiceGroup
          label="Размер текста"
          options={TEXT_SIZE_OPTIONS}
          value={prefs.textSize}
          onChange={(textSize) => setClientPrefs({ textSize })}
        />

        <p className="text-white/40 text-xs">
          Если в Windows, macOS или на телефоне выключены эффекты анимации, сайт тоже их не показывает.
        </p>
      </SettingsCard>
    </div>
  );
};

export default InterfaceTab;
