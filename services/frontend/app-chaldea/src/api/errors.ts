import axios from 'axios';

/**
 * Turns any failure (axios error, network error, thrown value) into a message
 * that can be shown to the player **in Russian**.
 *
 * Every FEAT-154 API call routes its failures through this helper so that no
 * error is ever swallowed silently (CLAUDE.md — Frontend Error Display).
 *
 * Backend `detail` strings are already Russian across all services, so they are
 * preferred over the generic fallback whenever present.
 */
export const apiErrorMessage = (error: unknown, fallback: string): string => {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      return error.code === 'ECONNABORTED'
        ? 'Сервер не ответил вовремя. Попробуйте ещё раз.'
        : 'Нет связи с сервером. Проверьте подключение.';
    }

    const status = error.response.status;
    const detail = (error.response.data as { detail?: unknown } | undefined)?.detail;

    // FastAPI returns either a string (HTTPException) or a list of validation
    // objects (422). Both are handled — see note N11: the bulk endpoints answer
    // 422 for a MISSING `ids` param and 400 for a MALFORMED one.
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail) && detail[0]) {
      const first = detail[0] as { msg?: unknown };
      if (typeof first.msg === 'string' && first.msg.trim()) return first.msg;
    }

    if (status === 401) return 'Сессия истекла — войдите заново.';
    if (status === 403) return 'Недостаточно прав для этого действия.';
    if (status === 404) return 'Запрошенные данные не найдены.';
    if (status === 409) return 'Действие невозможно в текущем состоянии.';
    if (status === 413) return 'Файл слишком большой.';
    if (status === 422) return 'Некорректные данные запроса.';
    if (status === 429) return 'Слишком много запросов. Подождите немного.';
    if (status >= 500) return 'Ошибка на сервере. Попробуйте позже.';
  }

  return fallback;
};

export default apiErrorMessage;
