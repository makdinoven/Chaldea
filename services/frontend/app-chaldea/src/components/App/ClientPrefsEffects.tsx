import { useEffect, type ReactNode } from 'react';
import { MotionConfig } from 'motion/react';
import { useClientPrefs, type TextSizePref } from '../../utils/clientPrefs';

/** Root font size per setting; Tailwind's rem-based text scales with it. */
const ROOT_FONT_SIZE: Record<TextSizePref, string> = {
  normal: '',
  large: '112.5%',
  xlarge: '125%',
};

/**
 * Applies this browser's interface settings to the whole site: text size on
 * the root element, and with «Облегчённая графика» shortened CSS and motion
 * animations. The system's own «reduce motion» is honoured either way.
 */
const ClientPrefsEffects = ({ children }: { children: ReactNode }) => {
  const { textSize, graphics } = useClientPrefs();
  const lowGraphics = graphics === 'low';

  useEffect(() => {
    document.documentElement.style.fontSize = ROOT_FONT_SIZE[textSize];
  }, [textSize]);

  useEffect(() => {
    document.documentElement.classList.toggle('reduce-motion', lowGraphics);
  }, [lowGraphics]);

  return <MotionConfig reducedMotion={lowGraphics ? 'always' : 'user'}>{children}</MotionConfig>;
};

export default ClientPrefsEffects;
