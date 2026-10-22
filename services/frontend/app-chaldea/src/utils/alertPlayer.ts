import toast from 'react-hot-toast';
import { getClientPrefs } from './clientPrefs';
import { playSound, type SoundKind } from './notifySound';

/*
  One way to tell the player something happened: a popup, a sound and — when
  the tab is in the background and they allowed it — a system notification.
  Whether each of those happens follows the player's settings: `silent` comes
  from the server when they chose «только колокольчик» for that kind.
*/

export interface AlertOptions {
  text: string;
  /** Heading of the system notification; the site name when absent. */
  title?: string;
  tone?: 'default' | 'success' | 'error';
  duration?: number;
  sound?: SoundKind;
  /** Quiet delivery: the bell only, no popup, sound or system notification. */
  silent?: boolean;
  /** Skip the popup but still sound and notify (e.g. a private message). */
  noToast?: boolean;
}

const SITE_NAME = 'Fall of Gods';

/** A system notification, only while the player is looking at another tab or window. */
export const showBrowserNotification = (title: string, body: string) => {
  if (typeof document === 'undefined' || !document.hidden) return;
  if (!getClientPrefs().browserNotifications) return;
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
  try {
    const notification = new Notification(title, { body, icon: '/favicon.ico' });
    notification.onclick = () => {
      window.focus();
      notification.close();
    };
  } catch {
    // Best effort — some browsers only allow notifications from a service worker.
  }
};

export const alertPlayer = ({
  text,
  title,
  tone = 'default',
  duration,
  sound = 'notification',
  silent = false,
  noToast = false,
}: AlertOptions) => {
  if (silent) return;
  if (!noToast) {
    const options = duration ? { duration } : undefined;
    if (tone === 'success') toast.success(text, options);
    else if (tone === 'error') toast.error(text, options);
    else toast(text, options);
  }
  playSound(sound);
  showBrowserNotification(title ?? SITE_NAME, text);
};
