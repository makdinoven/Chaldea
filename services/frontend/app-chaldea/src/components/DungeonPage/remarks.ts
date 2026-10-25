/*
  What a member says aloud over their figurine when they act on the table
  (FEAT-176): a vote for a door or the portal, a mark. Only a bubble on the
  board — the chat is kept for what people type.
*/

const pick = (lines: string[]) => lines[Math.floor(Math.random() * lines.length)];

const VOTE_DOOR = ['Пошли сюда!', 'Туда!', 'Предлагаю сюда.', 'Давайте туда!', 'Мне туда.', 'Нам сюда.'];
const VOTE_PORTAL = ['Давайте в портал!', 'В портал!', 'Рискнём порталом?', 'Портал — наш путь.'];
const VOTE_ANY = ['Веди, лидер.', 'Решай ты.', 'Куда скажешь.', 'Мне всё равно — веди.'];
const MARK_GO = ['Сюда!', 'Пошли сюда!', 'Нам туда!', 'Вот сюда.'];
const MARK_DANGER = ['Там опасно!', 'Осторожно!', 'Не нравится мне это…', 'Туда лучше не соваться.'];
const MARK_LOOK = ['Смотрите!', 'Гляньте сюда.', 'Что это там?', 'Видите?'];

/** A vote said aloud: for a door, the blue portal, or "as the leader decides". */
export const voteRemark = (vote: { corridor_id?: number | null; portal?: boolean }) =>
  pick(vote.portal ? VOTE_PORTAL : vote.corridor_id ? VOTE_DOOR : VOTE_ANY);

/** A mark said aloud. */
export const markRemark = (kind: string) => pick(kind === 'danger' ? MARK_DANGER : kind === 'look' ? MARK_LOOK : MARK_GO);
