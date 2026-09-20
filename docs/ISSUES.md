# Chaldea - Known Issues & Tech Debt

Файл с известными проблемами, багами и техническим долгом. Приоритеты: CRITICAL / HIGH / MEDIUM / LOW.

---

## DONE / Learning notes

### ~~Уязвимость: посты игроков пропускали `<form>`, `<input>` и `<style>` — фишинг и подмена интерфейса~~ DONE (2026-09-14)
**Сервис:** frontend
**Файлы:** `services/frontend/app-chaldea/src/utils/sanitizePostHtml.ts` (новый), `.../components/pages/LocationPage/PostCard.tsx`, `.../components/AdminModerationPage/AdminModerationPage.tsx`
**Описание:** Посты — это HTML, написанный игроками, и рендерятся через `dangerouslySetInnerHTML` после `DOMPurify.sanitize(html, { ADD_ATTR: ['data-archive-slug'] })`. Скрипты этот конфиг блокировал корректно, но **дефолты DOMPurify оставляют `<form>`, `<input>`, `<button>`, `<select>`, `<textarea>`, `<style>`**. То есть игрок мог положить в пост убедительную поддельную форму входа с `action` на свой сервер — её видели все, кто открывал локацию, — или `<style>`, чьи селекторы действуют на **всю страницу**, а не только на его пост (скрыть чужие посты, накрыть интерфейс). Конфиг к тому же был продублирован в двух файлах и неизбежно разошёлся бы.
**Исправление:** Один общий помощник `utils/sanitizePostHtml.ts`, который вызывают обе точки рендера. Политика переведена с deny-list на **allow-list**: вывод редактора TipTap — известное конечное множество, поэтому перечислены все допустимые теги и атрибуты, остальное удаляется (fail-closed). Инлайновый `style` сохранён (цвет — легальная возможность, FEAT-157), но допускается только по списку CSS-свойств, каждое привязано к тегам, на которых редактор его выпускает, и к шаблону значения; `position`, `z-index`, `transform`, `background-image: url(...)`, `width: 100vw` и т.п. вырезаются. `class` ограничен списком `archive-link` / `editor-link` — иначе игрок мог применить реальные классы из собранного CSS (`modal-overlay`).
**Проверено:** все 120 постов из БД и посты, полученные вживую из locations-service, после правки байт-в-байт совпадают со старым выводом; форма входа, `<style>`, оверлей, `url()`-маяк, `class="modal-overlay"`, `<script>`, `onerror`, `javascript:`, `<iframe>`, `id` — нейтрализованы. `npx tsc --noEmit` и `npm run build` зелёные.
**Осталось (отдельной задачей):** `utils/postText.ts` санитизирует тот же контент своим конфигом (`USE_PROFILES: { html: true }`) перед извлечением обычного текста — его стоит перевести на общий помощник. `ArchivePage/ArchiveArticlePage.tsx` и `RulesPage/RuleOverlay.tsx` рендерят контент, написанный админами (другой уровень доверия), и общую политику постов им применять нельзя без отдельного решения. Внешние ссылки в постах остаются — санитайзер не отличит фишинговую ссылку от обычной, это зона модерации.

### Prod-инцидент: взаимные HTTP-вызовы вычерпали QueuePool у character-service DONE (2026-09-04)
**Сервисы:** character-service, user-service, notification-service
**Симптом:** Прод «жутко лагает», внизу постоянно висит «Переподключение к серверу». При этом сервер здоров: load average 0.29, диск 40%, все контейнеры Up.
**Механика (цикл):**
1. `user-service` `GET /users/me` -> `_fetch_character_short()` -> ждёт `character-service /characters/{id}/short_info`.
2. `character-service` `GET /characters/{id}/profile` держал сессию из `Depends(get_db)` **и одновременно** ждал `user-service /users/{id}` до 5 секунд.
Соединение из пула удерживалось на всё время ожидания чужого HTTP. Пул (5 + 10 overflow) вычерпывался, дальше `sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached`, и сервис переставал отвечать вообще — включая `/openapi.json`, который к БД не обращается.
**Как это убивало WebSocket:** деградировавший `/users/me` стабильно отвечал за 5.03–5.07 с (сработавший внутренний `timeout=5.0`, исключение проглатывалось). В `notification-service.authenticate_websocket` таймаут был ровно `5.0` — промах на десятки миллисекунд, `return None`, handshake закрывался с 403 для **всех** пользователей. Фронт (`useWebSocket.ts`) уходил в бесконечный реконнект. В логах — ни одной причины: `except Exception: return None`.
**Исправление:**
- `character-service/app/main.py::get_character_profile` — все поля материализуются до вызова, `db.close()` перед HTTP. Цикл разорван.
- `character-service/app/database.py` — пул 15 + 15 overflow, `pool_timeout=10` (fail-fast вместо 30 с).
- `notification-service/app/auth_http.py` — `AUTH_REQUEST_TIMEOUT = 15.0` (заведомо больше худшего случая `/users/me` = 2 x 5 с), логирование причины отказа, таймаут для `requests.get` (его вообще не было — поток мог зависнуть навсегда), 503 вместо зависания при недоступном user-service.
- `notification-service/app/database.py` — добавлены `pool_pre_ping` / `pool_recycle` (единственный сервис, где их не было).
**Правило на будущее:** никогда не держать сессию БД открытой через `await` на межсервисный HTTP. Таймаут вызывающего всегда должен быть строго больше суммарного худшего случая вызываемого — равные таймауты дают 100% отказов вместо деградации. `except Exception: return None` в пути аутентификации делает такой инцидент недиагностируемым.

### Баг: некорректный рендер пути между локациями при рисовании от большего id к меньшему DONE
**Сервис:** frontend (`AdminPathEditor`) + locations-service
**Файл:** `services/frontend/app-chaldea/src/components/AdminPathEditor/AdminPathEditorPage.tsx` (`handleDrawClick`)
**Описание:** При создании пути между локациями (`createNeighborWithPath`) фронтенд отправлял `locationId`/`neighbor_id` в том порядке, в котором пользователь кликал, а `path_data` — в порядке рисования. Backend (`locations-service/app/crud.py::add_neighbor`) хранит обе строки `LocationNeighbor` (forward + reverse) с одинаковым `path_data`. На чтении (`crud.py` ~428) region endpoint нормализует ребро к `(min_id, max_id)` и дедуплицирует по `seen_edges`: какая из двух строк будет оставлена — зависит от порядка итерации по БД. Если оставалась строка, где `location_id > neighbor_id`, код разворачивал `path_data`; иначе — нет. В результате, когда пользователь рисовал от локации с бóльшим id к локации с меньшим id, `path_data` мог остаться в исходном (обратном относительно `min→max`) порядке, и в `RegionMapEditor.tsx` (~строка 897) полилиния `[from, ...path_data, to]` рендерилась с «прыжками».
**Исправление:** В `handleDrawClick` перед dispatch `createNeighborWithPath` канонизируем направление: всегда отправляем `locationId = min(drawStartId, locId)`, `neighbor_id = max(...)`, и если рисование шло от большего id — реверсируем `drawWaypoints`. Благодаря этому обе строки в БД хранятся в порядке `min→max`, и существующая логика reverse при чтении работает консистентно в обоих направлениях. Аналогичный приём уже был применён в ветке «arrow → location» того же файла.
**Альтернатива (не реализована):** то же самое можно было сделать в backend `add_neighbor` (нормализовать порядок + reverse при swap), но чтобы минимизировать blast radius, правка сделана только на фронтенде.

### ~~Баг: редактор подрасы всегда открывался с расой «Человек» и переподчинял подрасу~~ DONE (2026-09-06)
**Сервис:** frontend (`AdminRaces`) + character-service (источник данных)
**Файлы:** `services/frontend/app-chaldea/src/components/Admin/AdminRaces/AdminRacesPage.tsx`, `SubraceForm.tsx`, `services/frontend/app-chaldea/src/redux/slices/racesSlice.ts`
**Описание:** В `/admin/races` при нажатии «Редактировать» у любой подрасы селект «Раса» показывал первую расу списка («Человек») вместо настоящей. Причина: список рисуется из `GET /characters/races` (`response_model=List[RaceWithSubraces]`), а вложенная схема `SubraceWithPreset` **не содержит `id_race`** (в отличие от `SubraceResponse`). Фронтенд же брал родителя из самой подрасы: `setDefaultRaceIdForSubrace(subrace.id_race)` -> `undefined`, дальше `SubraceForm` падал в фолбэк `races[0]`. При этом TypeScript ошибку не ловил: интерфейс `Subrace` объявлял `id_race: number` как обязательное поле, чего API не гарантирует.
**Тяжесть:** не косметика. `handleSaveSubrace` отправляет `id_race` из формы, поэтому обычное сохранение подрасы (например, правка описания эльфийских Сидов) молча **переподчиняло её расе «Человек»**, если админ не замечал подмену и не выбирал расу заново вручную.
**Предсуществующий:** появился вместе с самим экраном в FEAT-043 (`05b4029`); FEAT-154 (`18ba9ea`) трогала эти файлы, но только добавляла поля — к багу отношения не имеет.
**Исправление:** родительская раса берётся из строки списка, под которой отрисована подраса: `handleEditSubrace(e, subrace, race.id_race)` -> `subrace.id_race ?? raceId`. `Subrace.id_race` в слайсе помечен опциональным с комментарием, откуда он есть, а откуда нет, чтобы тип перестал врать. Фолбэк в `SubraceForm` переведён с `||` на `??`.
**Корень закрыт (2026-09-06):** в `SubraceWithPreset` добавлено поле `id_race` (аддитивно, заполняется из уже загруженной родительской расы в `GET /characters/races`), так что публичный ответ больше не умалчивает о родителе. Фронтенд-фикс оставлен как есть — он самодостаточен.
**Правило на будущее:** публичная (урезанная) схема ответа и админская схема одной и той же сущности не должны расходиться по ключам, которые потребители считают гарантированными; расхождение TypeScript не ловит.

### Alembic revision IDs должны быть ≤32 символов DONE (FEAT-123 hotfix)
**Сервис:** все сервисы с Alembic
**Описание:** Дефолтная ширина колонки `version_num` в таблицах `alembic_version_*` — VARCHAR(32). Если revision id длиннее, `alembic upgrade head` падает на финальном UPDATE: `(1406, "Data too long for column 'version_num' at row 1")`, контейнер не стартует (fail-fast).
**Случай:** В FEAT-123 миграция character-service имела id `015_add_teleport_links_and_cooldown` (35 символов) → переименована в `015_teleport_cooldown` (21).
**Правило:** Все новые revision id — ≤32 символов. Желательно ≤24, чтобы оставить запас. Формат: `NNN_short_slug`.

### ~~Баг: Мастер Телепорта (FEAT-123) был полностью нерабочим — SELECT по несуществующей колонке~~ DONE (2026-09-14, FEAT-162 task #6)
**Сервис:** character-service
**Файлы:** `services/character-service/app/crud.py` (`execute_teleport`), `services/character-service/app/main.py` (`get_teleport_options`)
**Описание:** Оба места читали активного персонажа запросом `SELECT current_character_id FROM users WHERE id = :uid`, тогда как колонка в таблице `users` называется `current_character` (имя `current_character_id` существует только в ответе `GET /users/me` user-service, где оно формируется на лету). Любой вызов `POST /characters/npcs/{id}/teleport` падал с 500: `(1054, "Unknown column 'current_character_id' in 'field list'")`. То есть вся фича «Мастер Телепорта» не работала с момента выпуска.
**Обнаружено:** FEAT-162 task #6 — при живой проверке гашения намерений после телепорта (баг блокировал проверку, поэтому исправлен в рамках задачи).
**Исправление:** имя колонки в обоих запросах приведено к фактическому (`current_character`), с поясняющим комментарием. Проверено вживую: телепорт 523 → 1173 вернул 200.
**Правило на будущее:** имя поля в схеме ответа сервиса-владельца не обязано совпадать с именем колонки в общей БД; сырой SQL по чужой таблице сверять со `SHOW COLUMNS`, а не с API-схемой.

### ~~Баг: персонаж с титулом не удалялся, а веерная очистка успевала его «выпотрошить»~~ DONE (2026-09-14)
**Сервис:** character-service
**Файлы:** `services/character-service/app/models.py` (`Character.titles`, `CharacterTitle.character_id`), `services/character-service/app/main.py` (`DELETE /characters/{character_id}`), миграция `022_character_titles_cascade`
**Описание:** `character_titles.character_id` входит в составной первичный ключ таблицы, а связь
`Character.titles` была объявлена без каскада. При `db.delete(character)` ORM пытался занулить
дочерний FK — колонку первичного ключа — и падал на коммите с
`AssertionError: Dependency rule on column 'characters.id' tried to blank-out primary key column
'character_titles.character_id'`. Хендлер ловил только `SQLAlchemyError`, поэтому `AssertionError`
уходил наружу **пустым 500 без `detail`** и без `db.rollback()`. На dev-БД так не удалялись 11
персонажей; остальные удалялись нормально. `character_titles` была единственной внешней ссылкой на
`characters` с правилом `NO ACTION` (у `teleport_links` обе — `CASCADE`).
**Почему это было хуже отказа:** веерная очистка соседних сервисов (inventory, skills, attributes,
user_characters, черновики постов) шла **до** удаления строки и успевала отработать. Неудачное
удаление оставляло персонажа «выпотрошенным, но живым»: инвентарь, навыки, атрибуты и связь с
пользователем стёрты, персонаж остался в публичном списке, а админу показано
«Не удалось удалить персонажа».
**Исправление:**
1. `Character.titles` получил `cascade="all, delete-orphan"`; миграция `022_char_titles_cascade`
   переводит FK `character_titles.character_id` на `ON DELETE CASCADE` (страховка для удалений
   в обход ORM). ORM-каскад работает и без миграции — они независимы.
2. Порядок в хендлере перевёрнут: сначала удаление строки + коммит, и только после успеха —
   best-effort очистка соседей. Полной атомарности тут не существует (очистка идёт по HTTP и не
   входит в транзакцию БД), поэтому выбран безопасный режим отказа.
3. `except SQLAlchemyError` заменён на `except Exception` с `rollback()`, `exc_info=True` и русским
   `detail` вместо пустого тела.
**Остаточный риск (осознанный):** при падении очистки *после* успешного удаления в соседних сервисах
остаются осиротевшие строки (инвентарь/навыки/атрибуты несуществующего персонажа). Игроку они не
видны — все публичные выборки идут INNER JOIN по `characters`, — и чинятся повторным вызовом
admin-эндпоинтов соседей. Это строго лучше «выпотрошенного» персонажа в списке ролей.
**Проверено вживую (2026-09-14):** до правки `DELETE /characters/999806` → 500 с пустым телом,
`AssertionError` в логах, у персонажа обнулились инвентарь/навыки/атрибуты/связь, сам он остался.
После — `200 OK`, строки `characters`, `character_titles`, `character_inventory`, `character_skills`,
`character_attributes`, `users_character` = 0; персонаж исчез из `/characters/list`,
`/characters/by_location`, `/characters/{id}/public` (404), `/characters/{id}/short_info` (404),
`/characters/{id}/full_profile` (404) и `/characters/home-leaderboards`. Принудительный сбой
удаления (временный FK `ON DELETE RESTRICT`) дал 500 **с русским detail**, и всё содержимое
персонажа осталось на месте — «выпотрошить» персонажа больше нельзя.
**Тесты:** теста на удаление персонажа с титулом нет — это прямой аналог фикстуры, которая
скрывала опечатку в колонке. QA: нужен тест `DELETE /characters/{id}` для персонажа с
`character_titles` и тест на порядок (при сбое удаления очистка соседей не вызывается).
**Правило на будущее:** связь на таблицу, где FK входит в первичный ключ, обязана иметь
`cascade="all, delete-orphan"`; необратимую очистку нельзя запускать раньше операции, ради которой
она делается.

---

## CRITICAL

### ~~27. JWT-секрет — публично известный fallback `your-secret-key`~~ DONE (2026-09-19, ротация на проде)
**Сервис:** user-service (docker/env)
**Файлы:** `docker-compose.yml:227` (`JWT_SECRET_KEY: ${JWT_SECRET_KEY:-your-secret-key}`), `.env` (ключ отсутствует), prod `.env` на VPS (fallofgods.top)
**Обнаружено:** FEAT-150 (Codebase Analyst, 2026-07-17). По решению пользователя — исправляется отдельной задачей, не в рамках FEAT-150.
**Описание:** `auth.py` берёт секрет из `JWT_SECRET_KEY`, но ни локальный, ни (по всем признакам) prod `.env` его не задают — используется дефолт `your-secret-key`, прописанный прямо в публичном репозитории. HS256-подпись с известным секретом означает, что **любой может изготовить валидный JWT с ролью admin** и пройти авторизацию во всех 12 сервисах (они валидируют токены через `GET /users/me` user-service). Это полная компрометация аутентификации.
**Решение:**
1. Сгенерировать криптостойкий секрет (например, `openssl rand -hex 32`) и прописать `JWT_SECRET_KEY` в prod `.env` на VPS.
2. Добавить `JWT_SECRET_KEY` в `.env.example` с маскированным значением-заглушкой.
3. Рассмотреть удаление fallback-значения из `docker-compose.yml` (fail-fast без секрета) — как минимум для prod-конфигурации.
**Цена:** смена секрета инвалидирует все выданные токены → однократный принудительный re-logout всех пользователей (после FEAT-150 достаточно одного повторного входа; refresh-токены со старой подписью тоже перестанут работать). Скоординировать с деплоем.
**Сделано (2026-09-19):** на проде в `.env` прописан случайный секрет (64 hex), user-service пересоздан (`up -d --force-recreate`). Проверено: в контейнере секрет не дефолтный, а токен, подделанный старым `your-secret-key` с ролью admin, получает 401; вход и админка работают. Осталось (мелочь, отдельно): заглушка `JWT_SECRET_KEY` в `.env.example` и удаление публичного fallback из `docker-compose.yml`, чтобы сервис падал без секрета, а не поднимался с известным.
**Уточнено (Codebase Analyst, FEAT-169, 2026-09-19):** пункт 2 («заглушка в `.env.example`») **уже выполнен** — `.env.example:21` содержит `JWT_SECRET_KEY=change-me-jwt-secret-at-least-32-chars`. Остаётся только пункт 3. Заодно: сервис уже фейлится сам — `user-service/auth.py:13` читает `os.environ["JWT_SECRET_KEY"]` на импорте (KeyError), так что удаления fallback из `docker-compose.yml:248` достаточно; в `docker-compose.prod.yml` переменной нет вовсе, prod наследует ту же строку из базового файла. Локальный `.env` **не содержит** ни `JWT_SECRET_KEY`, ни `INTERNAL_SERVICE_TOKEN` — снятие fallback'ов сломает локальную разработку, пока оба ключа не добавят в `.env`.
**Закрыто полностью (FEAT-169, задачи #1/#9):** пункт 3 выполнен — в `docker-compose.yml` осталось `JWT_SECRET_KEY: ${JWT_SECRET_KEY}` без значения по умолчанию, литерал `your-secret-key` больше не встречается в репозитории ни разу (prod-файл user-service не переопределяет и наследует ту же строку). Заодно закрыта дыра, которой не было в исходной записи: `os.environ["JWT_SECRET_KEY"]` падал с голым `KeyError`, но **пустую строку пропускал** — теперь `user-service/auth.py` явно проверяет на непустоту и падает с `RuntimeError`, потому что compose без ключа в `.env` подставляет именно пустую строку, а не отсутствие переменной. Локальный `.env` (в gitignore) оба ключа получил; требование записано в `.env.example` и `docs/ARCHITECTURE.md`.

---

## HIGH

### ~~Утечка ПДн: `GET /users/{id}` анонимно отдавал e-mail живого человека~~ DONE (FEAT-171, задача #25)
~~**Сервис:** user-service~~
~~**Файлы:** `services/user-service/main.py:2254` (`get_user_by_id`, ни одной зависимости), `:748` (`GET /users/admins`), `schemas.py:50` (`UserRead` с полем `email`)~~
~~**Обнаружено:** FEAT-171 (Reviewer, review #1, 2026-09-19). Проверено вживую: `GET /users/7` без токена возвращал настоящий адрес.~~
**Исправлено (FEAT-171, задача #25):** публичной схемой стала `schemas.UserPublicRead` (`id`, `username`, `role`, `avatar`, `registered_at`), а `UserRead` теперь **наследуется от неё** и лишь добавляет `email` — направление наследования выбрано так, что новое приватное поле не может просочиться в публичный ответ. `GET /users/{id}` получил `get_optional_user` и отдаёт `UserRead` только владельцу учётки и админу/модератору с правом `users:read`; всем остальным ключа `email` в JSON **нет вовсе**. `GET /users/admins` (одним анонимным запросом отдавал адреса **всех** администраторов) переведён на ту же публичную схему — его единственный потребитель, consumer notification-service, читает только `id`. Внутренний двойник не понадобился: оба межсервисных вызывающих (`character-service/app/main.py:2252,2369,2476`, `locations-service/app/crud.py:6892`) берут отсюда только `username`.

### ~~Уязвимость: `POST /attributes/cumulative_stats/increment` открыт через gateway без авторизации~~ DONE (FEAT-167, задача #17)
~~Найдено Reviewer'ом в FEAT-167: эндпоинт был помечен как internal, но лежал не под `/attributes/internal/`, поэтому анонимный `POST` через gateway отвечал `200 {"detail":"Stats updated"}` и позволял накручивать `pve_kills` / `pvp_wins` / `total_damage_dealt` любому персонажу, а заодно **открывать перки** (обработчик возвращает `newly_unlocked_perks`).~~
**Исправлено в том же пуше:** на эндпоинт повешен `Depends(verify_internal_token)`; все четыре вызывающих (`battle-service/app/main.py`, `inventory-service/app/main.py`, `locations-service/app/main.py`, `skills-service/app/main.py`) шлют `X-Internal-Token`. Проверено вживую Reviewer'ом: анонимно → 401, все четыре вызывающих → 200/400 (т.е. авторизацию проходят).

### ~~Уязвимость: создание атрибутов и инвентаря доступно анонимно через gateway~~ DONE (FEAT-167, задачи #17/#18)
~~Найдено Reviewer'ом в FEAT-167: `POST /attributes/` и `POST /inventory/` не имели ни одной зависимости, и nginx их не резал — снаружи можно было создавать строки атрибутов и инвентаря для произвольных `character_id`.~~
**Исправлено в том же пуше:** оба под `Depends(verify_internal_token)`; единственный вызывающий, character-service, шлёт заголовок из всех трёх мест (`crud.send_attributes_request`, `crud.send_inventory_request`, `crud._sync_send_attributes_request` — спавн моба). Проверено вживую: анонимно оба → 401, все три клиентские функции в живом контейнере → 200 с созданием строк. **Остаётся открытым** более широкий долг ниже — «большинство внутренних эндпоинтов защищены только nginx».

### ~~Уязвимость: `GET /inventory/characters/{id}/fast_slots` отдаётся без авторизации~~ DONE (FEAT-169, задачи #3/#14)
**Сервис:** inventory-service
**Файл:** `services/inventory-service/app/main.py:1252-1259` (`get_fast_slots` — единственная зависимость `Depends(get_db)`; в записи ниже был устаревший диапазон 1186-1193, поправлено Analyst'ом в FEAT-169)
**Обнаружено:** FEAT-168 (QA, 2026-09-19) — предсуществующий долг, фичей не внесён.
**Приоритет:** HIGH
**Описание:** маршрут лежит под публичным префиксом `/inventory/` (nginx его не режет) и не проверяет ни JWT, ни владение персонажем: любой анонимный запрос отдаёт содержимое пояса произвольного `character_id`. После FEAT-168 ответ стал заметно богаче — к составу пояса добавились боевая настройка предмета (`consumable_action`, `coating_turns`, `coating_bonus_damage`) и полные строки `item_effects` / `item_damage_entries`, то есть разведка снаряжения противника перед боем стала точнее. Записи в БД маршрут не меняет, поэтому это утечка, а не порча данных. Архитектурная секция фичи (§3.3.3) утверждает «Auth unchanged (`get_current_user_via_http` + ownership check)» — в коде этой проверки нет ни до, ни после FEAT-168.
**Тест:** `services/inventory-service/app/tests/test_fast_slots_payload.py::TestFastSlotsAuth::test_fast_slots_requires_auth` — помечен `xfail` (non-strict), станет зелёным сам, когда проверку добавят.
**Возможное решение:** повесить `Depends(get_current_user_via_http)` + `verify_character_ownership`; учесть, что battle-service ходит сюда сервер-сервер (`battle-service/app/inventory_client.py:118`) — ему понадобится либо `X-Internal-Token`, либо отдельный internal-маршрут.
**Исправлено (FEAT-169):** маршрут разложен на два по образцу FEAT-167. Игровой путь остался прежним и получил `Depends(get_current_user_via_http)` + существующий `verify_character_ownership` (анонимно → 401, чужой персонаж → 403, свой → 200). Для battle-service добавлен близнец `GET /inventory/internal/characters/{id}/fast_slots` под `verify_internal_token` — проверки владения на нём нет намеренно, у мобов и NPC `user_id IS NULL`. Тело общее (`_get_fast_slots_core`), ответ байт в байт прежний. `battle-service/app/inventory_client.py:118` переведён на internal-путь и шлёт заголовок. `xfail` с `TestFastSlotsAuth::test_fast_slots_requires_auth` снят — тест зелёный сам по себе; анонимные вызовы в `test_equip_locking.py`, `test_npc_equipment.py`, `test_item_out_schemas_serve_stored_rows.py` переведены на internal-маршрут.

### ~~Долг: оставшиеся `/internal/*` маршруты char-attrs и inventory защищены только nginx~~ DONE (FEAT-169, задачи #3/#4)
**Сервисы:** character-attributes-service, inventory-service
**Файлы:** `character-attributes-service/app/main.py` (`POST /attributes/internal/settle-regen`, `/internal/{id}/satiety`, `/internal/{id}/reconcile-perks`), `inventory-service/app/main.py` (`POST /inventory/internal/characters/{id}/revalidate-equipment`, `/internal/characters/{id}/consume_item`, `/internal/characters/{id}/free_slots_check`, `/internal/characters/{id}/gathering/award`, `/internal/update-durability`)
**Обнаружено:** FEAT-167 (Architect §3.8.2 / Reviewer, 2026-09-18) — перечень сверен по таблице роутов после задач #17/#18.
**Приоритет:** HIGH
**Описание:** восемь маршрутов принимают запрос без единой проверки в самом сервисе; единственный слой — `location /…/internal/ { return 403; }` в nginx. Любая ошибка в ingress или доступ внутрь compose-сети открывает выдачу ресурсов сбора, списание предметов, снятие прочности и досчёт восстановления. Оба сервиса **уже имеют** `verify_internal_token` в `app/auth_http.py` (добавлен FEAT-167), так что правка построчная — но требует синхронно обновить вызывающих (в частности `party-service` → `/attributes/internal/settle-regen`, у которого токен появился только в FEAT-167).
**Возможное решение:** повесить `Depends(verify_internal_token)` на все восемь и добавить заголовок вызывающим; отдельной задачей, вместе с общей записью «большинство внутренних эндпоинтов защищены только nginx» ниже.
**Уточнено (Codebase Analyst, FEAT-169, 2026-09-19):** перечень сверен — ровно восемь, ни один не вызывается с фронтенда, так что internal-двойники (как в FEAT-167 для выдачи предметов) не нужны. Два более новых internal-маршрута inventory-service (`GET /internal/characters/{id}/xp-multiplier` `main.py:1773` и `…/xp-multipliers` `:1807`, оба FEAT-168) **уже** под `verify_internal_token`. Вызывающие и их готовность: satiety ← `inventory/main.py:3443` (хелпер есть), reconcile-perks ← `inventory/main.py:844-870` + `character-service/main.py:1963` (хелперы есть), revalidate-equipment ← `skills/main.py:734` (есть), free_slots_check ← `locations/crud.py:7374` (есть), gathering/award ← `locations/crud.py:6381` (есть), settle-regen ← `party/crud.py:22` (хелпер лежит в `party/main.py:53` — из `crud.py` не импортируется, циклический импорт), consume_item ← `battle/inventory_client.py:23` и update-durability ← `:83` (**в этом модуле хелпера нет вообще**). Шесть из восьми вызывающих проглатывают ошибку с WARNING — забытый заголовок даст тихую деградацию, а не отказ.
**Исправлено (FEAT-169):** на все восемь повешен `Depends(verify_internal_token)` (пусто → 503, чужой/отсутствующий заголовок → 401, русский `detail`). Все вызывающие обновлены синхронно: satiety и reconcile-perks — `inventory/main.py`, reconcile-perks — `character-service/main.py`, revalidate-equipment — `skills/main.py`, free_slots_check и gathering/award — `locations/crud.py`, settle-regen — `party/crud.py` через новый leaf-модуль `party-service/app/internal_auth.py` (хелпер лежал в `main.py`, из `crud.py` его было не импортировать — цикл), consume_item и update-durability — `battle-service/app/inventory_client.py`, куда добавлен локальный `_internal_token_headers()` (импорт из `main` дал бы цикл). Ровно из-за тихой деградации QA проверяет **сам заголовок на реальной клиентской функции** (`call.kwargs["headers"]["X-Internal-Token"]`), а не «ничего не упало»; закрыты и два пробела в покрытии — у `update-durability` и `reconcile-perks` не было ни одного HTTP-теста.

### ~~Долг: `INTERNAL_SERVICE_TOKEN` имеет публично известный fallback `dev-internal-token-change-me`~~ DONE (FEAT-169, задача #1)
**Сервисы:** character-service, character-attributes-service, locations-service, battle-service, inventory-service, skills-service, dungeon-service, party-service, battle-pass-service, celery-worker (все, кому токен задан в compose — после FEAT-167 это 10 сервисов)
**Файлы:** `docker-compose.yml`, `docker-compose.prod.yml` (объявление `${INTERNAL_SERVICE_TOKEN:-dev-internal-token-change-me}` у каждого из 10 сервисов), `.env.example:28`
**Обнаружено:** FEAT-162 (Reviewer, 2026-09-14). Долг **пред­существующий** — дефолт был прописан ещё до FEAT-162 для четырёх сервисов; фича лишь распространила ту же строку на ещё два и сделала её несущей.
**Описание:** во всех compose-файлах токен объявлен как `${INTERNAL_SERVICE_TOKEN:-dev-internal-token-change-me}`. Если переменная не задана в prod `.env` на VPS, все сервисы поднимутся с дефолтом, прописанным прямо в публичном репозитории. После FEAT-162 на этом токене держится второй (и для шести эндпоинтов — фактически единственный прикладной) слой защиты internal-маршрутов: `verify_internal_token` сравнивает заголовок именно с ним. Тот же класс проблемы, что и запись 27 про `JWT_SECRET_KEY`.
**Почему не CRITICAL:** первый слой (nginx `return 403` на всех `/internal/`-префиксах) остаётся, и порты сервисов в prod наружу не открыты — эксплуатация требует доступа внутрь compose-сети либо ошибки в ingress.
**Возможное решение:** сгенерировать криптостойкое значение (`openssl rand -hex 32`), прописать `INTERNAL_SERVICE_TOKEN` в prod `.env`, добавить в `.env.example` маскированную заглушку и рассмотреть удаление fallback-значения из `docker-compose.prod.yml` (fail-closed: без токена сервис отдаёт 503 — механизм уже реализован).
**Дополнено (Codebase Analyst, FEAT-167):** токен вообще не проброшен **party-service** и **battle-pass-service** — ни в `docker-compose.yml`, ни в `docker-compose.prod.yml`. Оба вызывают эндпоинты, которые FEAT-167 закрывает (party → `active_experience`/`passive_experience`, battle-pass → `POST /inventory/{id}/items`), и оба проглатывают ошибку с warning'ом. Без правки compose тихо пропадут опыт отряда и предметные награды боевого пропуска. FEAT-167 добавил переменную обоим (проверено на смёрженном prod-конфиге); после этого каждый новый сервис-вызывающий обязан получать её сразу.
**Дополнено (Reviewer, FEAT-167, 2026-09-18):** после FEAT-167 токен стал единственным прикладным слоем ещё для ~12 маршрутов (шесть изменяющих `/attributes/{id}/…`, новый `POST /inventory/internal/characters/{id}/items` и остальные `/internal/`-пути). **Настоящее значение обязательно задать в prod `.env` в том же пуше, что и FEAT-167** — иначе прод поедет с публично известной строкой.
**Исправлено (FEAT-169, задача #1):** в `docker-compose.prod.yml` у **каждого** потребителя стоит строгая форма `${INTERNAL_SERVICE_TOKEN:?INTERNAL_SERVICE_TOKEN is required in production}` — 7 строк переписаны с fallback'а и 6 добавлены. Шесть добавленных важнее семи переписанных: char-attrs, inventory и locations получали переменную **только** из базового файла, то есть при правке одних лишь объявленных в prod сервисов они уехали бы в прод на публичном `dev-internal-token-change-me`; ещё три (user-service, notification-service, autobattle-service) стали потребителями впервые и добавлены в **оба** файла. В `docker-compose.yml` (dev) fallback сохранён осознанно — свежий клон должен подниматься из коробки; потребителей в dev стало 13.
**Приёмка была эмпирической, а не «по рассуждению»:** посервисный diff окружения до/после на смёрженном конфиге (`docker compose -f docker-compose.yml -f docker-compose.prod.yml config`) дал ровно три добавленных ключа и ни одной потери — то есть блок `environment:` в prod-файле действительно **мержится** с базовым, а не заменяет его (проверено, потому что рядом в том же файле используется `!reset []` именно из-за merge-семантики). С секретами в `.env` — ноль вхождений `dev-internal-token-change-me`; без них prod-конфиг падает с `required variable INTERNAL_SERVICE_TOKEN is missing a value`, а dev поднимается с fallback'ом.
**Побочный эффект, который надо знать деплоящему:** строгая форма `:?` роняет `config`/`ps`/`down`/`up` для **всего** стека, а не один контейнер. См. `docs/ARCHITECTURE.md`, раздел «Секреты и fail-fast».
**Комментарий в `.env.example` тоже исправлен:** он описывал только сценарий FEAT-125 (battle-service → skills-service `GET /skills/{id}/resolved`), хотя потребителей уже 13.

### ~~Уязвимость: `POST /skills/assign_multiple` и `POST /skills/` открыты через gateway без авторизации~~ DONE (FEAT-169, задачи #2/#7)
**Сервис:** skills-service
**Файлы:** `services/skills-service/app/main.py:567` (`assign_multiple_skills`), `services/skills-service/app/main.py:75` (`legacy_create_skills_for_new_character`)
**Обнаружено:** FEAT-169 (Codebase Analyst, 2026-09-19), систематический прогон таблиц роутов против обоих nginx-конфигов. Предсуществующий долг.
**Приоритет:** HIGH
**Описание:** у обоих обработчиков единственная зависимость — `Depends(get_db)`, `character_id` берётся **из тела запроса**, а nginx проксирует `/skills/` целиком (`nginx.conf:264`, `nginx.prod.conf` — тот же блок) без каких-либо правил. Анонимный запрос может назначить любому персонажу любой набор навыков по их id (`assign_multiple`) или создать/привязать базовый навык (`POST /skills/`). Ровно тот же класс, что закрытая в FEAT-167 дыра с выдачей предметов, только про навыки.
**Возможное решение:** развести как в FEAT-167 — internal-маршрут под `Depends(verify_internal_token)` для вызова из character-service при создании персонажа, и/или `get_current_user_via_http` + проверка владения; вторым слоем добавить правило в оба nginx-конфига.
**Исправлено (FEAT-169):** решение принято по вызывающим каждого маршрута, а не одним правилом на оба. У `assign_multiple` вызывающих двое — character-service при одобрении заявки и **админский** редактор НПС (`NpcStatsEditor.tsx:249`), который назначает навыки чужому персонажу, поэтому проверка владения его бы сломала: маршрут разложен на internal-близнец `POST /skills/internal/assign_multiple` (`verify_internal_token`, на него переведён `character-service/app/crud.py:1547`) и публичный путь под `require_permission("skills:create")` — разрешение уже существует у соседнего `POST /skills/admin/character_skills/`, новой строки в `permissions` и миграции не понадобилось. Legacy `POST /skills/` в проде не вызывается ни разу (только тесты), закрыт `verify_internal_token`. В `skills-service/app/auth_http.py` добавлен **стандартный** `verify_internal_token`; существующий `allow_jwt_or_service_token` намеренно не расширяли — он сверяет токен как Bearer, и смешение сделало бы один секрет валидным в двух позициях заголовка.
**Вторым слоем (задача #2):** `/skills/` был единственным семейством вообще без правила deny. В оба nginx-конфига добавлены `location /skills/internal/ { return 403; }` и `location = /skills/ { limit_except GET HEAD { deny all; } }` (точное совпадение — подпути не задеты). Проверено вживую на обоих конфигах: `nginx -t` зелёный; `POST /skills/` → 403, `GET`/`HEAD /skills/` → 200, `/skills/internal/...` → 403, при этом `/skills/1`, `/skills/1/resolved`, `/skills/assign_multiple`, `/skills/admin/...` и `DELETE /skills/character_skills/...` проходят как раньше.

### ~~Уязвимость: `POST /users/{user_id}/activity/increment` открыт через gateway без авторизации~~ DONE (FEAT-169, задачи #9/#11)
**Сервис:** user-service
**Файл:** `services/user-service/main.py:1656` (`increment_activity_points`)
**Обнаружено:** FEAT-169 (Codebase Analyst, 2026-09-19).
**Приоритет:** MEDIUM
**Описание:** в докстроке написано «Internal service-to-service call, no auth required», но маршрут лежит **не** под `/users/internal/`, поэтому правило `location /users/internal/ { return 403; }` (`nginx.conf:118`, `nginx.prod.conf:141`) его не ловит. Любой анонимный POST накручивает `activity_points` произвольному пользователю на произвольную величину. Один в один сценарий `POST /attributes/cumulative_stats/increment`, закрытый в FEAT-167.
**Возможное решение:** перенести под `/users/internal/` и повесить `verify_internal_token` (в user-service его ещё нет — добавить по образцу `character-service/app/auth_http.py:78-95`), синхронно обновить вызывающих.
**Исправлено (FEAT-169):** маршрут перенесён на `POST /users/internal/{user_id}/activity/increment` под `verify_internal_token` (механизм добавлен в `user-service/auth.py` — в сервисе его не было вовсе); старый путь удалён, а не оставлен алиасом, и теперь отдаёт 404. Новый путь попадает под существующее правило nginx `location /users/internal/ { return 403; }` — проверено вживую на обоих конфигах. Единственный вызывающий, `notification-service/app/chat_routes.py:138`, переведён на новый путь и шлёт заголовок; заодно `except: pass` заменён на `logger.warning`, иначе будущая поломка была бы полностью немой. Пока маршрут трогали, добавлена валидация `points: int = Field(1, ge=1, le=100)` — раньше принимались и отрицательные значения. user-service и notification-service получили `INTERNAL_SERVICE_TOKEN` в обоих compose-файлах.

### ~~Уязвимость: открытые изменяющие маршруты locations-service (прогресс квестов и выбор в диалоге)~~ DONE (FEAT-169, задача #8)
**Сервис:** locations-service
**Файлы:** `services/locations-service/app/main.py:3133` (`update_quest_progress`), `services/locations-service/app/main.py:2488` (`choose_dialogue_option`)
**Обнаружено:** FEAT-169 (Codebase Analyst, 2026-09-19).
**Приоритет:** MEDIUM
**Описание:** обе ручки берут `character_id` из тела и не проверяют ничего. `/quests/progress/update` двигает объектив квеста произвольного персонажа на произвольный инкремент (завершение квеста платит награду); выбор узла диалога у NPC может выдавать квесты. nginx режет только `/locations/internal/` и `/locations/quests/internal/`, эти два пути — нет.
**Возможное решение:** `update_quest_progress` — очевидный internal-маршрут (перенести под `/locations/quests/internal/` + `verify_internal_token`, механизм в сервисе уже есть — `main.py:3750`); диалог — игровой маршрут, ему нужен JWT + проверка владения персонажем.
**Исправлено (FEAT-169):** `update_quest_progress` перенесён на `POST /locations/quests/internal/progress/update` под `verify_internal_token`; старый путь удалён (вызывающих у него не было вообще — ни сервиса, ни фронтенда, ни теста), новый попадает под существующее правило nginx `location /locations/quests/internal/ { return 403; }` — проверено вживую. Нюанс реализации: объявлять маршрут пришлось **ниже** определения `verify_internal_token`, декоратор выполняется на импорте и иначе даёт `NameError`.
**Диалог закрыт только JWT, проверки владения намеренно нет** — вопреки строке «Возможное решение» выше. В теле запроса (`DialogueChooseRequest = {option_id}`) `character_id` отсутствует как поле, а обработчик только ходит по дереву диалога и ничего не выдаёт (квест берётся отдельной ручкой `POST /locations/quests/{id}/accept`). Добавлять `character_id` ради проверки — ломать контракт и править фронтенд без выигрыша в защите; аутентификация и так убирает анонимный доступ.

### Долг: неаутентифицированные чтения чужих данных (инвентарь, атрибуты, профиль, чат)
**Сервисы:** inventory-service, character-attributes-service, character-service, user-service, notification-service
**Файлы:** `inventory/app/main.py:361` (`GET /inventory/{id}/items`), `:766` (`GET /inventory/{id}/equipment`), `character-attributes-service/app/main.py:357` (`GET /attributes/{id}`), `:332` (`GET /attributes/{id}/perks`), `character-service/app/main.py:1911` (`GET /characters/{id}/full_profile`), `user-service/main.py:702` (`GET /users/all`), `notification-service/app/chat_routes.py:153` (`GET /notifications/chat/messages`)
**Обнаружено:** FEAT-169 (Codebase Analyst, 2026-09-19) — тот же класс, что дыра с `fast_slots`.
**Приоритет:** LOW–MEDIUM
**Описание:** всё это отдаётся анонимно через gateway. Инвентарь и экипировка чужого персонажа — прямая разведка перед боем; `GET /notifications/chat/messages` отдаёт историю любого канала без токена (при том что `DELETE` на том же роутере — `require_permission("chat:delete")`); Данные эти чтения не портят, поэтому не HIGH. `GET /attributes/{id}/perks` из списка **выделен в отдельную запись ниже** — он не просто читает, а пишет в БД, и это баг независимо от продуктового решения о публичности чтений.
**Статус:** остаётся открытым после FEAT-169 — сознательно. Нужно **продуктовое** решение, что должно остаться публичным: часть страниц открыта гостям, и «закрыть всё» здесь сломает гостевой фронтенд.
**Возможное решение:** одним заходом повесить `get_current_user_via_http` на чтения, которые не нужны публично, и разобраться, какие из них реально используются гостевым фронтендом (часть страниц открыта без входа — проверить перед правкой).
**Продуктовое решение получено (FEAT-171, 2026-09-19):** правила сформулированы пользователем — персонаж публичен (анкета, уровень, титулы, посты, надетая экипировка с названием и описанием предмета), а цифры приватны (характеристики, инвентарь, пояс, опыт, деньги, перки, навыки). Полная карта чтений по всем сервисам — в `features/FEAT-171-public-profile-and-private-data.md` §2.2, матрица полей — §2.3. Запись закрывается вместе с FEAT-171.
**Уточнено (Codebase Analyst, FEAT-171):** список в строке «Файлы» неполон. Ещё анонимно отдаются: `character-attributes-service/app/main.py:1340` (`GET /attributes/{id}/cumulative_stats` — в т.ч. `total_gold_earned`/`total_gold_spent`), `skills-service/app/main.py:373` (`GET /skills/characters/{id}/skills` — уровни навыков и выбранные перки), `character-service/app/main.py:2211` (`short_info`), `:3813` (`/logs`), `:3841` (`/post-history` с `xp_earned`), `inventory-service/app/main.py:273` и `:244` (полный шаблон предмета). Актуальная строка равнения экипировки — `inventory/app/main.py:773`, а не `:766`.

### ~~Уязвимость: `GET /inventory/{id}/equipment` анонимно отдаёт быстрые слоты — обход гейта FEAT-169~~ DONE (FEAT-171, задача #8)
**Сервис:** inventory-service
**Файлы:** `services/inventory-service/app/main.py:773` (`get_equipment_slots`), `app/crud.py:429-430` (`get_equipment_slots` фильтрует только по `character_id`), `app/crud.py:482-486` (`fast_slot_1..4` — такие же `slot_type` в той же таблице `equipment_slots`)
**Обнаружено:** FEAT-171 (Codebase Analyst, 2026-09-19)
**Приоритет:** MEDIUM
**Описание:** FEAT-169 закрыл `GET /inventory/characters/{id}/fast_slots` (JWT + проверка владения), но быстрые слоты физически лежат в той же таблице, что и обычная экипировка, и соседний маршрут `GET /inventory/{id}/equipment` отдаёт **все** строки персонажа без какой-либо авторизации — включая `fast_slot_1..4` с полным шаблоном предмета (`consumable_action`, `coating_*`, `effects[]`, `damage_entries[]`), заточкой, вставленными камнями, прочностью и вычисленным `effective_damage`. То есть гейт пояса обходится одним анонимным запросом к другому URL, и разведка перед боем работает ровно как до FEAT-169.
**Исправлено (FEAT-171, задача #8):** дыра закрыта с двух сторон. `GET /inventory/{id}/equipment` получил `get_optional_user` + `visibility.require_private_access` — чужому и гостю 403, владельцу/админу/НПС прежнее тело вместе с рядами `fast_slot_*`. Для витрины добавлен отдельный маршрут `GET /inventory/{id}/equipment/public` (`crud.get_public_equipment_slots`), где пояс отсекается **в самом запросе** (`slot_type NOT LIKE 'fast_slot_%'`), а не пост-фильтром, и слот несёт ровно `{slot_type, item: PublicItemCard|null}` — без `effective_damage`, заточки, вставок, прочности и любых `*_modifier`. Межсервисные вызывающие ходят на двойник `GET /inventory/internal/characters/{id}/equipment` (Pass A, задача #5).

### ~~Утечка: золото персонажа отдаётся анонимно через профиль пользователя~~ DONE (FEAT-171, задачи #6 и #9)
**Сервисы:** user-service, character-service
**Файлы:** `services/user-service/schemas.py:66` (`CharacterShort.currency_balance`), `services/user-service/main.py:1554` (`GET /users/{user_id}/profile` — `get_optional_user`, то есть работает и без токена), `main.py:116` (`_fetch_character_short`), `services/character-service/app/main.py:2241` (`short_info` отдаёт `currency_balance`), `:2023` (`full_profile` отдаёт `currency_balance`)
**Обнаружено:** FEAT-171 (Codebase Analyst, 2026-09-19)
**Приоритет:** MEDIUM
**Описание:** `GET /characters/{id}/short_info` кладёт `currency_balance` в ответ, а user-service переносит его в `CharacterShort` и отдаёт в `GET /users/{user_id}/profile` — маршрут с *опциональной* авторизацией, то есть баланс золота любого игрока виден анонимно на странице чужого профиля. Третий путь утечки — `GET /characters/{id}/full_profile` (тоже без авторизации). Алмазы (`users.diamonds`) не текут: они есть только в `GET /users/me` (JWT) и во внутреннем маршруте.
**Возможное решение:** закрывается в рамках FEAT-171. Единственный легитимный потребитель `currency_balance` — собственный `/users/me`; на ветке «не владелец» поле убрать, из `short_info` убрать вовсе или перенести во внутренний близнец.
**Исправлено (FEAT-171, задачи #6 и #9):** закрыты все три пути. `GET /characters/{id}/short_info` больше не отдаёт `currency_balance` вообще — баланс живёт только во внутреннем двойнике `GET /characters/internal/{id}/short_info`, откуда его берут `/users/me` и `/users/{id}/profile`. `GET /characters/{id}/full_profile` стал optional-auth: чужому уходит `PublicProfileResponse` (id, name, level, титул, аватар), без денег, `stat_points`, `level_progress` и `attributes`. `GET /users/{id}/profile` отдаёт `character` без ключа `currency_balance`, если смотрит не владелец профиля и не админ/модератор (`schemas.CharacterShortPublic` / `UserProfileStrangerResponse`). Приватные поля именно ОТСУТСТВУЮТ в JSON, а не равны null.

### Баг: `GET /attributes/{id}/perks` пишет в БД на чтение и транзитивно дёргает два сервиса — анонимно
**Сервис:** character-attributes-service
**Файлы:** `services/character-attributes-service/app/main.py:332` (обработчик), `:339-345` (самолечение — синхронный вызов `reconcile_perks` прямо внутри GET)
**Обнаружено:** FEAT-169 (Codebase Analyst, 2026-09-19); выделено в отдельную запись Reviewer'ом FEAT-169 по §3.10.2 — раньше было пунктом внутри записи про анонимные чтения выше.
**Приоритет:** MEDIUM
**Описание:** обработчик объявлен как чтение, но на каждый вызов запускает `reconcile_perks` «на всякий случай» — то есть **GET пишет в БД**. Это плохо само по себе (нарушение семантики метода: любой прокси, префетч браузера или краулер меняет данные), но здесь хуже: оценка перков тянет весь `/full_profile` (см. отдельную запись выше) и транзитивно ходит в character-service и inventory-service. Маршрут при этом **не требует авторизации** и проксируется gateway'ем, так что один анонимный GET в цикле превращается в усилитель нагрузки на три сервиса и поток записей в БД.
**Почему это отдельная запись, а не часть долга про анонимные чтения:** там открыт **продуктовый** вопрос (какие чтения должны остаться публичными для гостей), и пока он не решён, вся запись стоит. Здесь вопроса нет: запись на GET — баг при любом ответе на продуктовый вопрос. Чинится независимо и раньше.
**Возможное решение:** убрать самолечение из GET — перенести `reconcile_perks` на события, которые реально меняют перки (уровень, смена подкласса, изменение снаряжения; все три уже дёргают `/attributes/internal/{id}/reconcile-perks`, закрытый в FEAT-169), а чтение оставить чтением. Если самолечение всё же нужно как страховка — делать его фоновой задачей с дедупликацией, а не синхронно на каждый запрос.

### ~~Долг: autobattle-service ходит в `/battles/internal/*` без токена и не имеет `INTERNAL_SERVICE_TOKEN`~~ DONE (FEAT-169, задачи #1/#13)
**Сервисы:** autobattle-service, battle-service
**Файлы:** `services/autobattle-service/app/clients.py:15` (`GET /battles/internal/{id}/state`), `:23` (`POST /battles/internal/{id}/action`); `docker-compose.yml` / `docker-compose.prod.yml` (переменной у autobattle нет ни там, ни там)
**Обнаружено:** FEAT-169 (Codebase Analyst, 2026-09-19).
**Приоритет:** MEDIUM (блокер для будущей работы, не дыра сама по себе)
**Описание:** оба маршрута battle-service (`app/main.py:1373`, `:1428`) держатся только на nginx `return 403`. Когда до них дойдёт общий сweep по internal-маршрутам, autobattle-service **молча перестанет ходить**: у него нет ни хелпера заголовка, ни переменной окружения. Это тот же блокер, что в FEAT-162 находили у inventory-service и dungeon-service.
**Возможное решение:** добавить `INTERNAL_SERVICE_TOKEN` autobattle-service в оба compose-файла и хелпер в `clients.py` **до** того, как на `/battles/internal/*` повесят проверку.
**Исправлено (FEAT-169), на упреждение:** `INTERNAL_SERVICE_TOKEN` добавлен autobattle-service в **оба** compose-файла (в prod — строгая форма `:?`), в `app/clients.py` появился `internal_token_headers()`, и оба вызова (`get_battle_state`, `post_battle_action`) его шлют. Сегодня заголовок инертен — `/battles/internal/*` ещё не проверяет ничего, — но когда до этих маршрутов дойдёт общий свип, автобой не умрёт молча. Это самый дешёвый способ снять блокер: слать заголовок в ручку, которая его пока не смотрит, безвредно.
**⚠️ Но блокер снят НЕ полностью:** у `GET /battles/internal/{id}/state` есть второй вызывающий без заголовка — **dungeon-service** (`app/http_clients.py:377`), он опрашивает состояние боя в подземелье. Autobattle застрахован, dungeon — нет. Перед тем как гейтить `/battles/internal/*`, надо обновить и его; подробности — в записи про оставшиеся internal-префиксы ниже.

### ~~Баг: ZSET `battle:deadlines` никто не читает — таймаут хода не срабатывает сам по себе~~ DONE (FEAT-163)
~~**Сервис:** battle-service~~
~~**Обнаружено:** FEAT-161 (Reviewer, 2026-09-14). Предсуществующее, фичей не внесено.~~
**Исправлено в FEAT-163:** у множества появился читатель — фоновый свипер в battle-service (`main.py:5379` `_deadline_sweeper_loop`, стартует из `@app.on_event("startup")` на `main.py:5400`). За тик он делает `ZRANGEBYSCORE battle:deadlines -inf <now> LIMIT 0 50` (`_sweep_due_deadlines`, `main.py:5225`) и засчитывает просрочившему выбывание, поддерживает TTL состояния замороженных боёв (`main.py:5285`) и раз в час сверяется с MySQL по брошенным боям (`main.py:5310`). Течь множества тоже закрыта: при передаче хода запись предыдущего актора теперь снимается (`main.py:2940`), а принудительное завершение боя с истекшим Redis-состоянием перечисляет участников из MySQL и чистит все записи (`_force_finish_battle`, `main.py:3965`). `TURN_TIMEOUT_HOURS` и `BATTLE_STATE_TTL_HOURS` вынесены в оба compose-файла. Подробности — `docs/services/battle-service.md`, раздел «FEAT-163».

### Баг: `settings.EQUIPMENT_SERVICE_URL` не существует, падение маскируется тестом
**Сервис:** character-service
**Файлы:** `app/crud.py:224` (`send_equipment_slots_request`), `app/config.py:9-13`, `app/tests/test_http_helpers.py:32-35`
**Обнаружено:** FEAT-154 (Codebase Analyst, 2026-09-06)
**Описание:** `crud.py:224` обращается к `settings.EQUIPMENT_SERVICE_URL`, но `config.py` эту настройку не объявляет. Pydantic v1 `BaseSettings` запрещает лишние атрибуты, поэтому вызов падает с `AttributeError`, если переменную не подставит недокументированный env. Тест `test_http_helpers.py` навешивает атрибут через `object.__setattr__` на импорте — набор тестов зелёный, а прод-путь сломан. Вызов лежит **на пути одобрения заявки** на персонажа.
**Исправление:** объявить настройку в `config.py` и в `docker-compose.yml`, убрать подмену из теста.

### Баг: таймер кулдауна перемещения никогда не отображается — `/users/me` не отдаёт `travel_cooldown_until`
**Сервис:** user-service (+ frontend consumer)
**Файлы:**
- `services/user-service/schemas.py` (класс `CharacterShort`, ~строка 66) — поле `travel_cooldown_until` отсутствует в схеме
- `services/user-service/main.py:154` — значение собирается в dict, но затем срезается response_model
- `services/frontend/app-chaldea/src/components/pages/LocationPage/LocationPage.tsx:59-90` — UI-таймер читает `character.travel_cooldown_until`, который никогда не приходит
**Описание:** `MeResponse.character` типизирован как `CharacterShort`, в котором нет поля `travel_cooldown_until`. Pydantic отфильтровывает поле из ответа `/users/me`, хотя main.py его подставляет (и frontend-тип `userSlice.ts` его ожидает). В результате блок «Перемещение будет доступно через N мин M сек» на странице локации никогда не показывается, кулдаун виден только как ошибка при попытке перемещения. Баг существовал до FEAT-152 (обнаружен Reviewer при live-проверке FEAT-152, 2026-07-17). Фикс: добавить `travel_cooldown_until: Optional[datetime/str] = None` в `CharacterShort`.
**Приоритет:** HIGH (нерабочая пользовательская функция)
### Долг: инкремент очков активности блокирует горячий путь отправки сообщения в чат
**Сервис:** notification-service
**Файл:** `services/notification-service/app/chat_routes.py` (`send_message`, шаг 9)
**Описание:** пользовательский запрос на отправку сообщения синхронно ждёт до 3 секунд (`timeout=3`) на не-критичном fire-and-forget вызове `POST {AUTH_SERVICE_URL}/users/internal/{id}/activity/increment`. Вызов best-effort (ошибка логируется как WARNING и не ломает отправку), но он всё равно стоит в горячем пути.
**Что сделать:** вынести инкремент активности в `BackgroundTasks`.
**Приоритет:** MEDIUM

**~~Хрупкость теста: rate limiting зависел от скорости отказа внешнего вызова~~ — DONE (FEAT-169 #17, 2026-09-20).** `TestRateLimiting` падал (`assert 201 == 429`) там, где хост `user-service` резолвился медленно: незамоканный `requests.post` занимал ~4 с на отправку и выносил тест за 2-секундное окно лимита. Исправлено autouse-фикстурой `mock_activity_increment` в `services/notification-service/app/tests/conftest.py` — теперь ни один чат-тест не ходит в сеть. Проверено: без обходного `AUTH_SERVICE_URL=http://127.0.0.1:1` полный `test_chat.py` проходит за 1.14 с (раньше — секунды на каждую отправку), два подряд прогона всей сюиты зелёные.

### Долг: list_characters держит сессию БД через N последовательных HTTP-вызовов
**Сервис:** character-service
**Файл:** `services/character-service/app/main.py` (`list_characters`, ~строка 1646)
**Описание:** Эндпоинт делает по одному синхронному `httpx.get` к user-service на каждого уникального `user_id` в выдаче (до 5 с каждый), не закрывая сессию БД, и продолжает пользоваться `db` после. Это тот же паттерн, что вызвал prod-инцидент 2026-09-04 в `get_character_profile`, но здесь эндпоинт объявлен обычным `def` (то есть исполняется в threadpool и не блокирует event loop) и доступен только админам, поэтому риск ниже.
**Что сделать:** батчить запрос имён одним вызовом к user-service либо закрывать сессию до HTTP-фазы. Отдельной задачей — в рамках инцидента не трогалось, чтобы не раздувать дифф.

### Долг: claim_reward держит сессию БД через все HTTP-вызовы выдачи награды
**Сервис:** battle-pass-service
**Файл:** `services/battle-pass-service/app/crud.py` (`claim_reward`, вызов `deliver_reward`)
**Описание:** К моменту выдачи награды в сессии уже прошли несколько SELECT (сезон, уровень, прогресс, награда), то есть транзакция открыта. `deliver_reward` из неё делает от одного до трёх HTTP-вызовов в character-service / inventory-service / user-service (таймаут 10 с каждый), и только потом пишется строка `bp_user_rewards`. Тот же паттерн, что вызвал прод-инцидент 2026-09-04 у character-service; здесь пул отдельный и нагрузка ниже, поэтому приоритет не критичный. Найдено в FEAT-168 (обнаружено при правке #6, существовало до неё).
**Что сделать:** вынести выдачу за пределы транзакции, материализовав нужные поля награды до сетевой фазы. **Нельзя чинить откатом сессии** (`rollback` ради возврата соединения в пул): в async-сессии он протухает загруженные ORM-объекты, и следующее же обращение к их полям падает с `MissingGreenlet` — ровно так сломался первый заход в review #2 FEAT-168.
**Приоритет:** MEDIUM

### Долг: ~93 эндпоинта character-service объявлены `async def`, но ходят в БД синхронно
**Сервис:** character-service
**Файл:** `services/character-service/app/main.py`
**Описание:** Сервис использует синхронный SQLAlchemy, но большинство эндпоинтов — `async def` с `db: Session = Depends(get_db)`. Такие обработчики выполняются прямо в event loop, и каждый синхронный запрос к БД блокирует весь цикл вместо того, чтобы уйти в threadpool. Именно поэтому во время инцидента 2026-09-04 перестал отвечать даже `/openapi.json`, не обращающийся к БД.
**Что сделать:** привести обработчики без `await` к обычному `def` (FastAPI сам уведёт их в threadpool). Менять пачками с прогоном тестов; правка механическая, но затрагивает почти весь файл.

### ~~Баг: locations-service миграция 004 падает на свежей БД (отсутствует таблица `permissions`)~~ DONE (2026-04-08)
~~**Сервис:** locations-service~~
~~**Файлы:** `services/locations-service/app/alembic/versions/004_game_time_config.py`~~
**Исправлено:** В `upgrade()` добавлен defensive guard — блок `INSERT INTO permissions / role_permissions` выполняется только если `inspector.get_table_names()` содержит `permissions`, `roles` и `role_permissions`. Схема (`game_time_config`) создаётся безусловно. `INSERT` заменён на `INSERT IGNORE` для идемпотентности. На prod no-op (таблицы существуют), фикс улучшает только dev/CI/disaster-recovery bootstrap. Проверено: `docker compose up -d locations-service` — миграции проходят 003 -> 028, uvicorn стартует, `curl http://localhost/characters/races` = 200 `[]`.

### Баг: маркеры на карте мира съезжают при нестандартной ширине окна DONE
**Сервис:** frontend
**Файлы:**
- `services/frontend/app-chaldea/src/components/WorldPage/InteractiveMap/InteractiveMap.tsx`
- `services/frontend/app-chaldea/src/components/AdminLocationsPage/FloatingRouteEditor.tsx`
**Описание:** Контейнер карты мира имел `min-h-[300px] md:min-h-[500px]` и `w-full`, то есть его соотношение сторон зависело от ширины окна. Внутри лежал `<img class="w-full h-full object-cover">`, который кропает картинку под контейнер. Все маркеры (clickable zones, локации, плавающие структуры, стрелки) позиционируются в `% left/top` относительно контейнера — поэтому при изменении aspect ratio контейнера они «уезжали» относительно фич карты. Стало особенно заметно при тестировании плавающих структур (FEAT-123).
**Исправление:** Контейнер теперь блокирует aspect ratio под натуральные размеры загруженной картинки (`onLoad` -> `setAspectRatio(`${naturalWidth} / ${naturalHeight}`)`), `min-h-*` убран. `object-cover` остаётся, но теперь идентичен `object-contain`, потому что контейнер совпадает с картинкой по пропорциям. Все существующие маркеры с `% left/top` автоматически выравниваются на любых ширинах окна (от 360px до 1920px+). Аналогичная правка применена к редактору маршрутов, чтобы клики `getBoundingClientRect` тоже маппились в правильные координаты картинки.



### ~~3. Баг: бой не завершается при HP <= 0~~ DONE (FEAT-059, Phase 1)
~~**Сервис:** battle-service~~
~~**Исправлено в FEAT-059:** Добавлена проверка HP<=0 после применения урона. При обнаружении — battle.status='finished' в MySQL, Redis state expire 5 мин, winner_team в ActionResponse. Повторные action на finished battle возвращают 400.~~

### ~~4. Баг: кулдаун навыков не обновляется в dict~~ DONE (FEAT-059, Phase 1)
~~**Сервис:** battle-service~~
~~**Исправлено в FEAT-059:** `remaining -= 1` заменено на `new_val = remaining - 1` с записью `cd_map[rank_id] = new_val`.~~

### ~~5. Баг: дублирование enemy_effects в бою~~ DONE (FEAT-059, Phase 1)
~~**Сервис:** battle-service~~
~~**Исправлено в FEAT-059:** Удалён дублирующий блок apply_new_effects для enemy в секции ATTACK.~~

### ~~6. Memory leak в autobattle-service~~ Частично исправлен (FEAT-071)
~~**Сервис:** autobattle-service~~
~~**Описание:** `LAST_STATS` dict растёт бесконечно — записи никогда не удаляются после завершения боя.~~
**Частично исправлено:** `_cleanup_battle()` добавлена, но cleanup LAST_STATS не работает корректно из-за бага #22 (несовпадение ключей).

### ~~Баг: DoT-эффекты и контроли не работают в боёвке~~ DONE (FEAT-143)
**Проверено Codebase Analyst 2026-09-18 (FEAT-168) по коду на f50284f — запись устарела, исправлено в FEAT-143:**
- периодический урон: `buffs.py:132 tick_periodic_effects()` (+ `_is_periodic_damage` :86), вызывается в `main.py:2906` ДО `decrement_durations` (`main.py:2920`), тикает по владельцу эффекта;
- сложные эффекты-модификаторы раскрываются в движковые каналы: `buffs.py:216 _expand_complex_effect()` (ArmorBreak/Freeze/Electrify/Daze/Wet/Holy/Curse), агрегация — `buffs.py:238`;
- контроли: `buffs.py:94 evaluate_control()` (Stun, Poison:paralysis, Knockdown/Windburn по типу навыка), вызывается в `main.py:2297`, обнуляет навыки и пишет события `control_skip` / `control_block`;
- фронтенд знает тот же словарь: `BattlePage/battleEffects.ts:27-29`, предупреждение игроку — `BattlePage.tsx:751-766`.
Оставлено ниже как исторический контекст.

~~**Сервис:** battle-service~~
~~**Файлы:**~~
- ~~`services/battle-service/app/buffs.py` (строки 5-35 `_normalize_effect`, 38-61 `apply_new_effects`, 64-75 `decrement_durations`)~~
- ~~`services/battle-service/app/main.py:1068`~~
**Описание (устарело):** Все 14 сложных эффектов из `COMPLEX_EFFECTS` (Bleeding, Burn, Poison, ArmorBreak, Stun, Knockdown, Daze, MagicImpact, Freeze, Wet, Electrify, Windburn, Holy, Curse) молча игнорируются боевым движком. `_normalize_effect` распознаёт только префиксы `Buff:` / `Resist:` и StatModifier — всё остальное проваливается в else-ветку и превращается в произвольный атрибут (`bleeding`, `burn`, ...). Эти атрибуты не входят в `inst_attrs = {hp,mana,energy,stamina}`, поэтому `apply_new_effects` не применяет мгновенный урон. На последующих ходах единственный per-turn вызов — `decrement_durations()` — только уменьшает `duration`, но никогда не читает `magnitude` и не вычитает HP. DoT-эффекты сохраняются в state, тикают по длительности, но не наносят урона. Аналогично сломан контроль: `next_actor` в `main.py` не консультируется с `active_effects` для пропуска хода оглушённых целей.
**Impact:** DoT-навыки (кровотечение, ожог, яд) бесполезны в бою. Контролей фактически нет. Замечено пользователем во время тестирования FEAT-125, но баг существовал и до FEAT-125 — это не регресс, а латентный баг боевого движка.
**Решение:** Добавить функцию `tick_dot_effects(state)` в `buffs.py`, вызвать её перед `decrement_durations()` в `main.py:1068`. Контроли — отдельная задача (модификация `next_actor` с чтением `active_effects` для пропуска хода при Stun/Freeze/Knockdown).

### 22. Баг: несовпадение ключей LAST_STATS и HISTORY в autobattle-service
**Сервис:** autobattle-service
**Файл:** `services/autobattle-service/app/main.py`
**Описание:** `build_features()` (строка 189, 227) использует ключ `(turn_number, pid)` для LAST_STATS и HISTORY, но `handle_turn()` (строка 300) записывает в HISTORY с ключом `(bid, pid)`. `_cleanup_battle()` (строки 254-257) ищет записи по `k[0] == bid`, но LAST_STATS хранит `(turn_number, pid)` — очистка не сработает если turn_number != bid. HISTORY имеет смешанные ключи.
**Решение:** Привести все ключи к единому формату `(bid, pid)` в build_features и handle_turn.

### ~~7. Баг: shield нельзя экипировать через API~~ DONE (FEAT-041)
~~**Сервис:** inventory-service~~
~~**Исправлено в FEAT-041:** добавлен `'shield'` во все ENUM-определения (models, schemas, crud) + Alembic-миграция + data backfill для существующих персонажей.~~

### ~~20. GIF-анимация теряется при загрузке аватарки/фона профиля~~ DONE (FEAT-044)
~~**Сервис:** photo-service~~
~~**Исправлено в FEAT-044:** `convert_to_webp` теперь определяет анимированные GIF (`image.format == 'GIF'` + `is_animated`) и сохраняет их как GIF с `save_all=True`, сохраняя все кадры и анимацию. Статические изображения по-прежнему конвертируются в WebP. S3 получает корректный `ContentType` (`image/gif` или `image/webp`).~~

## MEDIUM

~~### Баг: прямой заход по адресу `/rules` даёт 404 — nginx уводит SPA-путь в locations-service~~
~~**Сервис:** api-gateway (nginx) + frontend~~
~~**Обнаружено:** FEAT-173 (Reviewer, live-проверка, 2026-09-20)~~
~~**Описание:** для проксируемого блока `location /rules/` nginx сам отвечал `301` на запрос без завершающего слеша: `GET /rules` → `301 /rules/` → locations-service → `404`. SPA-маршрут `/rules` был недостижим по закладке и работал только при навигации внутри приложения.~~
~~**Исправлено в FEAT-173:** в оба конфига (`nginx.conf`, `nginx.prod.conf`) добавлены точные совпадения `location = /rules` и `location = /rules/` с `return 301 /guide` **до** префиксного блока `/rules/`. Точное совпадение имеет приоритет над префиксом, поэтому закладка на любую форму старого адреса попадает на редирект, а API-пути (`/rules/list`, `/rules/create`, …) не затронуты. Проверено live после пересборки шлюза: `/rules` и `/rules/` → `301 /guide`, `/rules/list` → 200 с четырьмя правилами.~~
~~**Остаётся общий риск:** любой будущий SPA-маршрут, совпадающий с префиксом сервиса, наступит на те же грабли — см. запись ниже про `/characters/list`.~~

### Утечка: снапшот наблюдателя отдаёт характеристики, навыки и пояс любому игроку из той же локации
**Сервис:** battle-service
**Файлы:** `services/battle-service/app/main.py:1555` (`GET /battles/{battle_id}/spectate`), `:305` (`build_participant_info`), `:5288` (WS-push того же снапшота)
**Обнаружено:** FEAT-171 (Reviewer, review #1, 2026-09-19); подтверждено Backend Dev'ом при фиксе логов боя (задача #24, 2026-09-20)
**Приоритет:** MEDIUM
**Описание:** авторизация на `/spectate` есть, но проверяется не участие, а «у меня есть персонаж в этой локации». `build_participant_info` кладёт в снапшот `attributes`, `skills` с уровнями, `fast_slots` и `equipment_durability` **каждого** участника, поэтому любой игрок может дойти до локации и прочитать полную сборку чужого персонажа — ровно те цифры, которые FEAT-171 закрыла на профиле. То же тело уходит в WebSocket-push.
**Почему не исправлено в FEAT-171:** это **отдельный путь кода** от логов боя — свой обработчик, своя сборка тела; гейт логов (задача #24) его не затрагивает. Сузить его — продуктовое решение: надо решить, что наблюдателю вообще положено видеть (скорее всего hp/mana/stamina/energy и имена, как в `/preview`), иначе сломается режим наблюдения. Расширять этим объём фикса по ревью было бы подменой решения пользователя.
**Возможное решение:** оставить наблюдателю только рантайм-часть (hp/mana/энергия/выносливость + имя и аватар из снапшота), а `attributes`/`skills`/`fast_slots`/`equipment_durability` отдавать лишь участникам боя. Гейт логов боя (`battle_visibility.can_view_battle_logs`) сознательно повторяет правило `/spectate`, поэтому сужать их надо **вместе** — иначе панель логов у наблюдателя перестанет работать, а более богатый снапшот всё равно останется открытым.

### Долг: регистрации автобоя живут в памяти процесса и теряются на каждом деплое
**Сервис:** autobattle-service
**Файл:** `services/autobattle-service/app/main.py:119-126` (`ALLOWED`, `PID_BATTLE`, `SPEED`, `OWNER`)
**Обнаружено:** FEAT-170 (Architect §3.14, зафиксировано Backend Dev в задаче #4, 2026-09-19). Предсуществующее, фичей не внесено.
**Приоритет:** MEDIUM
**Описание:** список участников под управлением ИИ хранится в обычных словарях процесса, а не в Redis. Любой рестарт контейнера (а CI-деплой делает `down` + `up --build` по всему стеку) стирает их: моб или автоведомый персонаж в уже идущем бою просто перестаёт ходить, пока его не зарегистрируют заново. Ошибки при этом нет — бой «зависает» на чужом ходу до таймаута. Побочный эффект для проверок: «ходит ли моб после деплоя» — слабый сигнал, живую проверку автобоя надо делать на **свежесозданном** бою.
**Возможное решение:** перенести регистрации в Redis (там уже лежит состояние боя), либо восстанавливать их при старте по активным боям с участниками-НПС.

### Долг: оценка перков тянет весь `/full_profile` ради одного поля и транзитивно дёргает inventory-service
**Сервис:** character-attributes-service
**Файл:** `services/character-attributes-service/app/perk_evaluator.py:63` (`_fetch_gold_balance`)
**Обнаружено:** FEAT-168 (Backend Dev + Reviewer, 2026-09-19). Предсуществующее, фичей не внесено.
**Приоритет:** MEDIUM
**Описание:** чтобы узнать баланс золота, вызывается блокирующий `httpx.get` на character-service `/full_profile` с таймаутом 5 с. Вызов идёт из синхронного обработчика (значит, в threadpool, цикл событий не блокируется) и fail-open, поэтому это не авария. Но ради одного поля выкачивается весь профиль, а после FEAT-168 `/full_profile` стал тяжелее: при повышении уровня он может запустить выдачу титулов и запрос множителя опыта в inventory-service, то есть оценка перков транзитивно доходит до инвентаря. В нагруженные моменты уже наблюдался `Failed to fetch gold balance … timed out`.
**Возможное решение:** лёгкий внутренний эндпоинт «только баланс золота» (или передавать баланс в вызов оценки перков), плюс таймаут поменьше.

### ~~Баг: событие `item_broken` не переводится в журнале боя~~ — DONE (FEAT-168)
**Исправлено в FEAT-168:** у `formatBattleEvent` появилась ветка `item_broken` со словарём слотов по-русски (`EQUIPMENT_SLOT_LABELS`), а общий fallback больше никогда не печатает английское имя события — он берёт название из локальной таблицы `EXTRA_EVENT_LABELS`, а в крайнем случае пишет нейтральное «совершает действие». Заодно добавлены ветки для всех новых событий FEAT-168 (`item_rejected`, `weapon_coating_applied`, `weapon_coating_expired`, `effects_removed`) и выносливость в `item_use`.

**Сервисы:** battle-service, frontend
**Файлы:** `services/battle-service/app/main.py:2849, 2860`; `services/frontend/app-chaldea/src/components/pages/BattlePage/BattlePageBar/BattlePageBar.tsx:462-656`; `services/frontend/app-chaldea/src/helpers/commonConstants.js:29-34`
**Обнаружено:** FEAT-168 (Codebase Analyst, 2026-09-18), по коду.
**Описание:** движок шлёт `{"event": "item_broken", "who": …, "slot": …}` при обнулении прочности, но у `formatBattleEvent` нет ветки для этого типа, а в `BATTLE_EVENTS_TRANSLATE` всего четыре ключа (`apply_effects`, `damage`, `resource_spend`, `item_use`). Срабатывает общий fallback (`BattlePageBar.tsx:644-655`) и игрок видит в журнале английскую строку `item_broken` вместо «Сломалось: нагрудник». Так же поведут себя любые новые типы событий.
**Возможное решение:** ветка в `formatBattleEvent` со словарём слотов по-русски; заодно завести правило «новый тип события = новая ветка в том же PR».

### Баг: синхронизация опыта при смене уровня тихо падает — character-service дёргает RBAC-роут без токена
**Сервисы:** character-service, character-attributes-service
**Файлы:** `services/character-service/app/main.py:747-772`
**Обнаружено:** FEAT-167 (Codebase Analyst, 2026-09-18), по коду; вживую не проверялось.
**Описание:** при смене уровня персонажа (админкой) character-service читает `GET /attributes/{id}/passive_experience`, а затем, если опыта не хватает, PUT-ит `/attributes/admin/{id}` — а этот роут защищён `require_permission("characters:update")` (`character-attributes-service/app/main.py:1083-1088`). Никакого `Authorization` character-service не отправляет, поэтому получает 403, пишет warning (`main.py:766-772`) и продолжает как будто всё хорошо. Итог: уровень меняется, `passive_experience` под него не подтягивается. Классический тихий отказ.
**Возможное решение:** либо отдельный internal-роут в char-attrs под `verify_internal_token` для этой синхронизации, либо честно пробросить админский токен вызывающего. Заодно перестать проглатывать 4xx на этом вызове.
**⚠️ Уточнение (Reviewer, FEAT-167, 2026-09-18) — описание выше неверно.** Токен как раз отправляется: `admin_update_character` получает его через `Depends(OAUTH2_SCHEME)` и передаёт `headers = {"Authorization": f"Bearer {token}"}` **и** в `GET .../passive_experience`, **и** в `PUT /attributes/admin/{id}` (`services/character-service/app/main.py:742-760`). Значит для админа с правом `characters:update` синхронизация должна работать, и описанный механизм «403 из-за отсутствия заголовка» не подтверждается. Запись нужно перепроверить вживую (сменить уровень персонажа админкой и посмотреть `passive_experience`) и либо переписать под настоящую причину, либо удалить. Проглатывание 4xx на этом вызове — реальная часть, она остаётся. §2.3 и §3.7 FEAT-167 повторяют то же неверное утверждение.

### Долг: `compute_derived_stats` затирает накопленные бонусы `damage` при пересчёте
**Сервис:** character-attributes-service
**Файл:** `services/character-attributes-service/app/crud.py:39-65` (сид `attr.damage = <главная характеристика класса>` на 63)
**Обнаружено:** FEAT-167 (Architect §3.8.3 / Backend Dev, 2026-09-18)
**Описание:** `/{id}/recalculate` и `/admin/recalculate_all` пересобирают `damage` из главной характеристики класса и тем самым стирают всё накопленное через `apply_modifiers` — бонусы перков, брони и украшений (их заточку и камни), баффы и еду. Дальше движок боя ещё раз прибавляет главную характеристику (`battle_engine.compute_damage_with_rolls`), то есть после пересчёта она учтена дважды, а неоружейные бонусы потеряны до следующего пере-экипирования. Предсуществующее, FEAT-167 это не менял; после FEAT-167 пересчёт больше не «возвращает» и урон оружия — но это как раз правильно (урон оружия живёт в `effective_damage` слота).
**Возможное решение:** либо сделать `damage` полностью производным (не сидировать главной характеристикой, а собирать из фактической экипировки и перков), либо убрать главную характеристику из сида, раз движок и профиль прибавляют её сами. Требует отдельной задачи с пересчётом данных.

### Баг: страница боя на 360px вылезает за экран, карточки бойцов перекрывают слоты навыков
**Сервис:** frontend (страница боя, `components/pages/BattlePage/`)
**Обнаружено:** FEAT-166 (Frontend Dev T2, 2026-09-18), вживую в headless-браузере; скриншот `dbg-battle-load-360.png` в scratchpad сессии. Предсуществующее, фичей не внесено.
**Описание:** на ширине 360px страница боя прокручивается по горизонтали, а карточки бойцов перекрывают слоты навыков — обычным касанием до слотов не достать. Проявляется ещё до открытия выбора навыка.
**Возможное решение:** адаптивная раскладка страницы боя (стопка на мобильных, `min-w-0`, без фиксированных ширин), проверка на 360px.

### Баг: админ не может вернуть рецепт из «базовых» в «изучаемые по предмету»
**Сервис:** inventory-service (`app/crud.py`, `update_recipe`)
**Обнаружено:** FEAT-165 (Backend Dev, 2026-09-18), проверено по коду.
**Описание:** `update_recipe` применяет поля через `if value is not None: setattr(...)`, поэтому явный `"auto_learn_rank": null` в `PUT /inventory/admin/recipes/{id}` молча игнорируется. Рецепт, однажды ставший базовым (выдаётся по рангу), нельзя снова сделать изучаемым из предмета-рецепта: поле не сбрасывается, предмет-рецепт не создаётся, а ответ 200 выглядит как успех. Та же ловушка у остальных nullable-полей рецепта (`description`, `icon`, `xp_reward`).
**Возможное решение:** для nullable-полей применять значение, если ключ есть в `exclude_unset`-словаре (включая `None`), и в ветке синхронизации предмета-рецепта проверять `"auto_learn_rank" in update_data`, а не истинность значения. Добавить тест «auto_learn_rank → null создаёт предмет-рецепт».

### Долг: админские эндпоинты боёв не отдают `is_paused` / `pause_reason`
**Сервис:** battle-service (потребитель — фронтенд, `components/Admin/BattlesPage/AdminBattlesPage.tsx`)
**Обнаружено:** FEAT-163 (Frontend Dev, задача #14, 2026-09-14). Сверено с живым `/openapi.json` — совпадает с кодом.
**Описание:** `AdminBattleListItem` (`schemas.py:221`) и словарь `battle` в `GET /battles/admin/{id}/state` (`main.py:3904-3909`) не содержат ни `is_paused`, ни `pause_reason`, хотя колонки в таблице `battles` есть и `LocationBattleItem` своё `is_paused` отдаёт. Из-за этого админский контрол заморозки/разморозки (FEAT-163) не может показать текущее состояние боя до первого вызова freeze/unfreeze и вынужден показывать обе кнопки сразу, полагаясь на честный 400 «Бой не приостановлен» от бэкенда.
**Возможное решение:** добавить `is_paused: bool` и `pause_reason: Optional[str]` в `AdminBattleListItem` и в `battle_dict` админского state-эндпоинта — аддитивно, обратная совместимость не ломается. Фронтенд уже типизировал оба поля как необязательные и подхватит их без правок.

### Долг (Stage 2): бэкенд отдаёт все временные метки без часового пояса
**Сервисы:** все 10 backend-сервисов
**Обнаружено:** FEAT-161 (Architect, разделы 2.2/3.1; подтверждено Reviewer 2026-09-14). Сознательно вынесено за пределы FEAT-161.
**Описание:** `created_at`/`updated_at` и прочие `DateTime`-колонки — наивный UTC (`server_default=func.now()` или `datetime.utcnow()`), `json_encoders` нет нигде, поэтому FastAPI/Pydantic v1 сериализует их без смещения: `"2026-03-23T10:23:58"` (проверено вживую на `GET /locations/game-time` и `GET /locations/posts/latest`). Клиент обязан угадывать, что это UTC. FEAT-161 закрыл симптом на фронтенде общим терпимым к смещению парсером `src/utils/serverDate.ts`, но корень остался: любой новый потребитель (мобильный клиент, внешняя интеграция, скрипт) получит ту же ловушку.
**Почему это не одна правка:** (1) ~160 блоков `class Config:` в 10 сервисах, которым нужен общий базовый класс с `json_encoders`; (2) **22 места с ручным `.isoformat()` в обход Pydantic**, которые `json_encoders` не покроет вообще: `notification-service/app/messenger_routes.py:652,796`, `notification-service/app/messenger_ws_handler.py:221,325,327,342`, `inventory-service/app/crud.py:2089,2090,2448,2984`, `inventory-service/app/main.py:1120,1333,3437`, `character-service/app/main.py:424,1975,3674`, `battle-service/app/main.py:1665,2817,3795`, `battle-service/app/redis_state.py:133`, `dungeon-service/app/gameplay.py:3627`, `skills-service/app/crud.py:557`; (3) выкатывается не атомарно — во время раскатки часть эндпоинтов отдаёт смещение, часть нет, поэтому клиент обязан быть терпимым к смещению **до** правки бэкенда (это и сделала FEAT-161, так что Stage 1 — предпосылка для Stage 2, а не замена ему).
**Побочные эффекты, которые надо учесть:** `skills-service/app/tests/test_character_skill_reset.py:128` вычитает наивное время из разобранного ответа — при появлении смещения упадёт с `TypeError`. `locations-service/app/main.py:1194,1457` уже терпимы к обеим формам, ломать межсервисные вызовы Stage 2 не должен.
**Возможное решение:** общий Pydantic-базовый класс с `json_encoders={datetime: lambda v: v.replace(tzinfo=timezone.utc).isoformat()}` + отдельный проход по 22 ручным местам; выкатывать сервис за сервисом.

### ~~Долг: оставшиеся internal-префиксы (battles, dungeons, battle-pass, locations, users/diamonds) защищены только nginx~~ DONE (FEAT-170, 2026-09-19)
**Сервисы:** battle-service, dungeon-service, battle-pass-service, locations-service, user-service, autobattle-service
**Обнаружено:** FEAT-162 (DevSecOps, аудит internal-префиксов 2026-09-14). **Сужено после FEAT-169** — большая часть исходного перечня закрыта, актуальный остаток см. в конце записи.
**Описание:** после FEAT-162 все internal-префиксы закрыты в обоих nginx-конфигах (`return 403`), но второй слой — проверка `X-Internal-Token` через `Depends(verify_internal_token)` — стоял на момент обнаружения лишь на 6 эндпоинтах из ~33 (к 2026-09-14 — на 16: все 14 под `/characters/internal/` и 2 под `/locations/internal/`): `character-service` (`/characters/internal/{id}/update_location`, `/characters/internal/{id}/set_travel_cooldown`, `/characters/internal/{id}/deduct_points`, `POST /characters/internal/{id}/logs`) и `locations-service` (`/locations/internal/cancel-gathering`, `/locations/internal/character-left-location`). Остальные (`/attributes/internal/{id}/reconcile-perks`, `/locations/internal/gathering-status`, `/locations/internal/action-gate*`, `/locations/quests/internal/*`, `/users/internal/*`, `/inventory/internal/*`, `/battles/internal/*`, `/dungeons/internal/*`, `/party/internal/*`, `/battle-pass/internal/track-event`, `/autobattle/internal/register`) не проверяют ничего: любой контейнер в compose-сети (или скомпрометированный сервис) может их дёргать. Проверено вживую: до правки nginx `POST /attributes/internal/1/reconcile-perks` через gateway без каких-либо заголовков возвращал `200`.
**Почему не критично:** снаружи всё закрыто gateway'ем (`403`), порты сервисов в prod наружу не открыты — эксплуатация требует доступа внутрь compose-сети.
**Возможное решение:** добавить `Depends(verify_internal_token)` на оставшиеся internal-эндпоинты, вынеся хелпер в общий модуль; выкатывать сервис за сервисом, синхронно с `INTERNAL_SERVICE_TOKEN` у вызывающих.
**Дополнено (Backend Dev, 2026-09-14, аудит `/characters/internal/`):** перечислены **все 14** роутов под этим префиксом. Было защищено 4, стало 6 — добавлен `Depends(verify_internal_token)` на `POST /characters/internal/unlink` (отвязывает любого персонажа от аккаунта по id — самый весомый из незакрытых) и на `POST /characters/internal/evaluate-titles`; вызывающие обновлены синхронно (`battle-service/app/main.py` — unlink; `character-attributes-service/app/main.py` x2 и `inventory-service/app/main.py` x2 — evaluate-titles). Заодно закрыт блокер: у `inventory-service` вообще не был проброшен `INTERNAL_SERVICE_TOKEN` в `docker-compose.yml` — добавлен (prod наследует `environment` из базового файла).

**Дополнено (Backend Dev, 2026-09-14, закрытие остатка):** оставшиеся **8** роутов
`/characters/internal/` («мобо-подземельный» кластер) закрыты — под префиксом теперь
защищены **все 14 из 14**. Вызывающие обновлены синхронно, каждый проверен вживую:

| Роут | Вызывающий (проверен) |
|---|---|
| `POST /internal/try-spawn` | `locations-service/app/main.py:88` (`_try_spawn_mob`) |
| `GET /internal/mob-pack/{active_pack_id}` | `battle-service/app/main.py:961` (`_get_pack_roster`) |
| `GET /internal/mob-reward-data/{character_id}` | `battle-service/app/main.py:270` (`_distribute_pve_rewards`) |
| `PUT /internal/active-mob-status/{character_id}` | `battle-service/app/main.py:309` (то же) |
| `PUT /internal/npc-status/{character_id}` | `battle-service/app/main.py:2015` (`_finalize_battle`) |
| `POST /internal/record-mob-kill` | `battle-service/app/main.py:372` (`_distribute_pve_rewards`) |
| `POST /internal/spawn-dungeon-mobs` | `dungeon-service/app/http_clients.py:131` |
| `POST /internal/deduct-gold` | `dungeon-service/app/http_clients.py:428` |

Заодно закрыт блокер: у `dungeon-service` не был проброшен `INTERNAL_SERVICE_TOKEN` —
добавлен в `docker-compose.yml` **и** в `docker-compose.prod.yml` (prod переопределяет
весь блок `environment` этого сервиса, поэтому наследования из базового файла не было).
`battle-service` и `dungeon-service` получили хелпер `_internal_token_headers()` по образцу
`character-attributes-service` / `inventory-service`.

24 теста в 5 файлах `character-service` дёргали эти роуты без заголовка — исправлено
механически (пин `auth_http.INTERNAL_SERVICE_TOKEN` + `headers=`), ни одно утверждение
не изменено: `test_add_rewards.py`, `test_bestiary.py`, `test_mob_packs.py`,
`test_mob_spawning.py`, `test_npc_status.py`.

**Остаётся пробел в покрытии:** у `POST /internal/spawn-dungeon-mobs` и
`POST /internal/deduct-gold` в `character-service` нет ни одного теста — ни до правки,
ни после (задача для QA).

**Сопутствующий пробел в тестах:** `battle-service/app/tests/test_pvp_death_duel.py::test_loser_character_unlinked` не вызывает `_finalize_battle`, а переписывает httpx-вызов у себя в теле — поэтому он **не поймал бы** отсутствие заголовка у настоящего вызывающего. Тест стоит переписать на реальный прогон функции (задача для QA).

**Дополнено (FEAT-162, задача 14, 2026-09-14):** полный аудит всех 99 роутов `character-service/app/main.py` (см. §3.4) не нашёл больше ни одного *публично маршрутизируемого* незащищённого write-эндпоинта. Отдельно стоит `POST /characters/{character_id}/add_rewards` — он **не** под префиксом `/internal/`, его закрывает точечное правило nginx (`location ~ ^/characters/\d+/add_rewards$ { return 403; }` в обоих конфигах), но `verify_internal_token` на нём нет, то есть он держится ровно на одном слое и относится к этому же долгу.

**Актуализировано (FEAT-169, 2026-09-19).** Исходная формулировка «большинство internal-эндпоинтов» устарела — большинство как раз закрыто. Закрыты и из этой записи вычеркнуты: все 14 под `/characters/internal/` (FEAT-162), весь `/attributes/internal/`, весь `/inventory/internal/`, весь `/party/internal/` (включая `active-members`), `/skills/internal/`, `POST /users/internal/{uid}/activity/increment`, `POST /locations/quests/internal/progress/update`, а также `POST /characters/{id}/add_rewards` (тот самый «не под префиксом, держится на точечном правиле nginx» из абзаца выше — теперь под `verify_internal_token`).

**Оставалось открытым ровно это (закрыто FEAT-170, см. итог в конце записи):**

| Маршрут | Файл | Вызывающие (и шлют ли заголовок) |
|---|---|---|
| `GET /battles/internal/{id}/state` | `battle-service/app/main.py:1373` | autobattle `clients.py:15` — **шлёт** (FEAT-169, на упреждение); dungeon `http_clients.py:377` — **не шлёт** |
| `POST /battles/internal/{id}/action` | `battle-service/app/main.py:1428` | autobattle `clients.py:23` — **шлёт** |
| `POST /battles/internal/party/leave-on-move` | `battle-service/app/main.py:6363` | locations-service |
| `GET /dungeons/internal/character-session/{cid}`, `POST /dungeons/internal/battle-callback` | `dungeon-service/app/main.py:730`, `:746` | battle-service |
| `POST /battle-pass/internal/track-event` | `battle-pass-service/app/main.py:295` | battle, locations, inventory |
| `GET /locations/internal/gathering-status`, `GET/POST /locations/internal/action-gate`, `/action-gate/consume` | `locations-service/app/main.py:3677`, `:3688`, `:3701` | inventory, character-service |
| `GET /locations/quests/internal/check-completed`, `/completed-count`, `POST /auto-progress` | `locations-service/app/main.py:3153`, `:3175`, `:3198` | battle-service, inventory-service (`auto-progress` — живой, активно используется) |
| `GET/POST /users/internal/{uid}/diamonds`, `/diamonds/add`, `/diamonds/spend`, `/cosmetics/unlock` | `user-service/main.py:1687`, `:1699`, `:1720`, `:2144` | battle-pass, dungeon |
| `POST /autobattle/internal/register` | autobattle-service | battle-service |

**Что тут самое весомое:** четыре маршрута `/users/internal/*diamonds*|cosmetics` — это **мутация валюты**; их стоит брать первыми. Механизм для этого уже готов: FEAT-169 добавил `verify_internal_token` в `user-service/auth.py` и `INTERNAL_SERVICE_TOKEN` во все compose-файлы, так что остаётся только навесить зависимость и обновить вызывающих.

**⚠️ Ловушка, на которую напорется следующий заход:** `GET /battles/internal/{id}/state` опрашивают **двое**, и застрахован только один. autobattle-service заголовок уже шлёт, а **dungeon-service (`app/http_clients.py:377`) — нет**: если гейтить `/battles/internal/*`, не тронув его, опрос боя в подземелье отвалится, и, судя по остальным его вызовам, молча. Первым шагом любой такой задачи должен быть заголовок в dungeon-service, а не зависимость в battle-service.

**Уточнено (Codebase Analyst, FEAT-170, 2026-09-19):** перечень выше пересобран заново AST-обходом
всех декораторов маршрутов и оказался неточным — правильная версия в
`features/FEAT-170-close-remaining-internal-prefixes.md` §2.1–2.2. Коротко: **маршрутов 17, а не 16**
(в таблице отсутствуют `GET /locations/quests/internal/completed-count` и read-only
`GET /locations/internal/action-gate`), **номера строк сдвинуты на 3–9** после FEAT-168/169, и
**вызывающие указаны неверно почти в каждой строке**: `track-event` зовут не «battle, locations,
inventory», а только locations (`main.py:1355`, `:1619`); `action-gate/consume` — не «inventory,
character-service», а battle (`main.py:902`, `:1239`) и dungeon (`http_clients.py:81`);
`gathering-status` — battle ×3 (`:1025`, `:1192`, `:3731`); `diamonds/add` и `cosmetics/unlock` — только
battle-pass (`crud.py:580`, `:594`), dungeon туда не ходит; у обоих `/dungeons/internal/*` вызывающих
**нет вообще** (как и у `diamonds/spend`, `GET diamonds`, `GET action-gate`, `completed-count`).
Всего точек вызова 18 в 6 сервисах, 15 из 18 проглатывают ошибку. Вторая ловушка помимо описанной
выше: в `locations-service/app/main.py` `verify_internal_token` объявлен на `:3743`, **ниже** шести
закрываемых маршрутов (`:3150`–`:3698`) — декоратор выполняется на импорте, так что гейт «на месте»
уронит сервис с `NameError` на старте.

**Исправлено (FEAT-170, 2026-09-19).** Долг закрыт полностью. На **все 17** оставшихся маршрутов
навешен `Depends(verify_internal_token)` (контракт FEAT-162/167: пустой токен → 503
`Internal service token не настроен`, отсутствующий или чужой → 401 `Недействительный internal token`),
и **все 18** точек вызова шлют `X-Internal-Token`. Порядок работ был обратный интуитивному и
обязательный: **сначала заголовки у вызывающих, потом гейты на маршрутах** — иначе описанная выше
ловушка с `dungeon-service/app/http_clients.py:377` уронила бы опрос боя в подземельях. Обе ловушки
из этой записи сняты: в `locations-service/app/main.py` блок `INTERNAL_SERVICE_TOKEN` +
`_internal_token_headers` + `verify_internal_token` **поднят в начало модуля** (с «хлебной крошкой» на
старом месте, чтобы не вернули обратно), имена остались атрибутами `main.*` ради существующих
тестов; в `character-attributes-service/app/perk_evaluator.py` заголовок собирается локально из
`config.settings`, а не импортом из `main` (это цикл). `verify_internal_token` появился в
`auth_http.py` четырёх сервисов: battle, dungeon, battle-pass, autobattle.

Проверено на закрытии независимыми свипами по всему `services/`: **маршрутов с сегментом `internal`
в пути — 57, закрыты 57, открытых 0**; **исходящих вызовов на internal-маршруты — 93, с
`headers=` — 93**. Живьём изнутри compose-сети: без заголовка и с чужим — 401, с верным — штатное
поведение маршрута.

Маршруты без вызывающих (`diamonds/spend`, `GET diamonds`, оба `/dungeons/internal/*`,
`GET /locations/internal/action-gate`, `completed-count`) **закрыты, но не удалены** — удаление не даёт
выигрыша в безопасности поверх токена, а `battle-callback` сам документирован как резерв к опросу.

Отдельно: старые свипы «вызов обязан слать заголовок» были построены на **списках-исключениях** и
поэтому зеленели не по делу — исключённая цель молча выпадала из проверки ровно в тот момент, когда
её закрывали. Они **инвертированы**: теперь под правило попадает любой URL с сегментом `internal`,
без исключений, плюс порог «проверено не меньше N вызовов», чтобы рефактор URL не опустошил свип
незаметно. Аллоу-лист `_KNOWN_UNGATED_TARGETS` в inventory-service удалён вместе с веткой пропуска,
и добавлены тесты, которые падают при попытке вернуть любой такой список.

**Не закрыто этой задачей и живёт отдельными записями:** анонимное чтение чужих данных (инвентарь,
экипировка, характеристики, история чата) — нужно продуктовое решение о публичности;
`GET /attributes/{id}/perks`, который пишет в БД на чтение; регистрации автобоя в памяти процесса.

### ~~Баг: отвязка персонажа не очищает `users.current_character` — UPDATE по несуществующей колонке~~ DONE (2026-09-14)
**Сервис:** character-service
**Файл:** `services/character-service/app/main.py:1053-1062` (`POST /characters/internal/unlink`)
**Описание:** после удаления связи в `user_characters` код выполняет
`UPDATE users SET current_character_id = NULL WHERE id = :uid AND current_character_id = :cid`.
Колонки `current_character_id` в таблице `users` **не существует** — реальное имя `current_character`
(то же самое расхождение «имя поля в API user-service ≠ имя колонки в общей БД», из-за которого
FEAT-123 Мастер Телепорта возвращал 500, см. запись в DONE выше). Запрос всегда падает с
`(1054, "Unknown column 'current_character_id' in 'where clause'")`, но исключение проглочено
`except Exception` c `logger.warning`, поэтому отвязка формально «успешна»: `characters.user_id`
обнуляется, а `users.current_character` продолжает указывать на отвязанного персонажа.
**Проверено вживую (2026-09-14):** тот же UPDATE, выполненный напрямую через движок character-service
на dev-БД, падает с `Unknown column 'current_character_id' in 'where clause'`;
`inspect(engine).get_columns('users')` подтверждает единственную колонку `current_character`.
**Почему тесты это не поймали:** `tests/test_internal_unlink.py` не создаёт зеркальную таблицу `users`
вовсе, так что в SQLite запрос падает ровно так же и точно так же проглатывается — тест зелёный
при полностью неработающем шаге.
**Обнаружено:** FEAT-162, задачи QA #9-#11 (при проверке, что фикстура `users` в `test_teleport.py`
теперь отражает реальную схему).
**Приоритет:** MEDIUM (тихая рассинхронизация данных, а не отказ).
**Исправлено (Backend Dev, 2026-09-14):** в `POST /characters/internal/unlink` колонка приведена к
фактическому имени `current_character` в обоих условиях UPDATE. Попутно найдена **вторая** опечатка
в той же функции: `DELETE FROM user_characters` — такой таблицы нет, реальная называется
`users_character`, и эта ошибка глоталась ровно так же (лог: `(1146, "Table
'fogdatabase.user_characters' doesn't exist")`), то есть связь пользователь↔персонаж при смертельной
дуэли не удалялась вовсе. Оба `except Exception` + `logger.warning` сняты: три записи (DELETE связи,
UPDATE `users`, обнуление `characters.user_id`) объединены в одну транзакцию с единым
`except Exception` → `rollback` + `HTTPException(500)`. Вызывающий (battle-service, `main.py:2603`)
уже логирует `resp.status_code != 200` как ошибку, поэтому 500 не теряется.
**Проверено вживую (2026-09-14):** до правки — `200 OK`, при этом `users_character` = 1 строка,
`users.current_character` = 999807, в логах два проглоченных WARNING. После — `200 OK` и все три
записи применились: `users_character` → 0, `users.current_character` → NULL, `characters.user_id` → NULL.
**Фикстура:** `tests/test_internal_unlink.py` теперь создаёт зеркальные таблицы `users`
(`id`, `current_character`) и `users_character` сырым DDL — без них сырой SQL в SQLite не выполнялся
и тест оставался зелёным при неработающем шаге. **QA:** ассертов на содержимое этих таблиц пока нет —
тест проверяет только `characters.user_id`; их стоит добавить.

### Баг: `POST /skills/assign_multiple` обрывает весь батч на первом ненайденном навыке
**Сервис:** skills-service (потребитель — character-service)
**Файлы:** `services/skills-service/app/main.py:562-566`, вызов из `services/character-service/app/main.py:465-482`
**Обнаружено:** FEAT-154 (Backend Dev, 2026-09-06)
**Описание:** Эндпоинт идёт по списку навыков и на первом отсутствующем делает `raise HTTPException(404, "Навык N не найден")`, то есть **прерывает выдачу целиком**, а не пропускает одну позицию. Навыки, обработанные до сбойного, к этому моменту уже закоммичены — получается частичная выдача без отката и без внятного сигнала вызывающему, какие именно позиции применились.
**Как проявилось:** до FEAT-154 в базе отсутствовал навык id 7 (универсальный подрасовый), который character-service добавлял в конец списка при одобрении заявки. В результате навыки класса выдавались, затем прилетал 404, character-service писал `logger.error` и возвращал `None`. Следы в данных: у персонажей id 754-762 от 0 до 3 навыков вместо полного набора.
**Текущее состояние:** триггер устранён — миграция skills-service `009_subrace_skill` создаёт навык id 7. Но хрупкость осталась: любой некорректный id в списке по-прежнему обрывает выдачу.
**Возможное решение:** пропускать неизвестные id и возвращать в ответе список применённых и список пропущенных, либо делать батч атомарным с откатом. Молча терять часть выдачи нельзя в любом случае.

### ~~Баг: отклонить можно уже одобренную заявку на персонажа~~ DONE (FEAT-154, задача #7)
~~**Сервис:** character-service~~
~~**Файл:** `app/main.py` (эндпоинт reject)~~
~~**Описание:** Эндпоинт отклонения не проверял текущий статус заявки. Заявку со статусом `approved` можно было отклонить: статус сменялся на `rejected`, но созданный персонаж оставался — со статами, стартовым набором, навыками и регистрацией у user-service.~~
~~**Исправлено в FEAT-154 (правило 30a):** перед отклонением проверяется `status == 'pending'`, иначе 409 «Отклонить можно только заявку, ожидающую рассмотрения.». Заодно (правило 30b) слишком длинная причина отказа даёт 400 с русским сообщением вместо 422 от Pydantic.~~

### Долг: осиротевшие аватары в S3 после брошенного создания персонажа
**Сервис:** photo-service, character-service
**Обнаружено:** FEAT-154 (Architect, 2026-09-06). По решению пользователя вынесено в отдельную задачу, не в рамках FEAT-154.
**Описание:** В FEAT-154 аватар загружается в S3 **до** создания персонажа (заявка ещё на модерации). Если игрок бросил мастер на полпути или заявку отклонили, файл остаётся в публичном S3 навсегда. Временного бакета нет, TTL нет, уборщика нет. Правило жизненного цикла S3 применить нельзя: одобренный аватар сохраняет тот же URL, то есть по возрасту объекта отличить брошенный от рабочего невозможно.
**Возможное решение:** периодическая задача, сверяющая объекты в префиксе аватаров заявок со ссылками в `character_requests` и `characters`, с удалением несослаемых старше N дней. Либо загрузка во временный префикс с переносом при одобрении.

### Баг: риск двойной выдачи при одобрении заявки на персонажа (HTTP + RabbitMQ)
**Сервис:** character-service
**Файлы:** `app/main.py:299,317,329` (HTTP-вызовы), `app/main.py:375,382,388` (публикации в RabbitMQ)
**Обнаружено:** FEAT-154 (Codebase Analyst, 2026-09-06)
**Описание:** Одобрение заявки отправляет одни и те же данные по инвентарю, навыкам и атрибутам дважды — синхронно по HTTP и повторно сообщением в очередь. **Уточнено (Architect, FEAT-154):** консьюмеры реально работают (`inventory-service/app/main.py:44` поднимает поток при старте) и содержат проверку идемпотентности (`rabbitmq_consumer.py:35-38` — «если инвентарь уже есть, пропускаем»). Поэтому систематической двойной выдачи нет, остаётся узкая гонка: если консьюмер успеет отработать раньше, чем HTTP-вызов закоммитит инвентарь, проверка идемпотентности не сработает и предметы выдадутся дважды. При частичном сбое одобрение неатомарно и может оставить смешанное состояние.
**Исправление:** убрать дублирующие публикации либо сделать консьюмеров идемпотентными.

### Баг: `CharacterRequest.name` — String(20), а `Character.name` — String(255)
**Сервис:** character-service
**Файлы:** `app/models.py` (`CharacterRequest.name`, `Character.name`), `app/main.py:132`
**Обнаружено:** FEAT-154 (Codebase Analyst, 2026-09-06)
**Описание:** Рассинхрон длины поля имени между заявкой и персонажем. При заявке на присвоение (claim) NPC с длинным именем значение обрезается или MySQL отдаёт ошибку 1406 на `main.py:132`.
**Исправление:** привести `CharacterRequest.name` к String(255) миграцией.

### 41. `add_neighbor` затирает `path_data`, если он не передан вместе со стоимостью
**Сервис:** locations-service
**Файл:** `services/locations-service/app/crud.py::add_neighbor` (ветка `if existing_forward` / `if existing_reverse`)
**Описание:** `POST /locations/{id}/neighbors/` работает как upsert, но при обновлении существующей связи присваивает `path_data = path_data_json` **безусловно**. Если вызвать эндпоинт только ради смены `energy_cost` (не переслав текущие waypoints), нарисованный в `RegionMapEditor` / `AdminPathEditor` путь молча превращается в `NULL`. Ловушка неочевидна, т.к. `GET /locations/{id}/neighbors/` вообще не возвращает `path_data` — получить его для пересылки можно только через `GET /locations/regions/{id}/details`.
**Обходной путь (реализован):** добавлен `PATCH /locations/neighbors/{from}/{to}/cost` (`crud.update_neighbor_cost`), который меняет только стоимость в обе стороны и не трогает `path_data`. Карта мира (`/map`) использует именно его.
**Решение:** Сделать `path_data` в `add_neighbor` необязательным к перезаписи (обновлять только если аргумент явно передан, например через sentinel-значение вместо `None`).

### 42. Граф мира сильно фрагментирован: 131 несвязная компонента
**Сервис:** locations-service (данные, не код)
**Описание:** По текущим данным: 2004 видимых локации, 2000 рёбер, **131 несвязная компонента**, крупнейшая покрывает лишь ~24% локаций (484 шт.), 63 локации полностью изолированы (ни одного соседа). Между регионами существует всего **8 рёбер** на 22 региона. Практическое следствие: для большинства пар локаций маршрут физически не существует, и навигатор на `/map` честно отвечает «маршрут не найден».
**Как посмотреть:** страница `/map`, режим раскраски «Связность» — каждая компонента подсвечена своим цветом, изолированные показаны серым пунктиром; счётчики в панели статистики.
**Решение:** Гейм-дизайнерская задача — дорисовать межрегиональные переходы и подключить изолированные локации. Редактор переходов доступен там же на `/map` (нужно право `locations:update`).

### 43. `POST /locations/{id}/neighbors/update` молча глотает ошибки
**Сервис:** locations-service
**Файл:** `services/locations-service/app/main.py` (обработчик `update_location_neighbors`, блок `try/except`)
**Описание:** Любое исключение перехватывается и превращается в `HTTP 200` с телом `[]`. Клиент не может отличить «соседей нет» от «сохранение упало». Дополнительно `crud.update_location_neighbors` неатомарен (удаление коммитится отдельно от вставки) и **теряет `path_data`**, т.к. пересоздаёт связи без него.
**Решение:** Пробрасывать ошибку (HTTP 500) и выполнять удаление+вставку в одной транзакции; сохранять `path_data` при пересоздании.

### 44. `RegionMapEditor` читает несуществующее поле `icon_url` в ответе photo-service
**Сервис:** frontend
**Файл:** `services/frontend/app-chaldea/src/components/AdminLocationsPage/RegionMapEditor/RegionMapEditor.tsx` (~строка 619)
**Описание:** `iconResp.data?.icon_url ?? iconResp.data?.map_icon_url` — `POST /photo/change_location_icon` возвращает только `map_icon_url`, ключа `icon_url` не существует. Первая ветка всегда `undefined`, работает лишь фолбэк. Безвредно сейчас, но вводит в заблуждение.
**Решение:** Убрать несуществующий ключ, оставить `map_icon_url`.


### 11. Celery подавляет ошибки при записи логов боёв
**Сервис:** battle-service
**Файл:** `services/battle-service/app/tasks.py:29`
**Описание:** `contextlib.suppress(Exception)` маскирует любые ошибки записи в MongoDB/Redis. Логи боёв могут теряться без каких-либо следов.
**Решение:** Заменить на try/except с логированием ошибки.

### 30. N+1 HTTP-запросов в BattlesSection при каждом polling-цикле
**Сервис:** frontend (+ нагрузка на battle-service)
**Файл:** `services/frontend/app-chaldea/src/components/pages/LocationPage/BattlesSection.tsx:49-69, 71-97`
**Описание:** После каждой загрузки списка боёв `checkExistingRequests()` последовательно вызывает `fetchJoinRequests(battle.id)` для КАЖДОГО боя в локации. При polling каждые 10 секунд это даёт N дополнительных запросов к battle-service каждые 10 с на каждого зрителя страницы локации. При 10 активных боях и 20 игроках на странице — 200 запросов / 10 с. Запросы выполняются последовательно (`for ... await`), что дополнительно растягивает цикл.
**Решение:** Отдавать признак «моя заявка подана» batch-эндпоинтом battle-service (например, поле `has_my_request` прямо в `/battles/by-location/{id}`), либо запрашивать заявки только для развёрнутой секции и параллельно (`Promise.all`).

### 13. Опечатки в названиях полей БД
**Сервис:** character-attributes-service
**Файл:** `services/character-attributes-service/app/models.py`
**Описание:** `res_catting` (вероятно `res_cutting`), `res_watering` (вероятно `res_water`), `res_sainting` (вероятно `res_holy`). Эти же названия продублированы в inventory-service (модификаторы предметов) и battle-service (расчёт урона).
**Решение:** Миграция БД для переименования полей + обновление кода во всех сервисах.

### 14. Синтаксическая ошибка в redis_state.py
**Сервис:** battle-service
**Файл:** `services/battle-service/app/redis_state.py:91-92`
**Описание:** Пропущена закрывающая скобка в dict comprehension при инициализации state.
**Решение:** Исправить синтаксис.

### ~~15. Polling вместо WebSocket на BattlePage~~ DONE (FEAT-074)
~~**Сервис:** frontend~~
~~**Исправлено в FEAT-074:** Polling заменён на WebSocket (`/battles/ws/{battle_id}`). Оба игрока получают обновления мгновенно. Авто-переподключение с exponential backoff, fallback на polling при неудаче. Автобой тоже через WebSocket + управление скоростью (быстрый/медленный режим).~~

~~### 23. Баг: GET /attributes/admin/perks недоступен из-за конфликта роутов~~
~~**Сервис:** character-attributes-service~~
~~**Файл:** `services/character-attributes-service/app/main.py`~~
~~**Исправлено в FEAT-078:** Perks-роуты (GET /{character_id}/perks, GET/POST/PUT/DELETE /admin/perks/*) перенесены выше catch-all роута GET /{character_id}. FastAPI теперь матчит специфичные пути первыми.~~

---

### Долг: `posts.content` — `TEXT` (64 КБ), длинный ролевой пост может молча обрезаться
**Сервис:** locations-service
**Файл:** `services/locations-service/app/models.py:165`
**Обнаружено:** FEAT-156 (Architect, 2026-09-13). Предсуществующее, вне области фичи.
**Описание:** Колонка объявлена как `Column(Text, ...)`, то есть потолок 64 **КБ**. Кириллица в `utf8mb4` стоит 2 байта на символ, а TipTap кладёт в то же поле HTML-разметку — длинный ролевой пост с форматированием реально способен подойти к границе. MySQL в нестрогом режиме обрежет текст **молча**, то есть игрок потеряет часть уже отправленного поста и не узнает об этом.
**Почему не починено в FEAT-156:** новая таблица `post_drafts` сделана с `MEDIUMTEXT` именно из-за этого риска, но саму таблицу `posts` фича не трогала — это отдельная миграция с `ALTER TABLE` на живых данных.
**Возможное решение:** миграция `posts.content` → `MEDIUMTEXT` плюс серверная проверка длины с русским 400, по образцу `MAX_DRAFT_LENGTH` в `locations-service/app/crud.py:34`.

### Долг: `delete_character` не чистит `posts` / `post_likes` / `action_gates` — строки осиротевают
**Сервис:** character-service (владельцы таблиц — locations-service)
**Файлы:** `services/character-service/app/main.py:1121` (`delete_character`), `services/locations-service/app/models.py` (`Post`, `PostLike`, `ActionGate`)
**Обнаружено:** FEAT-156 (Architect, 2026-09-13)
**Описание:** Удаление персонажа — жёсткое (`db.delete(character)`), и перед ним идёт веерная graceful-очистка в inventory-, skills-, character-attributes- и user-service, а с FEAT-156 ещё и в locations-service (шаг 4.5, эндпоинт D7). Но D7 удаляет **только** `post_drafts`. Ни у одной таблицы locations-service нет внешнего ключа на `characters`, поэтому `posts`, `post_likes` и `action_gates` удалённого персонажа остаются в базе со ссылкой на несуществующий `character_id` — так происходит уже сейчас, до FEAT-156.
**Почему не расширено в FEAT-156:** это продуктовое решение, а не технический недосмотр. Удаление `posts` вырвало бы куски из общего отыгрыша локации, который читают посты других игроков — необратимая правка чужого контента. Обоснование целиком: раздел 3.12 «Why drafts only» в `features/FEAT-156-rp-post-drafts.md`.
**Требуется решение пользователя:** удалять посты удалённого персонажа, обезличивать их или оставлять как есть. До этого решения расширять D7 нельзя.

### Долг: `move_and_post` коммитит пост до перемещения персонажа и списания стамины
**Сервис:** locations-service
**Файл:** `services/locations-service/app/main.py:1213` (`crud.create_post`) против `:1241` (500 «Не удалось обновить локацию персонажа») и `:1256` (500 «Не удалось списать выносливость за переход»)
**Обнаружено:** FEAT-156 (QA, задача T4, 2026-09-13). Предсуществующее, фичей не внесено.
**Описание:** `crud.create_post` (`app/crud.py:957`) делает `session.commit()` сразу. Обновление локации в character-service и списание стамины в character-attributes-service идут **после** и каждое имеет свою ветку `raise HTTPException(500)`. Если сработает любая из них, пост уже записан и виден в локации, а персонаж остался в старой локации с несписанной выносливостью — то есть отыгрыш и состояние мира разъехались. Откатить commit на этом месте нечем: соседние сервисы правятся по HTTP, общей транзакции нет.
**Тот же порядок** повторяется в `quick_move` (`:1470` / `:1477`).
**Почему заведено, а не починено:** это вопрос проектирования (сага/компенсация либо перенос вставки поста в самый конец), а не очевидный дефект, и он старше FEAT-156.
**Возможное решение:** создавать пост последним шагом, либо добавить компенсацию — удалять только что созданный пост при провале шагов 6/7 и отдавать вменяемую русскую ошибку.

### Долг: `strip_html_tags` вырезает теги без разделителя и не декодирует энтити — влияет на `char_count`, опыт и гейты
**Сервис:** locations-service (+ зеркало на фронте)
**Файлы:** `services/locations-service/app/crud.py:140-142` (`strip_html_tags`), `services/locations-service/app/tests/test_post_xp.py:35,38`, зеркало на фронте — `services/frontend/app-chaldea/src/components/pages/LocationPage/gateConstants.ts:90` (`stripHtmlTags`; во FEAT-159 переехало из `PostCreateForm.tsx`)
**Обнаружено:** FEAT-157 (Architect, 2026-09-13). Осознанно вынесено из фичи.
**Описание:** Теги удаляются без подстановки разделителя, поэтому `<p>Один</p><p>Два</p>` превращается в `"ОдинДва"` — два слова склеиваются на границе абзацев. HTML-энтити (`&nbsp;`, `&amp;`) не декодируются и считаются как литералы. Тест `test_post_xp.py:35,38` **закрепляет** неправильное поведение, ожидая `"line oneline two"`.
**Почему не исправлено в FEAT-157:** функция считает `char_count` поста, а от него зависят опыт за пост и пороги гейтов. Любая правка меняет длину **всех** постов, то есть это **изменение баланса**, а не тихий багфикс — решение за пользователем. Фронтовый `stripHtmlTags` обязан байт-в-байт зеркалить бэкенд, иначе счётчик символов будет обещать гейт, который сервер откажется засчитать; поэтому во FEAT-157 он тоже оставлен как есть (для спеллчекера сделана отдельная корректная модель смещений).
**Возможное решение:** вставлять `\n` на границах блочных тегов и декодировать энтити, одновременно правя `test_post_xp.py` и согласовав с пользователем пересчёт порогов опыта/гейтов.

### ~~Бэкенд отдаёт `length` поста как длину сырого HTML, а не текста~~ DONE (исправлено в источнике)
**Сервис:** locations-service (+ потребитель на фронте)
**Файлы:** `services/locations-service/app/crud.py:1587`, `services/locations-service/app/crud.py:2324` — `"length": len(post.content)`; схемы `PostResponse.length` (`schemas.py:569`) и `PostEditResponse.length` (`schemas.py:371`)
**Обнаружено:** 2026-09-14 (Frontend Dev, багрепорт «счётчик под постом считает разметку»).
**Описание:** Поле `length` в ответе API считается как `len(post.content)`, то есть по сырому HTML вместе с тегами и инлайновыми стилями. Все остальные длины в сервисе (опыт за пост, порог гейтов, `char_count` черновиков и истории постов) считаются через `strip_html_tags`. На реальном посте id=133 расхождение — 5597 против 4248 символов (+32 %). Единственным потребителем поля был счётчик «N симв.» под опубликованным постом: игрок видел завышенное число, считал, что пост оплачивает гейт, а сервер отказывал.
~~**Исправлено (Backend Dev, 2026-09-14):** оба места считают `"length": len(strip_html_tags(...))` — `crud.py:1587` (ответ редактирования) и `crud.py:2324` (лента `/client/details`). Баланс не затронут: поле нигде не участвует в проверках, единственный потребитель — счётчик «N симв.». Временный обход на фронте снят: `PostCard.tsx` снова показывает серверное `post.length`, клиентский `useMemo`/`stripHtmlTags` из него удалён, число считается ровно в одном месте. Замер на посте id=133: было `length=5597` при `strip_html_tags`=4248, стало 4248 = 4248. Тест `test_owner_edits_the_latest_post_inside_the_window` сверял `length` с `len(LONG_TEXT)` по сырой строке — переведён на `len(crud.strip_html_tags(LONG_TEXT))` (расхождение было в один концевой пробел, который снимает `.strip()`).~~
**Важно:** сам `strip_html_tags` НЕ трогали — его дефекты (нет разделителя на границах блоков, не декодируются энтити) остаются открытым долгом выше и являются изменением баланса.

### Долг: резолв имён в очереди модерации — N+1 запросов вместо батч-эндпоинта
**Сервисы:** locations-service -> character-service, user-service
**Файлы:** `services/locations-service/app/crud.py` — `_enrich_moderation_items()`, `_fetch_character_brief_map()`, `_fetch_username_map()`
**Обнаружено:** FEAT-158 (Architect, раздел 3.3; подтверждено Reviewer 2026-09-13)
**Описание:** Ни у character-service, ни у user-service нет батч-эндпоинта для получения имён по списку id, поэтому очереди модерации делают по одному HTTP-запросу на каждый **уникальный** id (`GET /characters/{id}/short_info`, `GET /users/{id}`). Сейчас это безопасно: обе очереди фильтруют `status='pending'`, вызовы дедуплицируются через `set()`, идут один раз за запрос уже после SQL, таймаут 5 c, а любой сбой даёт `null`, а не 500. Но на длинной очереди (или если такой резолв переиспользуют на более массовом экране) это линейный рост числа запросов.
**Возможное решение:** завести батч-эндпоинты (`POST /characters/short_info/batch`, `POST /users/batch`) и перевести оба хелпера на один запрос.

### Долг: `action_gates.created_at` никто не читает, а цели гейта не валидируются при создании поста
**Сервис:** locations-service
**Файлы:** `services/locations-service/app/models.py:196` (`ActionGate.created_at`), `services/locations-service/app/main.py:772-784` (`_validate_intent_post`), `services/locations-service/app/crud.py:1033` (`create_action_gates`), точки вызова — `main.py:848` (`POST /locations/posts/`) и `main.py:1284` (`move_and_post`)
**Обнаружено:** FEAT-159 (Codebase Analyst + Architect, раздел 3.9, 2026-09-13). Предсуществующее, фичей не внесено и сознательно вынесено за её пределы.
**Описание:** Две связанные асимметрии на пути **создания** гейта.
1. Колонка `action_gates.created_at` заполняется, но **не читается ни одним запросом** во всём репозитории: ни `ORDER BY`, ни сравнения, ни выборки по ней нет (проверено grep'ом по `services/`). Гейты не резервируют цели, не блокируют других игроков и не разрешают ни одной гонки — два персонажа могут одновременно держать `combat`-гейт на одного моба.
2. Цели гейта **никак не проверяются** при создании поста. `_validate_intent_post` смотрит только на то, что `action_type` входит в `GATED_POST_TYPES`, что у гейта есть хотя бы одна цель и что длина текста покрывает бюджет. Ничто не проверяет, что цель **существует**, что она **находится в этой локации**, что это моб, а не игрок (и наоборот), и что она **жива**. У `combat` и принудительного PvP есть отложенные проверки в battle-service, у `gathering` / `dungeon` / `npc_dialogue` — никаких.
**Почему не исправлено в FEAT-159:** раздел 3.9 фичи разбирал родственный вопрос («запрещать ли цели, появившиеся в локации позже поста») и решил **не** вводить проверку по времени: для `pvp` и `npc_dialogue` она в принципе нереализуема — у персонажей и НПС нет истории прибытия в локацию, `characters.current_location_id` перезаписывается без отметки времени. Полупроверка, покрывающая только `combat`, хуже отсутствующей. Вместо этого выбран путь «обогащать, а не блокировать»; он **реализован** в Phase B фичи — `crud._resolve_gate_targets` (`services/locations-service/app/crud.py:3314`) показывает админу имя и состояние каждой цели заявки, но **только на пути модерации ретро-гейтов**. Путь создания поста (`POST /locations/posts/`, `move_and_post`) как не валидировал цели, так и не валидирует — асимметрия сохраняется и после FEAT-159. Валидация целей там — отдельная задача и затрагивает оба «горячих» эндпоинта постинга.
**Статус после FEAT-159 (2026-09-13):** актуально. `action_gates.created_at` по-прежнему не читает ни один запрос (новый код Phase B выбирает из `action_gates` только `action_type` и `target_ref`).
**Возможное решение:** либо удалить `created_at` как неиспользуемую (дёшево, но теряется аудит), либо начать её использовать осознанно; отдельно — ввести проверку существования и локации цели в `_validate_intent_post` с русскими 400, согласовав с тем, что цель может легально умереть/уйти между постом и действием.

---

## LOW

### Долг: `GET /battles/character/{id}/in-battle` описан как внутренний, но лежит вне `/internal/`
**Сервис:** battle-service
**Файл:** `services/battle-service/app/main.py:3588` (`check_character_in_battle`)
**Обнаружено:** FEAT-171 (Reviewer, review #1, 2026-09-19)
**Приоритет:** LOW
**Описание:** в докстроке написано «no auth — internal», но путь не под `/battles/internal/`, поэтому nginx его не режет и анонимный запрос отвечает `{"in_battle": true, "battle_id": N}` по любому `character_id`. Сам по себе это слабый сигнал (участие в бою и так видно в локации), но он даёт готовый перебор: по `character_id` узнаётся `battle_id`.
**Почему не исправлено в FEAT-171:** задача #24 закрывала логи боя; у `in-battle` другой набор вызывающих (его читает фронтенд перед PvP-вызовом), и перенос пути под `/internal/` — ломающее изменение контракта, а не фикс по ревью.
**Возможное решение:** либо перенести во внутренний двойник и оставить фронтенду версию с JWT, либо просто повесить `Depends(get_current_user_via_http)` — гость этот маршрут не использует.

### Долг: мёртвая константа `DURABILITY_SLOT_TYPES`
**Сервис:** inventory-service (`app/crud.py`, константа `DURABILITY_SLOT_TYPES`)
**Обнаружено:** FEAT-165 (Backend Dev, 2026-09-18).
**Описание:** константа `{'head', 'body', 'cloak', 'main_weapon', 'additional_weapons'}` нигде не используется (прочность решается по `items.max_durability > 0`). Имена `main_weapon`/`additional_weapons` — это типы слотов экипировки (они существуют), но не типы предметов (после миграции 019 оружие — `weapon`), поэтому любой, кто начнёт сверять с ней `item_type`, получит тихо неверный результат.
**Возможное решение:** удалить константу или переименовать и перевести на типы предметов (`weapon`), если она понадобится.

### Баг: удаление предмета, который лежит у кого-то в инвентаре, падает с 500
**Сервис:** inventory-service (`services/inventory-service/app/main.py`, `DELETE /inventory/items/{item_id}`, `delete_item`)
**Обнаружено:** FEAT-164 (Reviewer, 2026-09-17), вживую на dev-стеке.
**Описание:** эндпоинт делает `db.delete(item)` + `commit()` без проверок и без обработки ошибок. Если на предмет ссылается `character_inventory` (FK `character_inventory_ibfk_1`, без `ON DELETE`), MySQL отклоняет удаление, и админ получает 500 вместо понятного сообщения. Докстринг сам упоминает, что проверки «можно добавить».
**Что сделать:** перед удалением проверять ссылки (инвентари, слоты, рецепты, лавки, аукцион) и возвращать 409 с русским текстом («Предмет используется: …»), либо ловить `IntegrityError` → 409.

### Долг: два теста конкурентности `refund_stamina` не запускаются нигде
**Сервис:** character-attributes-service (`services/character-attributes-service/app/tests/test_refund_stamina.py:207`, `:265`, класс `TestRefundStaminaConcurrency`)
**Обнаружено:** FEAT-164 (QA, 2026-09-17).
**Описание:** оба теста помечены `skipif(dialect == 'sqlite')` с пояснением «the test runs in CI» / «Verified on MySQL CI». Но движок в файле жёстко задан как SQLite, а в CI (`.github/workflows/ci.yml`) MySQL нет — условие пропуска истинно всегда, и тесты не выполняются ни локально, ни в CI. Гарантию сериализации `with_for_update()` в `refund_stamina` на деле ничего не проверяет, а текст причины вводит в заблуждение.
**Что сделать:** либо поднять MySQL-сервис в CI и гонять эти тесты на нём, либо переписать причину пропуска честно (и/или проверять наличие `FOR UPDATE` в сгенерированном SQL).

### Долг: dungeon-service не печатает итоговую строку pytest
**Сервис:** dungeon-service (`services/dungeon-service/app/tests/`)
**Обнаружено:** Reviewer, FEAT-169 (2026-09-20).
**Приоритет:** LOW
**Описание:** прогон `pytest tests/ -q` выводит только точки прогресса, без строки `N passed` — терминальный репортёр чем-то подавлен. Результат можно оценить только по коду возврата, из-за чего в логах фичи прогон фиксируется как «exit 0 (135)» вместо числа тестов, а скрипты, ищущие `passed`/`failed`, считают сюиту пустой.
**Что сделать:** найти подавление в `conftest.py` / `pytest.ini` сервиса и вернуть обычный вывод.

### Долг: шаблон свипа по исходникам с фиксированным окном может не заметить потерянный заголовок
**Сервисы:** party-service, locations-service, character-service, battle-pass-service, skills-service
**Файлы:** `party-service/app/tests/test_internal_headers.py:149` (±400), `locations-service/app/tests/test_internal_headers.py:175` (−200/+700), `character-service/app/tests/test_internal_headers.py:308`, `:342`, `battle-pass-service/app/tests/test_internal_headers.py:189`, `skills-service/app/tests/test_internal_headers.py:208`
**Обнаружено:** QA и Reviewer, FEAT-169 (2026-09-20). Наследие шаблона FEAT-167.
**Приоритет:** LOW
**Описание:** свип ищет `_internal_token_headers()` в окне фиксированной длины вокруг URL-литерала. Окно перетекает в соседнюю функцию и видит её хелпер, поэтому потерянный заголовок может остаться незамеченным. FEAT-169 исправил окно в новых свипах (обрезка по первой пустой строке), но перечисленные выше остались со старым шаблоном.
**Почему сейчас не горит:** мутационная проверка Reviewer'а (26 вызовов, FEAT-169) показала, что каждый вызов дополнительно закрыт поведенческим тестом на значение заголовка — ни один не держится на свипе одном.
**Что сделать:** перевести все свипы на разбор по скобкам, как в `inventory-service/app/tests/test_outgoing_internal_headers.py:137`.

### Долг: в локальной БД нет ни одного предмета-еды — сценарий eat-food нельзя проверить живьём
**Сервисы:** inventory-service, character-attributes-service (тестовые данные)
**Обнаружено:** Reviewer, FEAT-169 (2026-09-20).
**Приоритет:** LOW
**Описание:** `SELECT * FROM items WHERE is_food=1` возвращает пустой набор, поэтому маршрут `POST /inventory/{id}/eat-food` и вся механика сытости (FEAT-164/168) не проверяются кликом в локальной среде — только юнит-тестами и прямым вызовом внутреннего маршрута сытости.
**Что сделать:** добавить пару предметов-еды в сид или в инструкцию по локальной подготовке данных.

### Хрупкость теста: `test_approve_join_request` в battle-service падает, если перед ним выполнен `test_finalize_extraction.py`
**Сервис:** battle-service (`services/battle-service/app/tests/test_join_requests.py::TestAdminJoinRequests::test_approve_join_request`, `tests/_feat163_harness.py::patch_main`)
**Обнаружено:** FEAT-164 (QA, 2026-09-17). Воспроизводится и на чистом `HEAD`: `pytest tests/test_finalize_extraction.py tests/test_join_requests.py` → `TypeError: object MagicMock can't be used in 'await' expression`.
**Описание:** модули тестов подменяют `sys.modules` (`redis_state`, `battle_engine` и т.д.) MagicMock-ами, а харнесс FEAT-163 перепривязывает атрибуты `main`; при таком порядке файлов что-то из этого остаётся синхронным MagicMock там, где `admin_approve_join_request` делает `await`. В полном прогоне (алфавитный порядок) тест зелёный, поэтому CI не страдает — но случайный порядок (`pytest-randomly`, `-k`, выборочный запуск) даст ложное падение.
**Что сделать:** изолировать подмены модулей (фикстура с `monkeypatch.setitem(sys.modules, ...)` + восстановление) вместо глобальных `sys.modules[...] = MagicMock()` при импорте.

### Долг: при срабатывании `maxEditLength` jsdiff молотит ~30 секунд, блокируя вкладку, и только потом сдаётся
**Сервис:** frontend (`services/frontend/app-chaldea/src/components/pages/LocationPage/PostVersionHistoryModal.tsx:55`, `:111-117`)
**Обнаружено:** FEAT-160 (Frontend Dev — наблюдение; подтверждено Reviewer 2026-09-14 замером внутри контейнера `frontend`).
**Описание:** `DIFF_MAX_EDIT_LENGTH = 20000` ограничивает **ответ**, а не **ожидание**. jsdiff O(ND) доходит до порога и только тогда возвращает `undefined`; поток при этом занят. Замер (node внутри контейнера, реальный модуль `diff@9` + `Intl.Segmenter('ru')`): 1500 слов / 14 748 символов — 415 мс; 6000 слов / 59 205 символов — 6,6 с; 12 000 слов / 118 570 символов — **30,1 с**, и только после этого `undefined`. Модалка обрабатывает `undefined` корректно (показывает обе версии целиком), но до этого вкладка не отвечает.
**Почему сейчас не горит:** самый длинный пост в базе — 5 597 символов, у прода порядок тот же. Порог на реальных данных недостижим: пара постов максимальной длины считается за сотни миллисекунд. Риск латентный и зависит от того, вырастет ли допустимая длина поста (см. долг про `posts.content` TEXT).
**Возможное решение:** вынести расчёт в Web Worker, либо ограничивать вход по длине текста *до* вызова `diffWords` (например, отказываться от пословного сравнения сразу при > 40 000 символов на сторону) вместо того, чтобы полагаться на `maxEditLength`. Сознательно не правилось в FEAT-160: архитектурное решение 3.2 фиксирует `maxEditLength`, а отход от него — отдельное решение.


### Долг: таблица сервисов в CLAUDE.md п.1 устарела — три живых сервиса не перечислены
**Сервис:** документация (`CLAUDE.md`, раздел 1, «Сервисы и порты»)
**Обнаружено:** FEAT-161 (Architect, раздел 2.2, риск R6; подтверждено Reviewer 2026-09-14 по `docker ps`).
**Описание:** В таблице перечислено 10 backend-сервисов, а в `docker ps` живут ещё три: `dungeon-service`, `battle-pass-service`, `party-service`. Все три имеют собственный код в `services/`, поднимаются обоими compose-файлами и содержат `datetime`-поля в схемах. Агент, который сверяется только с CLAUDE.md, их не увидит и пропустит при любой сквозной правке (ровно это чуть не случилось со списком сервисов в FEAT-161).
**Возможное решение:** дописать три строки в таблицу раздела 1 (порт, путь, особенности) и заодно сверить граф межсервисных зависимостей в разделе 2.

### Долг: CLAUDE.md п.10.7 устарел — locations-service проверяет JWT сам
**Сервис:** документация (`CLAUDE.md`, раздел 10, пункт 7)
**Обнаружено:** FEAT-156 (Architect, 2026-09-13; сначала как «риск» попало в раздел 2 фичи, затем проверено по коду и опровергнуто)
**Описание:** П.10.7 утверждает: «Аутентификация — JWT реализована только в user-service и notification-service. Остальные сервисы не проверяют токены.» Для locations-service это неверно: `services/locations-service/app/auth_http.py:24` определяет `get_current_user_via_http`, которая валидирует Bearer-токен запросом к `user-service GET /users/me`. Зависимость стоит напрямую на **26** маршрутах `main.py` и ещё на **59** через `require_permission(...)` (`auth_http.py:73`), построенный поверх неё. Владелец персонажа сверяется отдельно — `verify_character_ownership` (`main.py:114`).
**Почему это важно:** формулировка уже один раз увела проектирование в сторону — архитектор FEAT-156 начинал с допущения, что для черновиков нужен новый механизм авторизации. Копии `auth_http.py` лежат в 12 сервисах, так что утверждение, скорее всего, устарело шире, чем на один сервис.
**Возможное решение:** перепроверить наличие и применение `auth_http.py` во всех сервисах и переписать п.10.7 по факту. Правка CLAUDE.md в FEAT-156 не делалась намеренно — файл вне области фичи. Фактическое состояние уже описано в `docs/services/locations-service.md` (раздел «Назначение»).

### Долг: прод-база называется `fogdatabase`, а документация говорит `mydatabase`
**Сервис:** документация (`CLAUDE.md` разделы 1 и 2, `docs/ARCHITECTURE.md`)
**Обнаружено:** FEAT-156 (PM, проверка прода 2026-09-13)
**Описание:** И CLAUDE.md, и `docs/ARCHITECTURE.md` называют единую MySQL-базу `mydatabase`. Это имя **локального dev-окружения**; на проде база называется `fogdatabase` — подтверждено прямым запросом к прод-БД при расследовании потерянного поста. Имя MongoDB-базы в `ARCHITECTURE.md` тоже указано как `mydatabase` и на проде не проверялось.
**Чем мешает:** любая инструкция вида «зайди в `mydatabase` и посмотри» на проде не работает, а агент, который поверит документации, решит, что базы нет.
**Возможное решение:** писать в документации оба имени с пометкой, какое из них dev, а какое prod, либо ссылаться на переменную окружения вместо литерала. Проверить заодно и имя базы MongoDB на проде.

### Долг: в миграциях индексы удаляются до таблицы — откат падает на MySQL
**Сервис:** locations-service (и любой другой, где повторят приём)
**Файл:** `app/alembic/versions/031_add_gathering_nodes.py` (в `034_origin_starting_points.py` исправлено в FEAT-155)
**Обнаружено:** FEAT-155 (Reviewer, 2026-09-06). Предсуществующее, не блокирует.
**Описание:** В `downgrade()` вызывается `op.drop_index(...)` **до** `op.drop_table(...)`. Если на индекс опирается внешний ключ, InnoDB отказывает: `(1553, "Cannot drop index '...': needed in a foreign key constraint")`. `drop_table` и так уносит индексы вместе с таблицей, поэтому явные `drop_index` перед ним не нужны и вредны.
**Почему не ловится тестами:** тесты идут на SQLite, который ограничение не проверяет. Дефект виден только при откате на живом MySQL.
**Это третий случай той же природы** в проекте — см. заметку N9 в `features/DONE-FEAT-154-character-creation-overhaul.md` (там порядок мешал снять уникальный индекс) и миграцию `035_origin_drop_map_link` (там внешний ключ искали через `information_schema`).
**Правило на будущее:** в `downgrade()`, удаляющем таблицу целиком, явные `drop_index` не писать. Любую миграцию, трогающую индексы или внешние ключи, прогонять циклом `upgrade → downgrade → upgrade` на живом MySQL, а не только под тестами.

### Долг: подстановочные знаки LIKE не экранируются в публичном лукапе локаций
**Сервис:** locations-service
**Файл:** `app/crud.py:208,213` (`get_locations_lookup`)
**Обнаружено:** FEAT-155 (Backend Dev, 2026-09-06). Предсуществующий, к фиче отношения не имеет.
**Описание:** Пользовательский ввод подставляется в `LIKE '%{q}%'` без экранирования, поэтому запрос `%` возвращает весь список локаций, `_` — любые односимвольные, а локацию с `%` или `_` в названии по этому символу не найти. **Не уязвимость:** параметризация на месте, инъекция не выполняется. Но поиск ведёт себя не так, как ожидает вводящий, и эндпоинт публичный — то есть `%` даёт любому полный список локаций одним запросом.
**Почему просто починить:** в том же модуле уже есть хелпер `_escape_like`, написанный для `search_locations_with_breadcrumbs` в FEAT-155. Правка — две строки: обернуть ввод и добавить `escape=_LIKE_ESCAPE_CHAR`.
**Важно при починке:** символ экранирования — `!`, а не `\`. Обратный слэш является служебным внутри строковых литералов MySQL, и `ESCAPE ''` ведёт себя по-разному на MySQL и SQLite (на котором идут тесты).

### ~~Долг: подстановочные знаки LIKE не экранируются в поиске локаций~~ DONE (FEAT-155)
~~**Сервис:** locations-service~~
~~**Файл:** `app/crud.py` — `search_locations_with_breadcrumbs`~~
~~**Исправлено в FEAT-155** (до выката, код был новый): `q` проходит через `_escape_like()` — экранируются `%`, `_` и сам символ экранирования, а к `LIKE` добавлен `ESCAPE '!'`. Символ `!` выбран вместо обратного слэша, потому что слэш сам является escape-символом внутри строковых литералов MySQL, а `!` одинаково буквален и в MySQL, и в SQLite (на котором идут тесты). Тест `test_like_wildcards_are_not_escaped` переписан в `test_like_wildcards_are_treated_as_literal_characters`, рядом добавлен позитивный случай `test_a_name_containing_a_wildcard_is_findable_by_it`.~~

### Баг: прямая ссылка на `/characters/list` и `/rules/*` отдаёт сырой JSON вместо страницы
**Сервис:** api-gateway (nginx), frontend
**Файлы:** `docker/api-gateway/nginx.conf`, `docker/api-gateway/nginx.prod.conf`, SPA-маршруты в `src/components/App/App.tsx`
**Обнаружено:** FEAT-154 (QA, живая проверка в браузере, 2026-09-06)
**Описание:** Nginx направляет `location /characters/` в character-service, а `/rules/` — в locations-service. Но во фронтенде на этих же путях объявлены SPA-маршруты (`/characters/list` — с FEAT-058, `/rules` — с FEAT-024). Внутри приложения переходы работают, потому что роутер меняет URL без запроса к серверу. А вот **обновление страницы, закладка или ссылка, присланная другому игроку**, уходят на сервер и возвращают ответ API — пользователь видит голый JSON вместо интерфейса.
**Почему важно именно сейчас:** FEAT-154 делает `/characters/list` страницей, на которую игроки будут ссылаться друг другу — там теперь паспорта персонажей.
**Возможное решение:** сузить префиксы в nginx до реальных API-путей, либо развести API и SPA по разным префиксам. Правку делать в обоих конфигах.

### Баг: путь к аватару по умолчанию задан относительным и даёт 404
**Сервис:** frontend
**Файлы:** `src/components/pages/AllUsersPage/AllUsersPage.tsx:7`, `src/components/pages/OnlineUsersPage/OnlineUsersPage.tsx:7`
**Обнаружено:** FEAT-154 (QA, живая проверка в браузере, 2026-09-06). Предсуществующий, из FEAT-029.
**Описание:** `const DEFAULT_AVATAR = 'assets/avatars/avatar.png'` — без ведущего слэша, поэтому путь разрешается относительно текущего маршрута. На любой вложенной странице даёт 404 и сломанную картинку. Например с `/characters/list` уходит запрос на `/characters/assets/avatars/avatar.png`.
**Возможное решение:** ведущий слэш.

### Долг: тесты inventory-service зависят от порядка выполнения
**Сервис:** inventory-service
**Файл:** `app/tests/conftest.py:163`
**Обнаружено:** FEAT-154 (Backend Dev, 2026-09-06)
**Описание:** `drop_all` не может отсортировать таблицы из-за циклической зависимости внешних ключей `items` <-> `recipes`, поэтому состояние между тестами подчищается не полностью. При обычном прогоне набор зелёный (466 passed), но если в окружении окажется плагин, перемешивающий порядок тестов (`pytest-randomly`), падает весь `test_items_bulk.py` — около 20 тестов. **На CI не влияет:** такого плагина нет ни в одном `requirements.txt`, проверено. Это скрытая хрупкость, а не сломанный набор.
**Возможное решение:** `use_alter=True` на одном из внешних ключей в цикле, либо пересоздание схемы между тестами вместо `drop_all`.

### Баг: двойной слэш в URL запроса опыта
**Сервис:** character-service
**Файл:** `app/crud.py:683`
**Обнаружено:** FEAT-154 (Codebase Analyst, 2026-09-06)
**Описание:** URL собирается как `{ATTRIBUTES_SERVICE_URL}/{id}/experience`, хотя настройка уже заканчивается на `/`. Получается `//`.

### Долг: блокирующий I/O в асинхронном контексте
**Сервисы:** все (12 копий `auth_http.py`), character-service
**Файлы:** `auth_http.py:30` (блокирующий `requests.get` внутри async-зависимости, срабатывает на каждом аутентифицированном запросе), `character-service/app/crud.py:954` (блокирующий `httpx.post`)
**Обнаружено:** FEAT-154 (Codebase Analyst, 2026-09-06)
**Описание:** Блокирующие вызовы внутри event loop подвешивают весь воркер на время запроса. Связано с уже заведённым пунктом про `async def` эндпоинты character-service с синхронной работой с БД.

### Баг: `auth_http` ловит только `ConnectionError`
**Сервисы:** все (12 копий)
**Файл:** `auth_http.py:32`
**Обнаружено:** FEAT-154 (Codebase Analyst, 2026-09-06)
**Описание:** Перехватывается только `ConnectionError`. `Timeout` или `SSLError` от user-service всплывают как 500 вместо 503, то есть временная недоступность выглядит как внутренняя ошибка.

### Баг: photo-service на превышение размера файла отдаёт 500 вместо 413 (общий путь)
**Сервис:** photo-service
**Файлы:** `utils.py:60-66` (`convert_to_webp`), все загрузочные эндпоинты `main.py`, кроме `POST /photo/upload_character_request_avatar`
**Обнаружено:** FEAT-154 (Codebase Analyst, 2026-09-06); уточнено FEAT-154 (DevSecOps, задача #13)
**Описание:** При файле больше 15 МБ `convert_to_webp` поднимает `ValueError`, который перехватывается общим `except Exception` и превращается в 500. Пользователь не понимает, что файл просто слишком большой. Рядом: `validate_image_mime` (`utils.py:25`) доверяет клиентскому `Content-Type` вместо проверки сигнатуры файла.

**Первопричина:** `convert_to_webp` бросает **голый `ValueError`** для трёх разных условий (превышение размера, битое/не-изображение, неподдерживаемый формат). Различить их можно только по тексту исключения — типизированных исключений в `utils.py` нет.

**Что уже сделано (FEAT-154, решение D14, примечание N3):** новый эндпоинт `POST /photo/upload_character_request_avatar` обрабатывает случай **локально** — ловит `ValueError` и отдаёт **413** с русским сообщением при превышении размера и **400** при некорректном изображении. Различение держится на **совпадении подстроки в тексте исключения** — по первопричине выше это единственный доступный способ, и он хрупок: любая правка формулировки в `utils.py` тихо ломает коды ответов.

**Общий путь остался как был** — все остальные загрузочные эндпоинты photo-service по-прежнему отдают 500 на превышение размера.

**Возможное решение:** ввести в `utils.py` типизированные исключения (например `ImageTooLargeError` / `InvalidImageError` вместо голого `ValueError`), перевести на них новый эндпоинт (убрав сопоставление по подстроке) и добавить обработку во все остальные загрузочные эндпоинты.

### Долг: непоследовательный дефолт CORS в prod — 5 сервисов падают на `*`
**Сервисы:** user-service, character-service, character-attributes-service, inventory-service, photo-service
**Файлы:** `docker-compose.yml` (`CORS_ORIGINS: ${CORS_ORIGINS:-*}`), `docker-compose.prod.yml`
**Обнаружено:** FEAT-154 (DevSecOps, задача #12, 2026-09-06)
**Описание:** В `docker-compose.prod.yml` восемь сервисов (locations, skills, battle, autobattle, battle-pass, dungeon, party, notification) переопределяют `CORS_ORIGINS` дефолтом `https://fallofgods.top`. Оставшиеся пять переопределения не имеют и наследуют базовый `${CORS_ORIGINS:-*}`. Проверено через `docker compose -f docker-compose.yml -f docker-compose.prod.yml config`: при незаданном `CORS_ORIGINS` в `.env` на VPS эти пять сервисов в проде поднимаются с `Access-Control-Allow-Origin: *`. Фактическое состояние прода зависит от `.env` на VPS, но сам дефолт непоследователен и небезопасен (CLAUDE.md п.10.6 — origins захардкожены в каждом сервисе отдельно).
**Возможное решение:** привести prod-дефолт к `https://fallofgods.top` для всех сервисов (либо перенести дефолт в один якорь compose), а `*` оставить только dev-конфигу.

### ~~Долг: расхождение документации с кодом~~ DONE (FEAT-154, задача #29)
**Файлы:** `CLAUDE.md` (раздел 7, п.10.4), `character-service/app/main.py`
**Обнаружено:** FEAT-154 (Codebase Analyst, 2026-09-06)
**Описание:** `CLAUDE.md` раздел 7 указывал notification-service и battle-service как сервисы без Alembic — у обоих Alembic есть. `CLAUDE.md` п.10.4 утверждал, что RabbitMQ-консьюмеры закомментированы в character-service, skills-service, inventory-service и character-attributes-service — реально запускаются в трёх из четырёх. Докстринг одобрения заявки ссылался на `SUBRACE_ATTRIBUTES` из `presets.py`, который является мёртвым кодом (реальный источник пресетов — колонка `subraces.stat_preset`).
~~**Исправлено в FEAT-154 (задача #29):** раздел 7 CLAUDE.md перечисляет battle-service (`alembic_version_battle`) и notification-service (`alembic_version_notification`) среди сервисов с Alembic; п.10.4 переписан — консьюмер закомментирован только в character-service, в skills/inventory/character-attributes он поднимается при старте (со ссылками на строки). Докстринг `approve_character_request` переписан по фактическому 13-шаговому флоу и больше не упоминает `SUBRACE_ATTRIBUTES`. `presets.py` помечен как мёртвый код в `docs/services/character-service.md`.~~

### 17. Неиспользуемые зависимости
**Описание:**
- `lightgbm`, `scikit-learn` в autobattle-service — не импортируются
- `credentials/gcs-credentials.json` в photo-service — не используется
**Решение:** Удалить неиспользуемый код и зависимости.

### ~~21. Schema/ORM mismatch: loot_table vs loot_entries in MobTemplateDetailResponse~~ DONE (FEAT-059, Review)
~~**Сервис:** character-service~~
~~**Исправлено в FEAT-059 Review:** Renamed schema field `loot_table` to `loot_entries` in `MobTemplateDetailResponse` and updated frontend TypeScript interface to match.~~

### ~~22. Баг: вражеские эффекты лечат вместо нанесения урона~~ DONE
~~**Сервис:** battle-service~~
~~**Файл:** `services/battle-service/app/buffs.py`~~
~~**Описание:** `apply_new_effects` для enemy-эффектов с положительной magnitude на HP/mana/energy/stamina прибавляла значение (лечила врага) вместо вычитания.~~
~~**Исправлено:** Добавлен параметр `is_enemy` — при `True` положительная magnitude инвертируется для мгновенных атрибутов.~~

### ~~23. Баг: _normalize_effect падает при effect_name без двоеточия~~ DONE
~~**Сервис:** battle-service~~
~~**Файл:** `services/battle-service/app/buffs.py`~~
~~**Описание:** `kind, tail = name.split(":", 1)` падал с `ValueError` если effect_name не содержал `:` (например "Bleeding").~~
~~**Исправлено:** Проверка `len(parts)` перед распаковкой.~~

### ~~24. battle-service skills_client вызывает admin endpoint без авторизации~~ DONE
~~**Сервис:** battle-service~~
~~**Файл:** `services/battle-service/app/skills_client.py`~~
~~**Описание:** `get_rank()` и `character_ranks()` вызывали `/skills/admin/skill_ranks/{id}` (требует JWT), battle-service не отправлял токен → навыки не загружались в бою.~~
~~**Исправлено:** `character_ranks()` использует данные из публичного ответа `/skills/characters/{id}/skills`. `get_rank()` использует новый публичный endpoint `/skills/skill_ranks/{id}`.~~

### 25. Баг: dungeon-service тесты не запускаются (from conftest import)
**Сервис:** dungeon-service
**Файлы:** `services/dungeon-service/app/tests/test_admin_crud.py`, `services/dungeon-service/app/tests/test_room_positions.py`
**Описание:** Тесты используют `from conftest import _dungeon_payload, _room_payload` — это не работает, т.к. `tests/__init__.py` существует и conftest не доступен как обычный модуль. pytest обрабатывает conftest.py автоматически, но прямой import невозможен при наличии `__init__.py`. Затрагивает 2 из 5 тестовых файлов.
**Решение:** Удалить `__init__.py` из `tests/`, либо переименовать helper-функции в фикстуры, либо вынести `_dungeon_payload`/`_room_payload` в отдельный модуль `tests/helpers.py`.

### 19. Несогласованность типов participant_id в battle-service
**Сервис:** battle-service
**Описание:** participant_id хранится как string ключ в Redis dict, но используется как int в разных местах кода. Потенциальный `KeyError`.
**Решение:** Унифицировать: всегда приводить к string при работе с Redis state.

### 26. Неиспользуемые константы в ProfilePage/constants.ts (после FEAT-149)
**Сервис:** frontend
**Файл:** `services/frontend/app-chaldea/src/components/ProfilePage/constants.ts` (строки ~98, ~252)
**Описание:** После редизайна профиля (FEAT-149) константы `MIN_GRID_CELLS` (филлеры сетки инвентаря удалены) и `DERIVED_STATS` (DerivedStatsSection перешёл на собственные COMBAT_CARD_LABELS/RESIST_CHIPS) больше нигде не используются.
**Решение:** Удалить обе константы (безопасный dead-code cleanup, отдельным мелким коммитом).

### 28. Мёртвый код удаления accessToken в useNavigateTo.js
**Сервис:** frontend
**Файл:** `services/frontend/app-chaldea/src/hooks/useNavigateTo.js:9`
**Обнаружено:** FEAT-150 (Reviewer, 2026-07-17). Pre-existing, к фиче не относится.
**Описание:** Хук удаляет `accessToken` (но не `refreshToken`) при `navigateTo('/')`. Ни один текущий вызов не передаёт `'/'` (проверено grep), так что ветка — мёртвый код. Однако она нарушает инвариант FEAT-150 «токены удаляются только в `handleAuthFailure()` / `clearTokens()`»: будущий вызов `navigateTo('/')` создаст «полу-logout» (accessToken удалён, refreshToken жив → интерсептор воскресит сессию).
**Решение:** Удалить ветку `if (link === '/')` из хука (заодно мигрировать файл на TS при первой правке логики, правило T3).

### 29. После логина через форму хедер не показывает пользователя до перезагрузки
**Сервис:** frontend
**Файлы:** `services/frontend/app-chaldea/src/components/StartPage/AuthForm/AuthForm.tsx` (навигация после логина), `src/components/CommonComponents/Header/Header.tsx:29-35` (getMe пропускается на первом маунте)
**Обнаружено:** FEAT-150 (Reviewer, 2026-07-17). Pre-existing поведение, воспроизводится и на HEAD до фичи (проверено).
**Описание:** После успешного логина AuthForm делает SPA-переход на `/home` без dispatch(getMe()). Header монтируется заново и пропускает getMe на первом маунте (`isInitialMount`), App.tsx вызывает getMe только при старте приложения. В итоге сразу после логина хедер выглядит «разлогиненным» (нет аватара/меню) до следующей навигации или F5.
**Решение:** Диспатчить `getMe()` после успешного логина в AuthForm (или убрать пропуск первого маунта в Header).

### 30. `PUT /locations/{id}/update` отвечает 500 вместо 404 на несуществующую локацию
**Сервис:** locations-service
**Файлы:** `services/locations-service/app/crud.py` (`update_location`), `app/main.py` (`update_location_route`)
**Обнаружено:** FEAT-154 (Backend Dev, задача #2). Pre-existing, к фиче отношения не имеет.
**Описание:** `crud.update_location` поднимает `HTTPException(404, "Location not found")`, но её же перехватывает собственный `except Exception` и переоборачивает в `HTTP 500 detail=str(e)`. То же самое повторяет `try/except` в обработчике. Клиент вместо «локация не найдена» получает 500. Дополнительно текст 404 на английском (нарушает правило русских сообщений).
**Решение:** Пробрасывать `HTTPException` без перехвата (`except HTTPException: raise` перед общим `except`), перевести сообщение на русский.

### Долг: применение исправления спеллчекера перемонтирует редактор — теряются курсор и история отмен
**Сервис:** frontend
**Файлы:** `services/frontend/app-chaldea/src/components/pages/LocationPage/PostCreateForm.tsx:140-148` (`replaceContent`, бамп `editorKey`), `:266-272` (`handleApplySuggestion`), `services/frontend/app-chaldea/src/components/CommonComponents/WysiwygEditor/WysiwygEditor.tsx:59-63`
**Обнаружено:** FEAT-157 (Architect, 2026-09-13). Предсуществующее (появилось в FEAT-156), не входит ни в один из трёх симптомов фичи.
**Описание:** Любая программная подмена контента (применение исправления правописания, вставка черновика) делается через смену `key` у `WysiwygEditor`. React размонтирует и монтирует редактор заново: позиция курсора теряется, история undo/redo обнуляется, поле проматывается наверх. При правке нескольких слов подряд это заметно.
**Почему не исправлено в FEAT-157:** правильное решение — применять замену транзакцией ProseMirror, а для этого нужно отдать наружу экземпляр `Editor`, то есть менять публичный контракт общего `WysiwygEditor` (`{ content, onChange, enableArchiveLinks }`), которым пользуются несколько страниц. Это отдельный рефакторинг, а не багфикс.
**Возможное решение:** расширить API `WysiwygEditor` императивным методом (`ref` + `replaceRange`/`setContent` через транзакцию), убрать `editorKey` и перевести на него же вставку черновика.

### Баг: палитра `react-colorful` красит текст при простом перетаскивании, без подтверждения
**Сервис:** frontend
**Файл:** `services/frontend/app-chaldea/src/components/CommonComponents/WysiwygEditor/WysiwygEditor.tsx:376`
**Обнаружено:** FEAT-157 (PM/Architect, 2026-09-13). Побочное наблюдение при разборе бага с цветом, отдельной жалобы от игроков не было.
**Описание:** `react-colorful` шлёт `onChange` непрерывно во время перетаскивания, и обработчик сразу применяет цвет к выделению. Достаточно открыть палитру и дёрнуть мышью, чтобы текст оказался покрашен — в том числе в белый `rgb(255,255,255)`, так как текущий цвет читается как `editor.getAttributes("textStyle").color || "#ffffff"`. Игрок получает цвет, который «не выбирал», а на обычном тексте это ещё и лишний `<span>` в HTML поста.
**Возможное решение:** применять цвет по `onMouseUp`/`onTouchEnd` (или по кнопке «Применить»), а во время перетаскивания показывать только превью; не подставлять `#ffffff` как «текущий цвет», если у выделения цвета нет.

### Долг: смещения спеллчекера ломаются на суррогатных парах (эмодзи)
**Сервис:** frontend
**Файл:** `services/frontend/app-chaldea/src/api/spellcheck.ts` (`htmlToSpellText` / `replaceWordInHtml`)
**Обнаружено:** FEAT-157 (Architect, 2026-09-13). Осознанно принятое ограничение, зафиксировано в разделе 3.3 фичи.
**Описание:** Яндекс.Спеллер возвращает `pos`/`len` в кодовых единицах UTF-16, что совпадает с индексами JS-строк для всей кириллицы и латиницы. Текст с суррогатными парами (эмодзи, редкие символы вне BMP) может дать смещение, не совпадающее с индексом в нашей модели, и исправление применится не к тому фрагменту.
**Почему не исправлено:** для ролевых постов случай редкий, а корректная обработка требует отдельной модели индексации по кодовым точкам во всём пути «HTML → текст → замена».
**Возможное решение:** считать индексы по кодовым точкам и переводить их в UTF-16 при сопоставлении с ответом спеллера, либо отклонять применение исправления, если в диапазоне обнаружена суррогатная пара, и показывать русское сообщение.

### Долг: права `gametime:read|update` заводятся миграцией locations-service, а не user-service
**Сервисы:** locations-service (миграция), user-service (владелец RBAC)
**Файл:** `services/locations-service/app/alembic/versions/004_game_time_config.py:45-66`
**Обнаружено:** FEAT-158 (Architect, раздел 3.5; проверено Reviewer 2026-09-13)
**Описание:** Это единственные права в системе, которые регистрируются вне user-service. Работает только потому, что база MySQL общая. Нарушает CLAUDE.md §10.13 («разрешения заводит владелец RBAC») и, что важнее, делает ненадёжной ровно ту проверку, которая поймала бы баг FEAT-158: «сгрепать `user-service/alembic` и получить полный список прав». Guard-тест `services/user-service/tests/test_moderation_permissions.py` вынужден сканировать оба дерева миграций.
**Возможное решение:** перенести регистрацию `gametime:*` в миграцию user-service (идемпотентным SELECT-then-INSERT, чтобы не задеть существующие установки), из миграции 004 убрать.

### Вопрос продукта: модератор не может открыть `/admin/game-time`
**Сервис:** frontend + user-service (RBAC)
**Файл:** `services/locations-service/app/alembic/versions/004_game_time_config.py:56-62`
**Обнаружено:** FEAT-158 (Architect, раздел 3.5)
**Описание:** Права `gametime:read|update` выдаются только роли `admin` (миграция джойнит `roles r WHERE r.name = 'admin'`). Плитка и маршрут согласованы между собой, поэтому визуального «битого» перехода нет — это не дефект, а не заданный продуктовый вопрос: должен ли модератор видеть игровой календарь.
**Возможное решение:** если ответ «да» — двухстрочная миграция, выдающая оба права роли 3.

### Долг: PUT-эндпоинты рассмотрения модерации объявляют полную read-схему, а отдают 7 полей
**Сервис:** locations-service
**Файлы:** `services/locations-service/app/main.py:2221-2238` (`PUT /admin/moderation/deletion-requests/{id}/review`), `services/locations-service/app/main.py:2241-2258` (`PUT /admin/moderation/reports/{id}/review`), `services/locations-service/app/main.py:2283-2303` + `crud.py:3620-3630` (`PUT /admin/moderation/gate-requests/{id}/review`, FEAT-159 — та же картина)
**Обнаружено:** FEAT-158 (Reviewer, 2026-09-13)
**Описание:** Оба хендлера объявлены с `response_model=PostDeletionRequestRead` / `PostReportRead`, но вручную собирают словарь из 7 ключей. Остальные шесть полей (`post_content`, `post_character_id`, `post_location_id`, `post_character_name`, `post_created_at`, `requester_username`) сериализуются как `null`. Живая проверка: `dismiss` жалобы на **живой** пост вернул `{"post_id":153, ..., "post_content":null}` — по правилу фронта `isPostMissing` (`post_id === null || post_content === null`) это читается как «пост удалён», что неправда. Сегодня безвредно: `AdminModerationPage.tsx` игнорирует тело PUT и перезапрашивает очередь. Но контракт в `/openapi.json` обещает то, чего эндпоинт не отдаёт, и любой следующий потребитель, доверившийся телу ответа, отрисует неверное состояние.
**Дополнено FEAT-159 (2026-09-13):** третий эндпоинт рассмотрения — заявки на ретро-гейты — повторил тот же паттерн: `response_model=PostGateRequestRead`, а `crud.review_gate_request` возвращает 9 ключей из 18 (`post_content`, `post_character_name`, `post_location_name`, `post_edited_at`, `requester_username`, `targets_resolved` -> `null` / `{}`). Симптом тот же и так же безвреден сегодня: фронт игнорирует тело PUT и перезапрашивает очередь.
**Возможное решение:** либо объявить отдельную узкую схему `PostModerationDecisionRead` (7 полей; для гейтов — плюс `gates`), либо заполнять тело теми же данными, что и очередь. Чинить стоит все три эндпоинта разом.

### Долг: видимость плитки в админке проверяет модуль, а маршрут — конкретное право
**Сервис:** frontend
**Файлы:** `services/frontend/app-chaldea/src/components/Admin/AdminPage.tsx:82-84` (`hasModuleAccess`), `services/frontend/app-chaldea/src/components/CommonComponents/ProtectedRoute/ProtectedRoute.tsx:56-58` (`hasPermission`)
**Обнаружено:** FEAT-158 (Reviewer, 2026-09-13)
**Описание:** После FEAT-158 обход `role === 'admin'` убран, и обе проверки идут от прав — это закрыло исходный баг. Но остаётся разная гранулярность: плитка показывается при **любом** праве модуля (`module:*`), а маршрут требует конкретное (`moderation:read`, `items:read` и т. д.). Пользователь, которому выдали только `moderation:review` (или только `items:create`), увидит плитку и будет выброшен на `/home` — тот же симптом, что чинила FEAT-158. Сейчас не воспроизводится: ни одна роль не имеет `review` без `read`, а админ получает все права. Риск реализуется при точечной выдаче прав через `user_permissions`.
**Возможное решение:** хранить в `sections[]` рядом с `module` то же самое право, что стоит в `requiredPermission` маршрута, и фильтровать плитки через `hasPermission`.

### Долг: тест «админ получает все разрешения» не читает миграции и новое право не покрывает
**Сервис:** user-service (тесты)
**Файлы:** `services/user-service/tests/test_rbac_permissions.py` (класс `TestAdminAutoPermissions`)
**Обнаружено:** FEAT-160 (QA, 2026-09-14)
**Описание:** CLAUDE.md §10.13 утверждал, что этот тест «обновится автоматически при добавлении новых разрешений». Это неправда: класс работает на собственном синтетическом сиде из 8 разрешений с захардкоженными счётчиками (`len(perms) == 9`, `== 11`) и дерево Alembic-миграций не читает вообще. Новая строка в `permissions`, заведённая миграцией, в него не попадает — покрытие появляется только если разрешение засеяно явно отдельной секцией. На это утверждение уже опёрлись две фичи, заведшие по разрешению (`characters:teleport` — FEAT-162, `posts:history` — FEAT-160); у обеих покрытие есть, но потому что QA засеял их руками, а не потому что тест сам их подхватил. Формулировка в CLAUDE.md исправлена (FEAT-160, T10); сам тест не трогали.
**Возможное решение:** отдельный guard-тест, который сканирует `user-service/alembic/versions/` (и, пока не закрыт долг про разрешения вне user-service, `locations-service/app/alembic/versions/`), собирает полный список `module:action` и проверяет, что `get_effective_permissions` для админа отдаёт их все. Тогда новое разрешение действительно покрывалось бы без ручного сида.


### Долг: `BattleStatus.forfeit` — мёртвое значение перечисления
**Сервис:** battle-service
**Файлы:** `services/battle-service/app/models.py:17`, `services/battle-service/app/alembic/versions/001_initial_baseline.py:32`; читается на `services/battle-service/app/main.py:4072` и `:4391`
**Обнаружено:** FEAT-163 (Backend Dev, задача #15, 2026-09-14)
**Описание:** значение `forfeit` объявлено в ENUM `battles.status`, читается ровно в двух местах — и в обоих означает ровно то же, что `finished` («Бой уже завершён»). **Не присваивается нигде**: `crud.finish_battle` пишет только `finished`, и никакой другой путь тоже. Собственного поведения значение не несёт.
**Почему FEAT-163 сознательно его не задействовала:** факт выбывания — **пер-участниковый**, а не пер-боевой. В командном бою бой не «сдан» вообще: уходит один участник, остальные доигрывают. Значение уровня боя — неверная гранулярность для основного случая. Кроме того, второй терминальный статус потребовал бы аудита всех мест, где `finished` считается *тем самым* терминальным значением (`_make_action_core`, фильтры админского списка, `battle_history`, выборка по локации, фронтенд). Факт выбывания вместо этого живёт в `battle_participants.dropped_out_at` и в Mongo-событии `participant_timed_out`.
**Возможное решение:** отдельной уборкой убрать `forfeit` из перечисления и из двух проверок (миграция ENUM на `battles.status`), либо оставить как есть и задокументировать как защитное чтение. Сейчас безвредно — просто мёртвый код.

### Ограничение: свипер таймаута не видит бой, потерявший запись в ZSET при живом ключе состояния
**Сервис:** battle-service
**Файлы:** `services/battle-service/app/main.py:5225` (`_sweep_due_deadlines`), `:5310` (`_reconcile_stale_battles`)
**Обнаружено:** FEAT-163 (Backend Dev, автор свипера, 2026-09-14). **Это заявленное покрытие проектного решения, а не регрессия** — записано, чтобы его не «переоткрыли» как баг.
**Описание:** свипер ключуется по `battle:deadlines`. Если запись боя из множества пропала, а ключ `battle:{id}:state` ещё жив (например, процесс упал между атомарным `ZREM`-захватом и повторным `ZADD`), проход по дедлайнам такой бой не увидит. Вторая линия — почасовая сверка с MySQL (`_reconcile_stale_battles`) — требует **отсутствия** ключа состояния, поэтому подхватит бой только после того, как ключ истечёт по `BATTLE_STATE_TTL_HOURS` (48 ч). То есть окно есть, но оно ограничено сверху и самолечится.
**Почему так сделано:** второй guard (отсутствие ключа состояния) — именно то, что не даёт сверке уничтожить живой, но тихий бой. Ослабить его = получить ложные срабатывания на здоровых боях.
**Возможное решение, если понадобится:** перевзводить запись в ZSET из ключа состояния — сверять `state["deadline_at"]` живых `in_progress` боёв с содержимым множества и восстанавливать недостающие записи. Отдельной задачей: это уже третий источник истины по дедлайну.

### Баг: notification-service отдаёт английское сообщение об ошибке авторизации
**Сервис:** notification-service
**Файл:** `services/notification-service/app/auth_http.py:50` (`get_current_user_via_http`)
**Обнаружено:** FEAT-171 (Backend Dev, задача #11, 2026-09-19)
**Приоритет:** LOW
**Описание:** при недействительном токене поднимается `HTTPException(401, "Could not validate credentials")` — единственная английская строка такого рода среди сервисов (в остальных «Не удалось подтвердить учётные данные»). Текст видит пользователь: фронтенд показывает `detail` в тосте. Задача FEAT-171 #11 этого не касалась (там закрывалась история чата для гостя, собственное русское сообщение добавлено отдельной зависимостью `require_chat_reader`), поэтому правка вынесена сюда.
**Возможное решение:** заменить строку на русскую; затронет все JWT-маршруты сервиса, поэтому проверить тесты, сверяющие `detail`.

---

### Долг: `GET /locations/{id}/client/details` анонимно принимает чужой `character_id` (побочный эффект записи)
**Сервис:** locations-service
**Файл:** `services/locations-service/app/main.py:1102` (`get_location_client_details`)
**Обнаружено:** FEAT-171 (Backend Dev, задача #22 — фикс по ревью, 2026-09-20)
**Приоритет:** LOW
**Описание:** маршрут публичный намеренно (страница локации открыта гостю), и ничего персонального в ответе нет. Но `character_id` из query уходит в `crud.finalize_due_sessions(session, character_id=...)` — то есть аноним может назвать чужого персонажа и **ускорить закрытие его просроченных сессий добычи**. Приватных чисел это не раскрывает (ответ от `character_id` не зависит), и операция идемпотентна — закрываются только сессии с `complete_at <= NOW()`, которые и так закрылись бы при следующем чтении владельцем. Поэтому в фикс по ревью не включено: гейт владельца здесь отнял бы у гостя страницу локации целиком.
**Возможное решение:** учитывать `character_id` только для авторизованного владельца (`get_optional_user` на маршруте уже есть), для остальных — общая ветка «финализировать все просроченные», она и так реализована при `character_id is None`.

---

## GLOBAL TASKS (стратегические задачи)

Крупные задачи по улучшению проекта. Каждая может быть разбита на подзадачи.

### T1. Frontend: переход на Tailwind CSS
**Сервис:** frontend
**Статус:** TODO
**Описание:** Заменить текущий подход к стилям (SCSS/CSS-файлы, inline-стили) на Tailwind CSS. Цель — унифицировать стилизацию, избавиться от разрозненных CSS-файлов, ускорить вёрстку.
**Стратегия: органическая миграция.** Не переписывать всё разом. Вместо этого:
- **Новые компоненты/страницы** — сразу писать на Tailwind, без создания CSS/SCSS-файлов.
- **Изменение существующего компонента** — если задача затрагивает стили компонента, мигрировать весь компонент на Tailwind в том же PR. Удалить старый CSS/SCSS-файл после миграции.
- **Задача не касается стилей** — не трогать стили, оставить как есть.

Таким образом проект постепенно перейдёт на Tailwind без выделения отдельного спринта на миграцию.
**Первый шаг (обязательный перед любой работой по T1):**
- Установить и настроить Tailwind CSS + PostCSS в Vite-проекте
- Настроить `tailwind.config.js` с кастомной цветовой палеттой и шрифтами проекта
- Убедиться, что Tailwind и старые SCSS сосуществуют без конфликтов
**Правила:**
- Не смешивать миграцию стилей с изменениями логики/функциональности — если задача требует и то и другое, делать два коммита.
- Сохранять визуальную идентичность — внешний вид компонента не должен меняться при миграции.
- Перед удалением CSS/SCSS-файла убедиться, что он не импортируется в других компонентах.

### T2. Backend: добавить Alembic во все сервисы
**Сервисы:** все backend-сервисы
**Статус:** DONE (9/9 сервисов с собственными таблицами готовы; проверено в FEAT-154, задача #29)
**Описание:** Цель — единообразное управление схемой БД через Alembic во всех сервисах с автоматическим запуском миграций при старте контейнера.

**Сервисы с Alembic (DONE — auto-migration при старте):**
- user-service — `alembic_version_user` (sync)
- character-attributes-service — `alembic_version_char_attrs` (sync)
- skills-service — `alembic_version_skills` (async)
- locations-service — `alembic_version_locations` (async)
- character-service — `alembic_version_character` (sync)
- inventory-service — `alembic_version_inventory` (sync)
- photo-service — `alembic_version_photo` (sync, mirror models, no own migrations)
- battle-service — `alembic_version_battle` (async) — added in FEAT-059
- notification-service — `alembic_version_notification` (sync)

**Сервисы без Alembic:** нет. autobattle-service своих таблиц не имеет — миграции ему не нужны.

**Стратегия: органическое добавление.** Не делать за раз. Вместо этого:
- **Работа в сервисе без Alembic** — добавить Alembic в рамках текущей задачи: инициализировать, создать initial-миграцию по существующим моделям, добавить `alembic` в `requirements.txt`.
- **Изменение схемы БД в сервисе с Alembic** — создать миграцию через `alembic revision --autogenerate`.
- **Задача не затрагивает БД** — не трогать.
**Правила:**
- **При добавлении Alembic в сервис** — настроить автоматический запуск миграций при старте контейнера: в Dockerfile CMD добавить `alembic upgrade head && uvicorn ...` (fail-fast — если миграция падает, сервис не стартует).
- **Каждый сервис должен использовать уникальное имя `version_table`** в `env.py` (например `alembic_version_user`, `alembic_version_photo`) для избежания коллизий в общей БД.
- **`create_all()` удалить** при добавлении Alembic — схемой БД управляет только Alembic.
- Initial-миграция должна точно соответствовать текущей схеме — не менять таблицы, типы, constraints.
- Для async-сервисов (battle-service) использовать async-конфигурацию Alembic (`run_async`).
- Не удалять SQL-бэкап из `docker/mysql/` — он останется как fallback.
- Добавление Alembic — отдельный коммит от основной задачи.

### T3. Frontend: переход с JavaScript на TypeScript (`.jsx` → `.tsx`)
**Сервис:** frontend
**Статус:** TODO
**Описание:** Сейчас весь фронтенд написан на JS (`.jsx`). Цель — постепенно перевести на TypeScript для типобезопасности, автодополнения и уменьшения runtime-ошибок.
**Стратегия: органическая миграция.** Не переписывать всё разом. Вместо этого:
- **Новые компоненты/файлы** — сразу писать на TypeScript (`.tsx` / `.ts`).
- **Изменение существующего файла** — если задача затрагивает логику компонента, мигрировать его на TypeScript в том же PR. Переименовать `.jsx` -> `.tsx` / `.js` -> `.ts`, добавить типы.
- **Задача не касается логики файла** — не трогать, оставить как есть.
**Первый шаг (обязательный перед любой работой по T3):**
- Убедиться, что `tsconfig.json` настроен в проекте (Vite поддерживает TS из коробки)
- Установить `typescript` и `@types/react`, `@types/react-dom` в devDependencies
- Настроить strict mode постепенно (начать с `"strict": false`, ужесточать позже)
- Убедиться, что `.tsx` и `.jsx` файлы сосуществуют без конфликтов
**Правила:**
- Миграция файла на TS — отдельный коммит от изменений логики.
- Не использовать `any` без явной причины. Если тип неизвестен — оставить `// TODO: type this` и использовать `unknown`.
- Для API-ответов создавать интерфейсы в отдельных файлах (`types/` или рядом с компонентом).
- Redux slices: типизировать state, action payloads, selectors.

### T4. Backend: органическое покрытие тестами (pytest)
**Сервисы:** все backend-сервисы
**Статус:** TODO
**Описание:** Сейчас тестов почти нет (тесты в character-service исправлены в FEAT-011). Цель — постепенно покрыть бекенд unit и integration тестами через pytest.
**Стратегия: органическое покрытие.** Не писать тесты для всего разом. Вместо этого:
- **Новая фича** → тесты обязательны для всех новых/изменённых эндпоинтов и CRUD-логики.
- **Изменение существующего кода** → покрыть тестами изменённую логику.
- **Код не менялся** → не трогать.
- **Фронтенд НЕ тестируем** — только backend Python-код.
**Правила:**
- Тесты размещаются в `services/<service>/app/tests/`.
- Фикстуры — в `conftest.py` (SQLite in-memory для тестов, override `get_db()`).
- Межсервисные HTTP-вызовы всегда мокать (`unittest.mock.patch`).
- Reviewer запускает `pytest` в затронутых сервисах как часть review-чеклиста.
- `pytest` добавлять в `requirements.txt` при первой работе с тестами в сервисе.

### T5. Frontend: адаптивность под мобильные устройства
**Сервис:** frontend
**Статус:** TODO
**Описание:** Сейчас почти ничего не адаптировано под мобильные устройства. Цель — постепенно сделать весь фронтенд рабочим на экранах 360px+.
**Стратегия: органическая адаптация.** Не переделывать всё разом. Вместо этого:
- **Новые компоненты/страницы** — сразу делать адаптивными.
- **Изменение стилей существующего компонента** — если задача затрагивает стили компонента, добавить адаптивность в том же PR.
- **Задача не касается стилей** — не трогать, оставить как есть.
**Правила:**
- Главное: всё должно помещаться и работать на экране 360px+. Контент не должен выходить за viewport.
- Навигация: должна быть доступна на мобильных (бургер-меню, сворачиваемые панели).
- Формы: поля ввода и кнопки удобны для touch.
- Изображения: масштабируются, не выходят за viewport.
- Таблицы: на мобильных либо горизонтальный скролл, либо переформатирование в карточки.
- Использовать Tailwind responsive breakpoints: `sm:`, `md:`, `lg:`, `xl:`.
- Не ломать десктопную версию при добавлении адаптивности.

---

## Статистика

| Приоритет | Количество |
|-----------|-----------|
| CRITICAL | 1 |
| HIGH | 10 |
| MEDIUM | 23 |
| LOW | 37 |
| **Итого** | **71** |

_Пересчитано 2026-09-14 (FEAT-163): таблица разошлась с содержимым файла — считаются только
незакрытые записи (`###`-заголовки без зачёркивания) в секциях CRITICAL/HIGH/MEDIUM/LOW._
