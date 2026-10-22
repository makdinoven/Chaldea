import { useSyncExternalStore } from 'react';
import type { SoundKind } from './notifySound';

/*
  Sounds the player picked themselves, kept in this browser's IndexedDB (the
  rest of «Звук и система» is per browser too). The original file is stored
  as is; playback cuts it at MAX_SOUND_SECONDS with a short fade, so nothing
  has to be re-encoded here.
*/

export const MAX_SOUND_BYTES = 500 * 1024;
export const MAX_SOUND_SECONDS = 5;
const ACCEPTED_EXTENSIONS = ['mp3', 'ogg', 'oga', 'wav'];
export const ACCEPTED_SOUND_TYPES = '.mp3,.ogg,.oga,.wav,audio/mpeg,audio/ogg,audio/wav';

const DB_NAME = 'chaldea-sounds';
const STORE = 'sounds';

interface StoredSound {
  kind: SoundKind;
  name: string;
  data: ArrayBuffer;
}

/** What the settings page shows for a sound slot. */
export interface CustomSoundInfo {
  name: string;
  /** Seconds, already capped at MAX_SOUND_SECONDS. */
  duration: number;
}

const openDb = (): Promise<IDBDatabase> =>
  new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('no indexedDB'));
      return;
    }
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: 'kind' });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });

const withStore = async <T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> => {
  const db = await openDb();
  try {
    return await new Promise<T>((resolve, reject) => {
      const request = run(db.transaction(STORE, mode).objectStore(STORE));
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  } finally {
    db.close();
  }
};

/* Decoded buffers live in memory once loaded; the info map feeds the settings page. */

const buffers = new Map<SoundKind, AudioBuffer>();
let info: Partial<Record<SoundKind, CustomSoundInfo>> = {};
let loaded: Promise<void> | null = null;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((listener) => listener());

let decodeContext: AudioContext | null = null;
const decode = (data: ArrayBuffer): Promise<AudioBuffer> => {
  if (!decodeContext) {
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    decodeContext = new Ctor();
  }
  // decodeAudioData detaches the buffer it is given; keep the stored copy intact.
  return decodeContext.decodeAudioData(data.slice(0));
};

const remember = (kind: SoundKind, name: string, buffer: AudioBuffer) => {
  buffers.set(kind, buffer);
  info = { ...info, [kind]: { name, duration: Math.min(buffer.duration, MAX_SOUND_SECONDS) } };
};

/** Loads every stored sound once per page; later calls wait for the same load. */
export const loadCustomSounds = (): Promise<void> => {
  if (!loaded) {
    loaded = (async () => {
      try {
        const all = await withStore<StoredSound[]>('readonly', (store) => store.getAll() as IDBRequest<StoredSound[]>);
        for (const sound of all) {
          try {
            remember(sound.kind, sound.name, await decode(sound.data));
          } catch {
            // A file the browser can no longer decode is skipped; the standard sound plays.
          }
        }
        emit();
      } catch {
        // No IndexedDB (private mode, blocked storage): only the standard sounds.
      }
    })();
  }
  return loaded;
};

export const getCustomSoundBuffer = (kind: SoundKind): AudioBuffer | undefined => buffers.get(kind);

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export const useCustomSounds = () => useSyncExternalStore(subscribe, () => info);

const extensionOf = (name: string) => name.split('.').pop()?.toLowerCase() ?? '';

/** Checks, decodes and stores a file for a slot. Throws a Russian message the page can show as is. */
export const saveCustomSound = async (kind: SoundKind, file: File): Promise<void> => {
  if (!ACCEPTED_EXTENSIONS.includes(extensionOf(file.name)) && !file.type.startsWith('audio/')) {
    throw new Error('Подходят только файлы mp3, ogg или wav');
  }
  if (file.size > MAX_SOUND_BYTES) {
    throw new Error('Файл больше 500 КБ — выберите звук покороче или сожмите его');
  }
  const data = await file.arrayBuffer();
  let buffer: AudioBuffer;
  try {
    buffer = await decode(data);
  } catch {
    throw new Error('Браузер не смог прочитать этот файл как звук');
  }
  try {
    await withStore('readwrite', (store) => store.put({ kind, name: file.name, data } satisfies StoredSound));
  } catch {
    throw new Error('Браузер не даёт сохранить файл — возможно, включён приватный режим');
  }
  remember(kind, file.name, buffer);
  emit();
};

export const removeCustomSound = async (kind: SoundKind): Promise<void> => {
  try {
    await withStore('readwrite', (store) => store.delete(kind));
  } catch {
    throw new Error('Не удалось удалить звук из браузера');
  }
  buffers.delete(kind);
  const next = { ...info };
  delete next[kind];
  info = next;
  emit();
};
