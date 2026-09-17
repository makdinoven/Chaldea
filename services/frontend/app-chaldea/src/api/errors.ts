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

/**
 * HTTP status of a failure, whether it arrived as a raw `AxiosError` or as the
 * normalized `ApiError` thrown by the inventory axios instance (`api/client`).
 */
const errorStatus = (error: unknown): number | undefined => {
  if (axios.isAxiosError(error)) return error.response?.status;
  const status = (error as { status?: unknown } | null)?.status;
  return typeof status === 'number' ? status : undefined;
};

/**
 * FEAT-167 — `POST /inventory/{id}/items` is now behind RBAC
 * (`require_permission("items:update")`), so an admin screen can legitimately
 * get a 401 or a 403. Both admin item-grant flows show this message, so the
 * reason is never swallowed: a moderator without `items:update` must see *why*
 * the grant failed, not a generic «не удалось».
 */
export const itemGrantErrorMessage = (
  error: unknown,
  fallback = 'Не удалось выдать предмет. Попробуйте позже.',
): string => {
  const status = errorStatus(error);
  if (status === 403) {
    return 'Не удалось выдать предмет: недостаточно прав (требуется разрешение items:update)';
  }
  if (status === 401) {
    return 'Не удалось выдать предмет: сессия истекла — войдите заново';
  }
  // `api/client` already unwrapped the backend `detail` (Russian across all
  // services) into the message — surface it instead of a generic fallback.
  if (
    status !== undefined &&
    !axios.isAxiosError(error) &&
    error instanceof Error &&
    error.message.trim()
  ) {
    return `Ошибка выдачи предмета: ${error.message}`;
  }
  return apiErrorMessage(error, fallback);
};

export default apiErrorMessage;
