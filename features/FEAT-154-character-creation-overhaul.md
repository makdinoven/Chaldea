# FEAT-154: Переделка создания персонажа — «Регистрация Скитальца»

## Meta

| Field | Value |
|-------|-------|
| **Status** | OPEN |
| **Created** | 2026-09-06 |
| **Author** | PM (Orchestrator) |
| **Priority** | HIGH |

Statuses: `OPEN` → `IN_PROGRESS` → `REVIEW` → `DONE`
On completion the file is renamed: `FEAT-154-slug.md` → `DONE-FEAT-154-slug.md`

---

## 1. Feature Brief (filled by PM — in Russian)

### Описание

Текущее создание персонажа — сухая форма из 5 шагов, которая не передаёт ни атмосферы мира, ни смысла выбора. Шаг класса заполнен фиктивными данными-заглушками (`item1`, `skill3`, «Описание воина»), статы показаны голыми цифрами без объяснений, аватар не загружается вообще (на бэкенд уходит литерал `avatar: 'string'`), стартовая локация не назначается (`current_location_id` остаётся NULL), валидация отсутствует на обоих концах.

При этом в проекте уже накоплен большой объём качественного контента, который в создании персонажа никак не используется: 10 рас и ~35 подрас с артами и лором, модуль «Архив» с 95 лорными статьями в 11 категориях, иерархия мира из 3 материков / 5 стран / 26 регионов / 322 районов / 2260 локаций, реестр из 21 подкласса с описаниями, реальные стартовые наборы в БД.

**Цель фичи** — превратить форму в атмосферный и осмысленный сценарий «вступления в организацию Скитальцы», где игрок одновременно погружается в лор и понимает последствия своего выбора.

#### Ключевая рамка: Скитальцы

Все игровые персонажи так или иначе являются членами организации «Скитальцы» — внегосударственной военизированной организации наёмников с резиденцией на плавучем острове-крепости Цитадель. Это стартовая рамка мира, и она должна быть явно проговорена при создании персонажа.

Опорные факты из канона (статья Архива `/skitaltsy`):
- **УР (уровень развития)** — внутренняя система оценки Скитальцев. Это внутримировое объяснение игровых уровней: «Оценивает он не только самих скитальцев, но также и всё, что можно оценить». Новый персонаж получает УР 1.
- **Мегалинк** — браслет, выдаётся каждому при вступлении, позволяет понимать незнакомые языки и держать связь с Координатором.
- **Институт Координаторов** — члены организации, живущие на Цитадели и ведущие новобранцев. От лица Координатора говорит интерфейс мастера создания.
- **Законы организации** — Десять Правил, Анафема (исключение), Домнацио Мемориае (проклятие памяти), Книга Обид.
- **Отношение стран к Скитальцам различается**: Республика Белый Клин почитает как героев, Священное Королевство Орос считает еретиками, Империя Мидденгерд называет «Важными Партнёрами», Империя Шинзо предоставила вольности.
- **Год не хардкодить нигде.** Статья Архива заканчивается словами «1788 год — собственно, вы здесь», но это цель на полноценный запуск, а не текущее состояние: прод сейчас в альфа-тесте, часы показывают 1787. Пользователь выставил дату в статье до появления календаря и менять её не планирует. Год везде читается в рантайме из `GET /locations/game-time` (196 реальных дней = 1 игровой год, 4 сезона по 39 дней + 4 праздника-перехода по 10 дней, неделя = 3 дня).

Важно: рамка задаётся, но не запирает игрока. Игрок связывает предысторию со Скитальцами, а дальше по отыгрышу волен делать что угодно — вплоть до выхода из организации или попытки её возглавить.

#### Источник данных: только прод

⚠️ Локальный сид (`docker/mysql/init/01-seed-data.sql`) содержит **устаревший, отброшенный сеттинг** (мир «Ло-Ка», материк «Халдея», страны «Малахия», «Гноста», «Улус», 7 рас, 16 подрас). Актуальный сеттинг живёт только на проде: мир **Каркарис**, материк **Эйдонэя**, страны Мидденгерд / Шинзо / Орос / Юнион-Ист / Обратная Экзоста, 10 рас, ~35 подрас. Пересечений между ними практически нет.

**Ни один агент не должен брать лорные данные из локального сида.** Разработка и проверка ведутся на дампе прод-базы, развёрнутом локально.

### Бизнес-правила

**Общие**
1. Двухфазный флоу «заявка → модерация → персонаж» сохраняется без изменений.
2. Ни один выбор игрока не блокирует другой. Нетипичные сочетания (демон из Ороса, низкорослый рюджин) разрешены — система лишь помечает их как редкие. Решение принимает модератор.
3. Все тексты, видимые игроку, — на русском.
4. Описания стран из таблицы `Countries` — админские заглушки и **не должны показываться игроку**. Лорные тексты для игрока берутся из Архива.

**Шаги мастера** — 5 шагов вместо текущих 5, с иной группировкой (было 8 в черновике, объединено):
1. **Кровь** — раса и подраса в одном шаге (выбор расы раскрывает подрасы в той же панели).
2. **Родина** — страна происхождения.
3. **Путь** — класс, его подклассы и стартовый набор.
4. **Личность** — анкета и аватар.
5. **Контракт** — стартовая локация, паспорт, отправка заявки.

Перед первым шагом — короткая заставка-пролог (2–3 фразы) от лица Координатора на Цитадели.

**Статы**
5. Стат-пресет подрасы всегда равен ровно 100 очкам; на уровне персонаж получает +10 очков. Это соотношение проговаривается игроку.
6. Каждый стат сопровождается объяснением эффекта и производными значениями (HP, мана, энергия, выносливость, уклонение, крит, инициатива).
7. Показывается словесный архетип билда и сравнение со средним по подрасам.

**Происхождение**
8. Происхождение становится сущностью-справочником (страна с гербом, описанием и ссылкой на статью Архива), а не свободным текстовым полем на 20 символов, как сейчас.
9. Список стран происхождения шире списка играбельных стран на карте: включает Железный Пояс, Эльфийские Сады, Республику Белый Клин.
10. На шаге показывается, как выбранная страна относится к Скитальцам.
11. Для каждой подрасы отмечаются характерные страны; нехарактерный выбор помечается как редкий, но разрешается.

**Класс**
12. Фиктивные данные `INITIAL_CLASSES` удаляются. Состав стартового набора берётся из БД (`starter_kits`): реальные предметы с иконками и описаниями, реальные стартовые навыки.
12a. **Стартовый набор зависит не только от класса, но и от происхождения.** Воин из Шинзо и воин из Мидденгерда получают разную стартовую одежду и оружие. Набор задаётся парой (класс × происхождение) и настраивается из админки.
12b. Если для пары (класс × происхождение) набор не задан, используется набор по умолчанию для этого класса. Система обязана работать, пока заполнены не все комбинации.
12c. На шаге «Путь» игрок видит набор, соответствующий уже выбранному происхождению. Значит, шаг «Родина» идёт раньше шага «Путь» — порядок шагов это уже обеспечивает.
12d. **Фактически выданный набор замораживается в момент одобрения заявки.** Паспорт показывает то, что персонажу действительно выдали, а не пересчитывает состав заново. Последующее редактирование набора в админке не меняет паспорта уже созданных персонажей — паспорт является лорной записью «тебе это выдали при вступлении», и задним числом она меняться не должна.
13. Показываются 7 подклассов выбранного класса с описаниями из реестра `subclasses.py` — как предпросмотр «куда растёт этот путь».

**Внешность**
14. У подрасы появляется отдельное поле «Отличительные особенности» — только про облик (кожа, рост, чешуя, рога, хвост, глаза), без географии и политики. Редактируется из админки.
15. У подрасы появляется характерный диапазон роста. Значение вне диапазона вызывает мягкое предупреждение, но не блокирует отправку.
16. На шаге «Личность» рядом с полем внешности постоянно видна памятка: портрет подрасы и её отличительные черты.
17. Если поле «Отличительные особенности» не заполнено, показывается обычное описание подрасы (фича работает до наполнения контентом).

**Стартовая локация**
18. Появляется признак «стартовая точка» у локации и краткий текст «почему герои начинают здесь». Управляется из админки.
19. Игрок выбирает стартовую точку из курируемого списка (десятки вариантов), а не из всех 2260 локаций.
20. При одобрении заявки `current_location_id` заполняется выбранной локацией.

**Аватар**
21. Загрузка аватара при создании должна работать. Литерал `avatar: 'string'` устраняется.

**Даты и стаж**
22. Различаются две даты: **дата регистрации** (системная, проставляется при одобрении заявки) и **«в Скитальцах с»** (внутримировая, указывает игрок).
23. Стаж ограничен: не раньше, чем позволяет возраст персонажа, и не позже текущей игровой даты.
24. **Стаж не даёт никаких механических преимуществ.** УР нового персонажа всегда 1. Стаж — исключительно отыгрыш, достоверность оценивает модератор.

**Паспорт**
25. Финальный экран — «паспорт Скитальца», оформленный как разворот страницы из книги/реестра Цитадели, в визуальном языке Архива.
26. Паспорт реализуется **одним переиспользуемым компонентом** и применяется в четырёх местах: финальный шаг создания, страница персонажа в профиле, карточка в общем списке персонажей (`/characters/list`), экран модератора при рассмотрении заявки.
27. Состав паспорта: портрет, печать Скитальцев, номер Мегалинка, УР, дата регистрации и стаж, имя, «{подраса} из {страна}» с гербом родины, класс, статы с производными, стартовый набор, точка первого назначения, тексты анкеты.

**Модерация**
28. У отказа появляется причина; игрок получает уведомление об отказе.
29. Появляется страница «мои заявки» со статусом заявки.
30. Отклонённую заявку можно отредактировать и переотправить, не заполняя всё заново.
30a. **Отклонить можно только заявку в статусе `pending`.** Попытка отклонить уже одобренную или уже отклонённую заявку возвращает 409 с русским сообщением. Сейчас проверки нет, и одобренную заявку можно отклонить, оставив созданного персонажа привязанным к отклонённой заявке.
30b. Причина отказа длиннее допустимой возвращает **400 с русским сообщением**, а не стандартный 422 — по языковой политике проекта все ошибки API, видимые пользователю, на русском.
31. Лимит в 5 персонажей проверяется **при подаче заявки**, а не только при одобрении.

**Валидация и черновик**
32. Обязательные поля действительно блокируют отправку, с понятными русскими сообщениями.
33. Нельзя перепрыгнуть на следующий шаг, минуя незаполненные предыдущие.
34. Бэкенд проверяет существование расы, подрасы и класса, а также принадлежность подрасы выбранной расе.
35. Черновик анкеты автосохраняется, чтобы случайная перезагрузка не стирала введённое.

### UX / Пользовательский сценарий

1. Игрок открывает `/createCharacter`. Видит короткий пролог: он на Цитадели, перед ним Координатор Скитальцев, сейчас его внесут в реестр.
2. **Кровь.** Выбирает расу — видит арт, лор, тултипы Архива по именам собственным. Раскрываются подрасы. Выбирает подрасу — появляется стат-пресет с расшифровкой и производными, словесный архетип.
3. **Родина.** Выбирает страну происхождения: герб, карта, лор из Архива, отношение страны к Скитальцам. Нехарактерные для подрасы страны помечены как редкие.
4. **Путь.** Выбирает класс: реальный стартовый набор, стартовые навыки, 7 подклассов как предпросмотр развития.
5. **Личность.** Заполняет имя, возраст, пол, рост, вес, внешность, биографию, характер; загружает аватар. Рядом с полем внешности — памятка об отличительных особенностях подрасы. Под биографией — подсказка Координатора «Как ты оказался среди Скитальцев?». Указывает стаж «в Скитальцах с».
6. **Контракт.** Выбирает точку первого назначения из курируемого списка стартовых локаций на карте. Видит блок о законах организации со ссылкой на статью Архива. Разворачивается паспорт Скитальца. Нажимает «Подписать контракт».
7. Заявка уходит на модерацию. Игрок видит подтверждение и может следить за статусом на странице «мои заявки».
8. Модератор открывает заявку и видит тот же паспорт. Одобряет — персонаж создаётся, получает статы, стартовый набор, навыки и стартовую локацию; игроку приходит уведомление. Отклоняет с причиной — игрок получает уведомление и может отредактировать заявку и переотправить.
9. Другие игроки видят готового персонажа в общем списке в виде того же паспорта.

### Edge Cases

- Что если игрок выбрал нехарактерную для подрасы страну происхождения? → Разрешено, помечается как редкое, решает модератор.
- Что если рост вне характерного для подрасы диапазона? → Мягкое предупреждение, отправка не блокируется.
- Что если у подрасы не заполнено поле «Отличительные особенности»? → Показывается обычное описание подрасы.
- Что если игрок указал стаж больше собственного возраста? → Валидация не пропускает.
- Что если игрок указал стаж позже текущей игровой даты? → Валидация не пропускает.
- Что если у игрока уже 5 персонажей? → Отказ на этапе подачи заявки, с понятным сообщением.
- Что если игрок обновил страницу посреди заполнения? → Черновик восстанавливается.
- Что если аватар не загрузился (S3 недоступен)? → Ошибка показывается игроку; поведение при отправке без аватара определяет Архитектор.
- Что если админ не отметил ни одной стартовой локации? → Поведение определяет Архитектор (нужен безопасный fallback, персонаж не должен остаться с NULL-локацией).
- Что если заявка одобрена, а выбранная стартовая локация к тому моменту удалена? → Поведение определяет Архитектор.
- Что если игрок отклонён и переотправляет заявку — лимит персонажей считается повторно? → Считаются только активные персонажи и заявки в статусе pending.

### Ответы на открытые вопросы архитектора (2026-09-06)

1. **Наполнение контентом** — пользователь заполняет сам, PM должен выдать точный перечень того, что нужно заполнить. Админка выкатывается раньше контента.
2. **Список стран происхождения** — восемь: Мидденгерд, Шинзо, Орос, Юнион-Ист, Обратная Экзоста, Железный Пояс, Эльфийские Сады, Республика Белый Клин. Где статьи в Архиве нет — она будет написана, поэтому поле ссылки на статью остаётся, но не обязательно.
3. **Стартовый набор в паспорте** — показывается выданный набор (лорная запись «тебе это выдали»), а не текущий инвентарь. Дополнительно: набор должен быть настраиваемым и зависеть от происхождения — см. правила 12a-12c.
4. **Паспорт в списке персонажей** — в сетке компактная карточка, полный разворот паспорта только в модалке.
5. **Брошенные аватары в S3** — уборка выносится в отдельную задачу, не в эту фичу.
6. **Удаление происхождения** — мягкое удаление (скрытие) принято.

### Вопросы к пользователю (если есть)

- [x] Главное — погружение или смысловая подача? → И то, и другое.
- [x] Меняется ли структура выбора? → Раса/подраса/класс остаются, добавляются происхождение и стартовая локация. Предыстория, биография, внешность остаются свободными текстовыми полями.
- [x] Модерация остаётся? → Да.
- [x] Чинить ли аватар? → Да, в рамках этой фичи.
- [x] Расовые навыки под каждую расу/подрасу? → Нет, отдельная фича на будущее (пассивки и уникальные фишки).
- [x] Паспорт — как должен выглядеть? → Антуражно, как страница из книги/Архива.
- [x] Показывать ли паспорт в общем списке персонажей? → Да, тот же компонент.
- [x] Как быть с датой контракта при отыгрыше «я тут давно»? → Две даты: системная регистрация и внутримировой стаж без механических бонусов.
- [x] Показывать ли отличительные особенности подрасы при описании внешности? → Да, отдельным полем + памятка на шаге анкеты.
- [ ] Развернуть дамп прод-базы локально для разработки → требуется пароль от VPS.

---

## 2. Analysis Report (filled by Codebase Analyst — in English)

> Scope note: this section records the **current state and constraints only**. Design decisions (fallbacks, new API shapes, where the origin registry lives) are the Architect's call and are deliberately left open, with the constraint that forces each decision spelled out.

### Affected Services

| Service | Type of Changes | Files |
|---------|----------------|-------|
| **character-service** | Model + schema + validation + 2 new player endpoints + approve/reject rework + new HTTP client to locations-service + Alembic migration | `app/models.py` (`CharacterRequest` L5-27, `Character` L30-62, `Subrace` L77-87), `app/schemas.py` (`CharacterRequestBase` L7-21, `StarterKit*` L312-335), `app/crud.py` (`create_character_request` L23, `create_preliminary_character` L51, `update_character_request_status` L86, `get_moderation_requests` ~L244), `app/main.py` (L62 create, L180-405 approve, L1073 reject, L1107 moderation list, L1690 races, L1124 starter-kits), `app/config.py` (L9-13 — no locations URL), `app/producer.py`, `app/alembic/versions/019_*.py` (new) |
| **locations-service** | Model + admin CRUD + curated public endpoint + Alembic migration | `app/models.py` (`Location` L104-122, `Country` L25-40), `app/schemas.py`, `app/crud.py`, `app/main.py` (locations CRUD block, archive router L2874-2910, game-time L1669), `app/alembic/versions/033_*.py` (new) |
| **user-service** | RBAC only — seed new permissions | `alembic/versions/0026_*.py` (new). No model change. |
| **photo-service** | Possibly one new generic/pre-entity upload endpoint (see Risk R1) | `main.py` (flat, **no `app/` dir**), `utils.py`. **Has no `alembic/versions/` directory at all** — must be created before any migration. |
| **skills-service** | None expected — `GET /skills/subclasses` already public (`app/main.py:360`) | — |
| **inventory-service** | None expected — `GET /inventory/items/{id}` already public (`app/main.py:158`) | — |
| **frontend** | Full rewrite of the wizard, new passport component, new "my requests" page, admin form extensions | `src/components/CreateCharacterPage/**`, `src/components/pages/CharactersPage/CharactersListPage.tsx`, `src/components/Admin/RequestsPage/RequestsPage.tsx` + `src/components/Admin/Request/Request.tsx`, `src/components/Admin/AdminRaces/SubraceForm.tsx`, `src/components/AdminLocationsPage/EditForms/EditLocationForm/`, `src/components/App/App.tsx` (routes), `src/redux/slices/racesSlice.ts`, `src/api/` |
| **notification-service** | None — reuse the existing `general_notifications` queue | — |

---

### Existing Patterns

**character-service** — sync SQLAlchemy (`Session`, `Depends(get_db)`), Pydantic v1 (`class Config: orm_mode = True`), Alembic present (`version_table = alembic_version_character`, head `018_add_mob_packs`, **next = 019**). ~93 endpoints are declared `async def` but perform blocking DB I/O (known debt, `docs/ISSUES.md` HIGH). Cross-service calls use `httpx.AsyncClient` inside `crud.py`. `main.py` no longer calls `create_all()` — Alembic owns the schema.

**locations-service** — async SQLAlchemy (`AsyncSession` + aiomysql), Pydantic v1, Alembic present (`alembic_version_locations`, head `032_add_action_gates`, **next = 033**). Router prefix `router = APIRouter(prefix="/locations")` (`main.py:113`), plus separate `archive_router` (`/archive`) and a rules router.

**user-service** — sync SQLAlchemy, Alembic (`alembic_version_user`, head `0025_add_gathering_permissions`, **next = 0026**). Bare-numeric revision ids (`'0025'`), unlike the `NNN_slug` style elsewhere.

**photo-service** — sync SQLAlchemy, **flat module layout at the service root** (`services/photo-service/main.py`, not `app/main.py`), Pydantic v1, mirror models only. Alembic configured (`alembic_version_photo`) but **zero migrations and no `versions/` directory**.

**Authentication (all backend)** — no local JWT verification outside user-service. Every service copies `auth_http.py` (12 near-identical copies) which does `requests.get(f"{AUTH_SERVICE_URL}/users/me", headers={"Authorization": ...}, timeout=5)` and hydrates `UserRead(id, username, role, permissions[])`. Three tiers:
- `get_current_user_via_http` — any authenticated user
- `get_admin_user` — `role in ("admin", "moderator")` (no permission granularity)
- `require_permission("module:action")` — exact string membership in `user.permissions`, no wildcards
- locations-service additionally has `get_strict_admin_user` (`role == "admin"` only, `auth_http.py:58-70`)

**RBAC** — tables `roles`/`permissions`/`role_permissions`/`user_permissions` in user-service (`models.py:7-46`). Permission string = `f"{module}:{action}"`. Role ids are fixed constants: **1=user(0), 2=editor(20), 3=moderator(50), 4=admin(100)**. `crud.py:33-35`: **role `admin` receives every row in `permissions` automatically** — new permissions never need an explicit admin grant.

**Alembic permission-seeding pattern** — the current idiom (0013 onward, canonical example `user-service/alembic/versions/0025_add_gathering_permissions.py`) is idempotent SELECT-then-INSERT with `LAST_INSERT_ID()` and a `ROLE_ACTIONS = {3: [...], 2: [...]}` map. **Do not** use the old hardcoded-id `op.bulk_insert` style from 0006-0011.

**Frontend** — React 18 + Vite, Redux Toolkit, **default axios instance** with relative paths (no shared client for the main app); interceptors attached once in `src/api/axiosSetup.ts` (Bearer injection, 401 single-flight refresh + retry, 403 toast). Router is `src/components/App/App.tsx` (there is no `src/App.tsx`); `ProtectedRoute` is always applied inline per route, never as a layout route. Tailwind + a legacy SCSS tail.

**character-service tests** — `app/tests/`, 37 files. Each module builds its own in-memory SQLite engine and calls `Base.metadata.create_all()`, with `conftest.py:60` `_seed_reference_data` inserting FK rows for races/subraces/classes.

---

### Cross-Service Dependencies

Existing (character-service `config.py:9-13` + `crud.py`):
```
character-service ──HTTP──> inventory-service            (POST {INVENTORY_SERVICE_URL},        crud.py:474)
character-service ──HTTP──> skills-service               (POST {SKILLS_SERVICE_URL},           crud.py:496)
character-service ──HTTP──> skills-service               (POST .../assign_multiple,            crud.py:736)
character-service ──HTTP──> character-attributes-service (POST {ATTRIBUTES_SERVICE_URL},       crud.py:525)
character-service ──HTTP──> user-service                 (POST /users/user_characters/,        crud.py:609)
character-service ──HTTP──> user-service                 (PUT  /users/{id}/update_character,   crud.py:623)
character-service ──HTTP──> user-service                 (GET  /users/me — every auth dep)
character-service ──AMQP──> general_notifications        (producer.py:9)
```

**New dependency required — this edge does not exist today:**
```
character-service ──HTTP──> locations-service  (validate / resolve the chosen starting location)
```
`config.py` has **no `LOCATIONS_SERVICE_URL`** — the setting, the client function and its failure policy are all new. This is the single largest new integration in the feature.

**Avatar path (currently broken end-to-end):**
```
frontend ──multipart──> photo-service /photo/change_character_avatar_photo ──> characters.avatar
```
…is unusable at creation time (see R1).

**Reads the wizard will need:**
```
frontend ──> character-service  GET /characters/races          (public, main.py:1690)
frontend ──> character-service  GET /characters/starter-kits   (public, main.py:1124)
frontend ──> skills-service     GET /skills/subclasses         (public, main.py:360)
frontend ──> inventory-service  GET /inventory/items/{id}      (public, main.py:158)
frontend ──> skills-service     GET /skills/{skill_id}         (public, main.py:374)
frontend ──> locations-service  GET /archive/articles/preview/{slug}  (public, main.py:2887)
frontend ──> locations-service  GET /locations/game-time       (public, main.py:1669)
```

**Notification transport (for the rejection notice, rule 28)** — it is **WebSocket, not SSE**. Publish to the durable queue `general_notifications` on the **default exchange** (routing_key == queue name), payload:
```json
{"target_type":"user","target_value":<user_id>,"message":"...","ws_type":"<optional>","ws_data":{...}}
```
Consumer: `notification-service/app/consumers/general_notification.py` (pika, daemon thread) → row in `notifications` (`models.py:6-13`: id, user_id, message, status enum unread|read, created_at) → `ws_manager.send_to_user`. Client socket: `@app.websocket("/notifications/ws")` (`notification-service/app/main.py:62`), token via `?token=` query param. Frontend consumer: `src/hooks/useWebSocket.ts` (connect L151, `switch (parsed.type)` L172-411). Adding `ws_type`/`ws_data` yields a structured message; omitting them yields the generic `{"type":"notification"}`. **Rejection needs only a new producer call in character-service — no notification-service change.**

---

### DB Changes

Owner mapping matters because all services share one MySQL database `mydatabase`.

**1. Distinctive features + height range for a subrace (rules 14-15, 17)** — table `subraces`, **owned by character-service**.
New nullable columns, e.g. `distinctive_features TEXT NULL`, `height_min INT NULL`, `height_max INT NULL`. All nullable so rule 17's "fall back to `description`" works with no backfill. Note `subraces.description` currently carries appearance prose mixed with geography/politics — splitting it is a **content task, not a migration**. Consumers of `subraces`: character-service (owner), photo-service (mirror model, writes `image` only), skills-service (`SUBRACE_SKILL_ID = 7` logic). Additive nullable columns are safe for all of them.

**2. Origin country registry (rules 8-11)** — **ownership is an open architectural question.** The list must be *wider* than the playable `Countries` (adds Железный Пояс, Эльфийские Сады, Республика Белый Клин), and rule 4 forbids showing `Countries.description` to players. Facts constraining the choice:
   - `Countries` (locations-service, `models.py:25-40`) already has `emblem_url` and `is_hidden`, but its `description` is an admin stub.
   - There is **no** link from a country to an Archive article, and no "attitude toward Скитальцы" field anywhere.
   - A join table for "characteristic countries per subrace" (rule 11) crosses the character-service/locations-service ownership line whichever way it is placed.
   New columns/tables needed regardless: an origin reference (name, emblem, archive slug, attitude text) + a subrace↔origin affinity table + `character_requests.origin_id` / `characters.origin_id`.

**3. Starting-location flag + text (rules 18-20)** — table `Locations`, **owned by locations-service**. Confirmed absent today: `Location` (`models.py:104-122`) has `recommended_level`, `marker_type` enum('safe','dangerous','dungeon','farm'), `quick_travel_marker`, `no_quick_move`, `sort_order` — **no `is_starting`, no `is_safe`, and no `is_hidden`** (`is_hidden` exists only on `Country`, L37). New: `is_starting BOOLEAN NOT NULL DEFAULT 0` (+ index) and `starting_blurb TEXT NULL`.

**4. Rejection reason (rule 28)** — table `character_requests` (character-service). New `rejection_reason TEXT NULL`. `crud.update_character_request_status` (L86) currently writes only `status`.

**5. Registration date + in-world tenure (rules 22-24)** — `character_requests` already has `created_at TIMESTAMP server_default now()` (submission time, **not** approval time). `Character` has **no** date column at all. New: `characters.registered_at` (set at approval) and a player-supplied tenure field on both request and character.
   ⚠️ **Constraint for rule 23:** the game calendar has no absolute date. `GET /locations/game-time` (`main.py:1669`) returns only `{epoch, offset_days, server_time}`; the client computes `{year, segment_name, segment_type, week, is_transition}` via `crud.compute_game_time` (`crud.py:2281`) with `DAYS_PER_YEAR=196`, `DAYS_PER_WEEK=3` and 8 segments (4 seasons of 39 real days + 4 transitions of 10). **`year` is a counter starting at 1 — the lore year 1788 exists nowhere in code or DB.** So "not later than the current in-game date" must be expressed in `{year, segment, week}` terms, and the 1788 framing is presentation-only. Duplicated algorithm lives at `src/utils/gameTime.ts` (`YEAR_SEGMENTS` L18, `DAYS_PER_YEAR` L29).

**6. Megalink number (rule 27)** — no such column anywhere. Whether it is stored or derived from `characters.id` is an Architect decision.

**7. Starting location on the character** — `characters.current_location_id BIGINT NULL` already exists (`models.py:54`). No migration needed; only `crud.create_preliminary_character` (L51-80) must start populating it — it currently sets 19 fields and omits `current_location_id` entirely.

**Alembic summary:**

| Service | version_table | Current head | Next |
|---|---|---|---|
| character-service | `alembic_version_character` | `018_add_mob_packs` | **019** |
| locations-service | `alembic_version_locations` | `032_add_action_gates` | **033** |
| user-service | `alembic_version_user` | `0025_add_gathering_permissions` | **0026** |
| photo-service | `alembic_version_photo` | *none (no `versions/` dir)* | 001 — dir must be created first |
| skills / inventory / char-attrs | `alembic_version_skills` / `_inventory` / `_char_attrs` | `008` / `017` / `007` | not expected to change |

⚠️ **CLAUDE.md §7 is stale:** it lists notification-service and battle-service as "no Alembic". Both **do** have it configured with migrations (`alembic_version_notification`, head `0010`, 10 migrations; `alembic_version_battle`, head `005_battle_parties`, 5 migrations). Neither is affected by this feature, but the doc should be corrected.

**New RBAC permissions required (user-service migration 0026):** starting-location admin fits the existing `locations:update`; subrace fields fit `races:update`. A genuinely new origin-registry module would need its own `origin:read|create|update|delete` (or equivalent). Admin gets them automatically; moderator/editor grants go in `ROLE_ACTIONS`.
⚠️ Pre-existing gap worth flagging: `gametime:read` / `gametime:update` are **enforced** at `locations-service/app/main.py:1691,1713` but **seeded by no migration** — they work only via the admin-gets-everything shortcut. Same for the `moderation` module used by the frontend admin hub. Not caused by this feature; do not silently inherit the pattern.

---

### Current-State Findings That Shape the Work

**Backend**
- `POST /characters/requests/` (`main.py:62`) **does** require auth (`get_current_user_via_http`, L63) and checks `request.user_id != current_user.id` → 403. What is missing is **domain** validation: no race/subrace/class existence check, no subrace↔race consistency, no character-limit check (rule 31, 34). Correction to the brief, which stated "валидации нет".
- `schemas.CharacterRequestBase` (L7-21) has **zero validators** and declares `avatar: str` as **required with no default** — this is precisely why the frontend sends the literal `'string'`.
- **Two different 20-char limits, easy to confuse.** (a) `background` is unlimited `Text` in the DB but is rendered as the "Происхождение" input with `maxLength: 20` in `BiographyPage.jsx:57` — **that limit is frontend-only**. (b) `CharacterRequest.name` is genuinely `String(20)` (`models.py:9`) while `Character.name` is `String(255)` (`models.py:34`) — a real asymmetry that makes long NPC names unable to round-trip into a claim request (`main.py:132` copies `character.name` into the 20-char column). There is no `origin` column anywhere.
- `Character` has **no creation timestamp at all**. The only date in the flow is `CharacterRequest.created_at` (submission, not approval), reachable only via the nullable `request_id` — so NPC/claim-created characters have no derivable date. Rule 22 needs a new column regardless.
- `schemas.CharacterRequest` (the `response_model` of `POST /requests/`) omits `created_at`, `request_type` and `character_id`, so the client never learns the submission timestamp.
- `POST /requests/{id}/reject` (`main.py:1073`) sets status only — no reason, no notification.
- `GET /characters/moderation-requests` (`main.py:1107`) returns **all** statuses (`crud.py:244` filters `status.in_(['pending','rejected','approved'])`) with **no pagination**.
- **No player-facing endpoint returns the current user's own requests.** The 8 `get_current_user_via_http` call sites in `main.py` are L63 (create), L83 (claim), L162 (count), L1185/L1207 (titles), L3099/L3129 (teleport). Rule 29 needs a new endpoint.
- `POST /requests/claim` (`main.py:79-130`) **already implements exactly the pattern rule 31 needs**: character-limit check via raw SQL `SELECT COUNT(*) FROM users_character WHERE user_id = :uid` (L102-105, note: `users_character` is a **user-service** table) plus a duplicate-pending-request guard (L118-120). Reuse this shape.
- The character limit is also exposed read-only at `GET /characters/my-character-count` (`main.py:159-176`). ⚠️ Both existing limit checks **swallow any exception and fall through as if under the limit** (`main.py:114-115`, `L220-222`) — if `users_character` is unreachable the limit silently stops being enforced. Copying this pattern into request creation would inherit that weakness; note also that `real_db_client`-based tests run against SQLite where `users_character` does not exist.
- ⚠️ **Approve does the same work twice.** In `main.py:180-405` the handler makes synchronous HTTP calls (inventory L299, skills L317, attributes L329) **and then also publishes to RabbitMQ** for the same three payloads (L375, L382, L388). The consumers in inventory/skills/char-attrs also apply them, so a starter kit can be granted twice unless those consumers are idempotent. Pre-existing; touching approve puts it in scope.
- Approve's two notification sites (L254 claim branch, L365 creation branch) are mutually exclusive, not duplicates.
- `generate_attributes_for_subrace` (`crud.py:428`) reads `subraces.stat_preset` and falls back to a hardcoded all-10s dict with a warning if absent.
- `presets.py` is **confirmed dead** — the only references are a comment in `alembic/versions/002_add_race_subrace_columns.py:2,19`.
- **Starter-kit data is id-only.** `StarterKitItem = {item_id, quantity}` and `StarterKitSkill = {skill_id}` (`schemas.py:312-318`). Rule 12 ("real items with icons and descriptions") requires resolving each id. The admin page does this via `/inventory/items` (full catalogue) and **`/skills/admin/skills/` — an admin endpoint players cannot call** (`StarterKitsPage.tsx:65-68`). Public per-id resolution does exist (`GET /inventory/items/{id}`, `GET /skills/{skill_id}`), but there is **no public bulk lookup**, so a naive port yields N+1 requests.
- `subclasses.py` holds exactly **21** `SubclassDef(key, class_id, name, description)` entries, served publicly by `GET /skills/subclasses?class_id=` (`skills-service/app/main.py:360`, schema `SubclassRead` L266). Ready to use for rule 13.
- There is **no public `GET /characters/classes`** — `classes` (`models.py:89-93`: `id_class`, `name`, `description`) is exposed nowhere for players. Needed to replace `INITIAL_CLASSES`.
- Stat derivations (character-attributes-service `crud.py:16-63`, `constants.py`): `max_health=100+health*10`, `max_mana=75+mana*10`, `max_energy=50+energy*5`, `max_stamina=100+stamina*5`, `dodge=5+agility*0.1+luck*0.1`, `crit=20+luck*0.1`, `res_effects=endurance*0.2+luck*0.1`; damage from `CLASS_MAIN_ATTRIBUTE = {1:"strength", 2:"agility", 3:"intelligence"}`. Initiative (battle-service `redis_state.py:95`): `agility*1.0 + (strength+intelligence)*0.75`. Preset always sums to 100 (enforced client-side in `SubraceForm.tsx:29-30,142`); +10 points per level (`character-service/crud.py:664`).

**Locations / Archive**
- Public archive endpoints (all no-auth, `locations-service/app/main.py`): `/archive/articles` L2874, **`/archive/articles/preview/{slug}` L2887** (schema `ArchiveArticlePreview`: `id, title, slug, summary, cover_image_url` — `schemas.py:1134`), `/archive/articles/{slug}` L2893, `/archive/categories` L2899, `/archive/featured` L2905.
- `GET /locations/map/graph` (L1584) is `get_strict_admin_user` — **unusable for player UI**, as noted.
- `move_and_post` has a special branch: when `current_location_id IS NULL`, movement to **any** location is permitted at `movement_cost=0`. This is the current de-facto safety net for NULL-location characters and would be closed by rule 20.

**Frontend**
- `CreateCharacterPage.tsx` (286 lines) — `INITIAL_CLASSES` L22-74 is mock data (`item1`, `skill3`, "Описание воина"); only races are fetched, via a raw `axios.get('/characters/races')` at L120 that bypasses the existing `fetchRaces` thunk.
- **Correction to the brief:** `racesSlice.ts` is **not unused** — it is registered in `store.ts:18,54` and drives `AdminRacesPage.tsx`, `RaceForm.tsx`, `SubraceForm.tsx`, `StatPresetEditor.tsx`. It is simply not wired into the wizard.
- `SubmitPage.tsx` — avatar is preview-only (`URL.createObjectURL`, L102-113), `avatar: 'string'` at L72, POST at L80. Not responsive (`px-[120px]` L132) → T5 applies.
- Legacy files requiring T1/T3 migration: `ClassPage.jsx` (29 lines + `ClassPage.module.scss` 7), `ClassItem.jsx` (76 + SCSS 129), `BiographyPage.jsx` (109 + SCSS 34), plus shared `CommonComponents/Input|Select|Textarea/*.jsx`.
- Dead code: the whole `RacePage/RaceCarousel/` folder (`RaceCarousel.tsx` 86 lines, `ArrowButton/ArrowButton.tsx` 33) — no importers.
- Moderator UI: `Admin/RequestsPage/RequestsPage.tsx` (85) + `Admin/Request/Request.tsx` (152, approve L54 / reject L67, no reason input). Route `requestsPage` guarded by `characters:approve` (`App.tsx:124-128`).
- `CharactersListPage.tsx` (471) — detail modal at L362-471 already renders Внешность L436, Биография L443, Характер L450, Предыстория L457. `openDetail` (L131-152) re-fetches `/characters/list` with `page_size:1` and a name search because **no `GET /characters/{id}` is used**; a passport component will likely need a proper detail endpoint. There is **no public per-character route** — the modal is the only public per-character view.
- Hover-tooltip precedent for Archive lore (rule: lore tooltips): `CommonComponents/ArchiveLinkPreview/ArchiveLinkPreview.tsx` — `previewCache` Map L25, `HOVER_DELAY_MS=200`, `createPortal` L49, viewport clamping L40-47, parchment styling hardcoded at L62 (`bg-[#f5e6c8]`) with `MedievalSharp` at L86. `CommonComponents/Tooltip/Tooltip.jsx` is a **stub** (14 lines, never renders `content`) — do not build on it.
- Upload UI precedent: `AdminRacesPage.tsx` uses a **two-phase** pattern — save entity, get id, then dispatch `uploadRaceImage`/`uploadSubraceImage` (L88, L164). That pattern is exactly what is unavailable at character creation (R1).

**Design System** (`docs/DESIGN-SYSTEM.md`, 641 lines; classes in `src/index.css` `@layer components`)
- Directly reusable for the passport and wizard: `gold-text` (L14), `gold-outline` / `gold-outline-thick` (L24/L44), `gray-bg` (L53), `gradient-divider` (L79) and `gradient-divider-h` (L95) for a book gutter, `hover-gold-overlay` (L113), `dark-bottom-gradient` (L133), `btn-blue` (L150), `btn-line` (L170), `site-link` (L193), `modal-overlay` (L243) + `modal-content` (L256), `input-underline` (L284), `textarea-bordered` (L305), `gold-checkbox` (L269), `gold-scrollbar` (L322), `site-tooltip` (L343), `image-card` (L356), `chip-outline` / `chip-outline-active` (L496/L508), `stat-bar` / `stat-bar-fill-hp|mana|energy|stamina` (L423-450), `item-cell` (L369), `rarity-*` (L394-414), `prose-rules` (L619) for Archive-style rich text.
- Tokens (`tailwind.config.js`): `gold.light #fff9b8` / `gold #f0d95c` / `gold.dark #bcab4c`, `site.blue #76a6bd`, `site.red #F37753`, `site.bg rgba(9,10,16,.62)`, `site.dark #1a1a2e`, `input #c6c4c4`, `rarity.*`, `stat.*`; `rounded-card` 15 / `card-lg` 20 / `card-xl` 29 / `map` 40; `shadow-card|hover|pressed|modal|dropdown`; `maxWidth.container` 1360px; `font-montserrat`; `duration-200`, `ease-site`, `animate-fade-in`.
- ⚠️ **Gap for rule 25:** there is **no parchment/cream color token and no serif or medieval font family** in `tailwind.config.js`. The only book-like surface in the app is hardcoded inside `ArchiveLinkPreview.tsx:62,86`. A "page from the Citadel register" look requires **extending the design system** — which CLAUDE.md §10.10 explicitly permits — rather than inventing one-off hex values inline.
- Mandatory rules that apply to every file touched here: T1 Tailwind-only (no new SCSS), T3 `.jsx` → `.tsx`, T5 mobile responsiveness from 360px, and the `React.FC` ban.

---

---

### Pre-existing Bugs Found During Analysis (not part of this feature)

Recorded here rather than in `docs/ISSUES.md` because this task's scope was limited to section 2 of this file. **PM should have these filed in `docs/ISSUES.md` separately.**

1. **HIGH — Unauthenticated state-mutating endpoints in character-service.** `PUT /characters/{id}/deduct_points` (`main.py:1266`), `PUT /characters/{id}/update_location` (`main.py:1493`), `POST /characters/{id}/set_travel_cooldown` (`main.py:3204`) have **no auth dependency and no ownership check**. `update_location` in particular would let anyone teleport any character once rule 20 makes location meaningful.
2. **HIGH — `settings.EQUIPMENT_SERVICE_URL` does not exist.** `crud.py:224` references it but `config.py` (L9-13) never defines it; Pydantic v1 `BaseSettings` forbids extra attrs, so `send_equipment_slots_request` raises `AttributeError` at call time unless an undocumented env var supplies it. `test_http_helpers.py:32-35` masks this by `object.__setattr__`-ing the attribute onto `settings` at import — the suite is green while the production path is broken. This is on the approval path.
3. **MEDIUM — Double-grant risk on approve.** HTTP calls (`main.py:299,317,329`) and RabbitMQ publishes (`L375,382,388`) carry the same inventory/skills/attributes payloads; both sets of consumers apply them.
4. **MEDIUM — `CharacterRequest.name` String(20) vs `Character.name` String(255).** Claims of long-named NPCs truncate or raise MySQL 1406 at `main.py:132`.
5. **LOW — Double slash in URL.** `crud.py:683` builds `{ATTRIBUTES_SERVICE_URL}/{id}/experience` while the setting already ends in `/`.
6. **LOW — Blocking I/O on the event loop.** `auth_http.py:30` uses blocking `requests.get` inside an async dependency (every authenticated request); `crud.py:954` uses blocking `httpx.post`. Related to the existing HIGH entry about `async def` handlers doing sync DB work.
7. **LOW — `auth_http` catches only `ConnectionError`** (L32); a `Timeout` or `SSLError` from user-service surfaces as a 500 instead of 503. Present in all 12 copies.
8. **LOW — photo-service oversize upload returns 500, not 413.** `utils.py:60-66` raises `ValueError`, caught by a blanket `except Exception`.
9. **Doc drift — `CLAUDE.md` §7** lists notification-service and battle-service as lacking Alembic; both have it. Also `main.py:187`'s approve docstring still references `SUBRACE_ATTRIBUTES` from the dead `presets.py`.

---

### Risks

**R1 — Avatar upload has no pre-character path (blocks rule 21). CRITICAL.**
`POST /photo/change_character_avatar_photo` (`photo-service/main.py:117-132`) hard-requires an existing owned character: `get_character_owner_id` (`crud.py:9-12`) returns `None` → **404**, and `owner_id != current_user.id` → **403**. At wizard time the character does not exist — approval creates it. The two-phase pattern used by the admin races UI is therefore unavailable.
*Mitigation / material for the Architect:* four **generic, non-entity-bound** upload endpoints already exist and return a permanent public S3 URL without writing to any table — `POST /photo/upload_ticket_attachment` (L696) and `POST /photo/upload_chat_image` (L103) need only `get_current_user_via_http`; `upload_archive_image` (L615) and the cosmetics uploads (L642, L669) need permissions. Any of these is a working precedent for "upload first, attach the URL to the request, copy to `characters.avatar` on approval". Caveats: there is **no temp bucket, no TTL, and no orphan reaper** — an abandoned wizard leaks a public S3 object permanently; `validate_image_mime` (`utils.py:25`) trusts the client `Content-Type` rather than sniffing magic bytes; the 15 MB cap (`utils.py:60-66`) raises `ValueError` which the blanket `except Exception` turns into a **500, not 413**; and nothing deletes a replaced character avatar.

**R2 — No starting locations exist yet (edge case in brief, and rule 20).**
`is_starting` does not exist, so immediately after the migration **zero** locations are flagged. Meanwhile `create_preliminary_character` currently leaves `current_location_id` NULL, and `move_and_post`'s NULL branch (any location, cost 0) is what silently absorbs that today. Setting a starting location closes that escape hatch, so a character approved with a bad/deleted location id could become genuinely stuck.
*Mitigation:* the Architect must define a fallback and an approval-time re-validation; content seeding of flagged locations must land before or with the release. Note the prod scale — 2260 locations across 322 districts — makes an unfiltered picker (rule 19) a non-starter, which is the point of the curated flag.

**R3 — Making `character_requests` columns required breaks 13 test files.**
`CharacterRequest` is constructed directly in 13 of the 37 test modules (`character-service_tests.py`, `test_add_rewards`, `test_admin_auth`, `test_admin_character_management`, `test_admin_update_level_xp`, `test_approval_flow`, `test_claim_request`, `test_endpoint_auth`, `test_exception_handling`, `test_gold_transactions`, `test_race_crud`, `test_short_info_extended`, `test_starter_kits`). Tests build schema from `Base.metadata.create_all()` on in-memory SQLite, so **new columns appear automatically** — but any column made `NOT NULL` without a server default, and any new validation in `create_character_request`, will fail these constructions. `test_approval_flow.py` (12 tests) asserts the exact HTTP-call sequence and commit/rollback behaviour of approve and will need updating for a locations-service call; `test_moderation_requests.py` (7 tests, incl. `test_response_contains_all_expected_fields`) pins the moderation response shape; `test_starter_kits.py` (15) and `test_claim_request.py` (19) are also in the blast radius.
Precise breakdown:
- **New model column that is `NOT NULL` without a `server_default`** breaks the direct `models.CharacterRequest(...)` constructions: `test_admin_character_management.py:44` (parent row for all 25 tests), `test_admin_update_level_xp.py:48` (all 6), `test_endpoint_auth.py:73`, `test_race_crud.py:242,423,567`, `test_short_info_extended.py:100` (all 14), `test_starter_kits.py:106` (~8 of 15).
- **New required Pydantic field** is nearly invisible to the suite: the only test posting a creation payload is `test_endpoint_auth.py:155`, and it asserts the loose `status_code not in (401, 403)` — a 422 would still pass. ⚠️ **There is no test asserting that `POST /characters/requests/` returns 200 and persists a row.** That gap should be closed by QA as part of this feature.
- **Reject gaining a reason:** if the body field is **required**, the ~3 reject tests in `test_exception_handling.py` get 422 instead of the expected 404/500 and break. Making it `Optional[str] = None` keeps them green.
- **Ordering matters:** `test_endpoint_auth.py:131` expects 403 on a `user_id` mismatch, so the ownership check must stay **before** any new domain validation, or it returns 400/404 and fails.
- `test_moderation_requests.py` mocks `crud.get_moderation_requests`, so changing that function's SELECT shape leaves those 7 tests **passing while no longer reflecting reality** — silent staleness rather than a red test.

*Mitigation:* add every new column as nullable with a server default and every new Pydantic field as `Optional[...] = None`; update `conftest.py:_seed_reference_data` in the same commit; treat the approve-flow tests as part of the backend task, not an afterthought. `test_claim_request.py:211 test_user_at_character_limit` is the right template for the new limit-on-create test.

**R4 — Approve is a 12-step non-atomic distributed transaction, and this feature adds a 13th step.**
Approval already fans out to **five** services (inventory, skills, character-attributes, equipment, user) plus a RabbitMQ publish. Statuses today: attributes = critical, user-service registration = critical, inventory and skills = graceful-degrade. Adding a locations-service call raises the failure surface, and the duplicated HTTP+AMQP writes (see findings) mean a partial failure can double-grant. `test_approval_flow.py` covers only the assign-failure and attributes-failure rollbacks.
*Mitigation:* the Architect must classify the new call (critical vs graceful) explicitly and decide whether the duplicate publishes are removed as part of this work.

**R5 — Local seed data is the wrong setting.** `docker/mysql/init/01-seed-data.sql` holds the abandoned "Ло-Ка/Халдея" setting with 7 races and 16 subraces; prod has Каркарис/Эйдонэя with 10 races and ~35 subraces, 5 countries, 26 regions, 322 districts, 2260 locations, 95 archive articles in 11 categories. `conftest.py:_seed_reference_data` also seeds the **old** 7 races.
*Mitigation:* all lore verification against a prod dump, per the brief. Note this also means test fixtures must not be treated as a reference for real subrace ids. The blocking dependency — VPS password to pull the dump — is still open in section 1.

**R6 — Cross-service ownership of the origin registry.** Rules 8-11 need country-shaped data that is wider than `Countries`, must not expose `Countries.description`, and must link to Archive articles and to subraces. `Countries` and `archive_articles` live in locations-service; `subraces` and `character_requests` live in character-service. Any layout crosses a boundary, and CLAUDE.md warns that the shared database offers no isolation.
*Mitigation:* explicit Architect decision on ownership plus the direction of the HTTP call; avoid a second service writing another's tables (a pattern photo-service already abuses via mirror models).

**R7 — N+1 on starter-kit rendering.** Resolving id-only kit contents through per-id public endpoints costs one request per item and per skill, on a page load. The existing admin workaround (fetch the whole catalogue) is not available to players because `/skills/admin/skills/` is permission-gated.
*Mitigation:* a public bulk-resolve endpoint, or embedding resolved names/icons in the starter-kit response, is likely required. Architect's call.

**R8 — Rule 23 has no absolute calendar to validate against.** As detailed above, the game clock is a `{year(from 1), segment, week}` counter with no year 1788 anywhere. Comparing a player's tenure against "the current in-game date" and against character age needs a defined mapping between real years, in-game years and the lore epoch — none exists.
*Mitigation:* the Architect must define the mapping, or restate rule 23 in the counter's own units.

**R9 — Draft autosave (rule 35) has no precedent and touches unsanitised free text.** No autosave/draft mechanism exists in the app. `localStorage` is the obvious carrier but the wizard collects long free-text fields that are later rendered in the passport in four places.
*Mitigation:* keep drafts client-side; ensure the passport renders user text as text (the existing modal uses `whitespace-pre-wrap`, not `dangerouslySetInnerHTML` — preserve that).

**R10 — `get_admin_user` vs `require_permission` inconsistency.** character-service is nearly migrated (46 `require_permission` vs 4 `get_admin_user` at L3147-3194); locations-service is not (49 vs 24, including the whole post-moderation block L2004-2044). Endpoints left on `get_admin_user` are reachable by **any moderator** regardless of granular permissions.
*Mitigation:* new admin endpoints added by this feature must use `require_permission`, and new permissions must be seeded by migration — not left to the admin-gets-everything shortcut, which is exactly how `gametime:*` and `moderation` ended up unseeded.

---

## 3. Architecture Decision (filled by Architect — in English)

### 3.0 Guiding Decisions (answers to the questions the analysis left open)

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| **D1** | Who owns the origin registry (R6)? | **New table `origin_countries` in locations-service.** character-service stores only an opaque `origin_id INT NULL` (no cross-service FK — same style as the existing `characters.current_location_id BIGINT`, which is a plain column, not an FK). | The registry is country-shaped, needs `emblem_url` / `map_image_url` and must link to `archive_articles` — both live in locations-service. No service writes another service's tables. |
| **D2** | Extend `Countries` or add a new table? | **New table.** `Countries` stays the map entity. `origin_countries.country_id` is a nullable soft link for the 5 playable countries (lets the admin reuse an existing emblem). | Rule 9 needs a *wider* list (Железный Пояс, Эльфийские Сады, Республика Белый Клин are not playable countries) and rule 4 forbids exposing `Countries.description`. |
| **D3** | Where does subrace↔origin affinity live (rule 11)? | **`subraces.typical_origin_ids JSON NULL`** in character-service — an array of `origin_countries.id`. No join table, no cross-boundary FK. | Tiny cardinality, read-mostly, editable from the existing `SubraceForm`. A join table would have to physically sit on one side of the ownership line anyway. |
| **D4** | Avatar before the character exists (R1, rule 21)? | **New unbound upload endpoint `POST /photo/upload_character_request_avatar`**, modelled on `upload_ticket_attachment` (auth-only, no DB write, returns a permanent S3 URL). The wizard attaches the URL to the request; approve copies the *string* into `characters.avatar`. | The two-phase admin pattern is unavailable (no character id yet). A dedicated endpoint rather than reuse of the ticket one gives its own S3 subdirectory `character_avatar_drafts/`, its own rate limit, and correct semantics. |
| **D5** | Avatar missing / S3 down at submit? | `avatar` becomes `Optional[str] = None`. At approve, `characters.avatar` (NOT NULL) falls back to `subraces.image`, then to `''`. An upload failure is shown to the player but never blocks submission. | Makes the avatar non-blocking without a schema change on `characters`. |
| **D6** | Orphaned S3 objects from abandoned wizards? | **Accepted debt, out of scope.** No temp bucket, no TTL, no reaper is introduced; a follow-up `docs/ISSUES.md` entry is filed instead. | A lifecycle/reaper is a self-contained infrastructure feature. An S3 lifecycle rule on the prefix cannot be used, because an approved avatar keeps the very same URL and would be deleted with the orphans. |
| **D7** | Starting-location fallback (R2, rule 20)? | Three-step chain at approve — §3.6. The character is **never** left stuck: step 3 leaves `current_location_id = NULL`, which is today's behaviour and is absorbed by the existing `move_and_post` NULL branch (any destination, cost 0). | Preserves the current safety net instead of closing it before the content exists. |
| **D8** | Classify the new locations-service call in approve (R4). | **Graceful-degrade, NOT critical.** A failure logs a warning, applies the fallback chain, and lets the approval succeed. | Approve already creates the character row and fans out to five services. A 13th *critical* step adds a new way to half-fail with no operator recovery path — approve is one-shot, so a hard failure strands the request in `pending` after side effects have landed. A NULL location is recoverable by a moderator; a half-approved request is not. |
| **D9** | Remove the duplicate HTTP+AMQP publishes in approve (R4 / ISSUES #3)? | **No — do not touch them in this feature.** | Verified: the consumers *are* running (`inventory-service/app/main.py:44`, `skills-service:57`, `character-attributes-service:40`) **and are idempotent** — `inventory-service/app/rabbitmq_consumer.py:35-38` skips when the character already has inventory. What remains is a narrow race window, not a systematic double-grant, so it is not a blocker for any rule here. Removing a publish path changes three services' delivery guarantees and belongs in its own change. It stays in `docs/ISSUES.md`. |
| **D10** | N+1 on starter kits (R7, rule 12)? | **Two new public bulk-resolve endpoints** — `GET /inventory/items/bulk?ids=` and `GET /skills/bulk?ids=` — consumed **by the frontend**, not by character-service. `GET /characters/starter-kits` stays byte-identical. | 3 requests total (kits + items + skills) instead of N. No new backend↔backend edge on a hot public path, no cache to invalidate, fully backward compatible. As a bonus the admin `StarterKitsPage` can drop its permission-gated `/skills/admin/skills/` call. |
| **D11** | Megalink number (rule 27)? | **Derived, not stored:** `СК-{character.id:06d}`. Computed inside the passport component. For an unapproved request the passport renders «будет присвоен при регистрации». | Unique and stable by construction; no column, no collision handling, no migration. |
| **D12** | 20-char name limit (ISSUES #4)? | **Column not widened.** A Pydantic `max_length=20` constraint with a Russian message is added to `CharacterRequestBase.name` instead. | Rule 32 only requires the player to get a clear message rather than a MySQL 1406 → 500. Widening `character_requests.name` to `String(255)` is a separate data-shape change and stays in ISSUES. |
| **D13** | Character-limit check on submit (rule 31)? | Reuse the `POST /requests/claim` shape (`main.py:102-105`): `SELECT COUNT(*) FROM users_character` **plus** a count of the caller's own `pending` `creation` requests. The cross-table count keeps `claim`'s graceful `except` (log + allow). | The local pending-request count is always reliable; the `users_character` count is not available under the SQLite test harness. Inheriting the graceful branch keeps 13 test modules green and matches the sibling endpoint. The weakness is pre-existing (ISSUES) and is not newly introduced here. |
| **D14** | Oversize upload → 500 (ISSUES #8)? | Fixed **only inside the new endpoint**: `ValueError` from `convert_to_webp` → **413** with a Russian message. `utils.py` is not changed. | The new endpoint is player-facing, so rule 32 makes a readable error a blocker *there*. The general fix across all photo-service uploads stays in ISSUES. |
| **D15** | How does the backend learn the current in-game year (rule 23)? | **Extend the existing public `GET /locations/game-time` response with the already-existing `computed: ComputedGameTime` block** (locations-service already computes it for the admin variant). character-service reads `computed.year`; nothing re-implements the calendar. | Avoids a third copy of `DAYS_PER_YEAR` / `YEAR_SEGMENTS` (they already exist in `locations-service/app/crud.py:2281` and `frontend/src/utils/gameTime.ts`). Additive field — the frontend's own client-side ticking computation is untouched. |
| **D16** | How is "class default" encoded on `starter_kits` (rules 12a-12c)? | **`origin_id INT NOT NULL DEFAULT 0`, where `0` means "class default"** — *not* a nullable column. Unique key on the pair `(class_id, origin_id)`. | ⚠️ **Deviation from the brief's "nullable `origin_id`", for a correctness reason: MySQL treats NULLs as distinct inside a UNIQUE index**, so `UNIQUE (class_id, origin_id)` with a nullable column would happily accept two competing default rows for the same class, and the resolution order would become non-deterministic. A `0` sentinel makes the constraint actually enforce one default per class. It is also strictly better for the migration: existing rows acquire `0` from the column default, so **every current kit silently becomes that class's default with no data rewrite at all**. Semantically `0` still reads as "no origin"; `origin_countries.id` is `AUTO_INCREMENT` and never yields 0. |
| **D17** | Does the passport store the granted kit, or re-resolve it? | **Freeze it — `characters.granted_kit JSON NULL`, written at approval from the very same `resolve_starter_kit` result the grant is made from. The passport reads the snapshot.** (Rule 12d. This reverses the earlier draft, which re-resolved; the user chose freezing.) | The passport is an **in-world record of what was issued at recruitment**, not a live view of a template. A record that silently rewrites itself when an admin edits a template is not a record, and a player would see gear in their passport that they were never given. One resolution feeds both the grant and the snapshot, so the two cannot diverge by construction. |
| **D18** | What does a character created *before* this feature show (rule 12d, backfill)? | **No backfill.** `granted_kit IS NULL` → the passport falls back to resolving `(id_class, origin_id)` live, exactly as the pre-12d design did. The API exposes `granted_kit_is_snapshot: bool` so the frontend can mark a reconstruction if it ever wants to. | Backfilling from today's class default would **fabricate** a record: it would assert "you were issued this" for characters whose kit at the time is genuinely unknown and may since have been edited. A NULL that falls back to a live resolve is honest — it is visibly a best-effort reconstruction rather than a false certainty. It also keeps the migration purely additive (R3), consistent with `registered_at`, which is likewise not backfilled. |
| **D19** | Does the snapshot freeze item names and icons too? | **No — it freezes the item and skill *ids*, quantities and currency.** Names, descriptions, icons and rarity are still resolved live through the bulk endpoints. | A renamed or re-illustrated item is still the same item; showing its current presentation is correct, not a rewrite. Freezing presentation would mean a passport slowly filling with stale art. What rule 12d protects is *which* items were issued, and that is exactly what the snapshot holds. |

---

### 3.1 API Contracts

Paths are as seen **through the API gateway** (each service's router already carries its prefix).

#### NEW — `GET /characters/classes` *(public)*
Replaces the mock `INITIAL_CLASSES`. Rule 12.
**Response 200:**
```json
[{ "id_class": 1, "name": "Воин", "description": "..." }]
```

#### NEW — `GET /characters/requests/my` *(auth)*
Rule 29. **Must be declared before any `/requests/{request_id:int}` route** — otherwise `my` is parsed as an int and the endpoint answers 422.
**Response 200:**
```json
[{
  "id": 12, "status": "rejected", "request_type": "creation",
  "created_at": "2026-09-06T10:00:00",
  "rejection_reason": "Возраст не соответствует подрасе",
  "name": "Аэлис", "id_race": 3, "id_subrace": 11, "id_class": 2,
  "race_name": "Эльфы", "subrace_name": "Лесные эльфы", "class_name": "Разбойник",
  "avatar": "https://s3.../x.webp", "origin_id": 7, "start_location_id": 1183,
  "biography": "...", "personality": "...", "appearance": "...", "background": "...",
  "sex": "female", "age": 120, "weight": "52", "height": "168",
  "skitaltsy_since_year": 1783, "skitaltsy_since_segment": 2,
  "character_id": null
}]
```

#### NEW — `PUT /characters/requests/{request_id}` *(auth + ownership)*
Rule 30 — edit and resubmit a rejected request.
**Request:** the same body as `POST /characters/requests/` minus `user_id`.
**Response 200:** the updated request (shape above), `status` back to `"pending"`, `rejection_reason` cleared.
**Errors:** `403` not the owner · `404` not found · `409` status is not `rejected` · `400` domain validation (§3.2).

#### CHANGED — `POST /characters/requests/` *(auth)*
Rules 31-34. **Check order is load-bearing** (`test_endpoint_auth.py:131` expects 403): ownership **first**, then domain validation.
**Request (new/changed fields marked):**
```json
{
  "name": "Аэлис", "id_race": 3, "id_subrace": 11, "id_class": 2,
  "appearance": "...", "biography": "...", "personality": "...", "background": "...",
  "sex": "female", "age": 120, "weight": "52", "height": "168",
  "user_id": 42,
  "avatar": "https://s3.../x.webp",
  "origin_id": 7,
  "start_location_id": 1183,
  "skitaltsy_since_year": 1783,
  "skitaltsy_since_segment": 2
}
```
`avatar` changes from **required `str`** to `Optional[str] = None`; `origin_id`, `start_location_id`, `skitaltsy_since_year`, `skitaltsy_since_segment` are all `Optional[...] = None` (R3).
**Response 200:** the created request, now also carrying `created_at`, `request_type`, `character_id`, `rejection_reason` and the four new fields (the current response model omits the first three).
**Errors:** `403` `user_id` mismatch · `422` schema · `400` domain validation · `500` DB.

#### CHANGED — `POST /characters/requests/{request_id}/reject` *(`characters:approve`)*
Rule 28.
**Request** — new body, **optional** so the three existing reject tests stay green (R3):
```json
{ "reason": "Возраст не соответствует подрасе" }
```
**Response 200:** `{ "message": "Заявка с ID 12 была отклонена." }`
**Side effect:** publish to `general_notifications` —
`{"target_type":"user","target_value":<user_id>,"message":"Ваша заявка на персонажа отклонена: <reason>","ws_type":"character_request_rejected","ws_data":{"request_id":12,"reason":"..."}}`. No notification-service change is needed.

#### CHANGED — `POST /characters/requests/{request_id}/approve` *(`characters:approve`)*
Rules 20, 22, 12a-12d. Four additions to the existing 12-step flow: start-location resolution (§3.6, graceful), `characters.registered_at = utcnow()`, `characters.origin_id` / `skitaltsy_since_*` copied from the request, and — **before anything is granted** — the starter kit read at `main.py:265` changes from a direct `filter(class_id == …)` query to `crud.resolve_starter_kit(db, request.id_class, request.origin_id or 0)`. Because that is the identical call the wizard used to preview the kit, **what the player was shown is exactly what is granted**. That single resolution result is then also written to `characters.granted_kit` (rule 12d, D17) — one resolution, used for the grant and for the snapshot, so the two cannot diverge. **The resolver must be called exactly once in this handler.** `characters.avatar` falls back to `subraces.image` when the request carries none (D5).
**Response 200 (additive):**
```json
{ "message": "Персонаж с ID 501 успешно создан и присвоен пользователю.",
  "current_location_id": 1183,
  "location_warning": null }
```
`location_warning` is a Russian string when the fallback chain had to degrade, otherwise `null`.

#### NEW — `GET /characters/{character_id}/public` *(public)*
The per-character read that does not exist today — `CharactersListPage.openDetail` currently fakes it with a `page_size:1` name search. Feeds the passport on the profile page.
**Response 200:**
```json
{
  "id": 501, "name": "Аэлис", "avatar": "https://...", "level": 3,
  "id_race": 3, "id_subrace": 11, "id_class": 2,
  "race_name": "Эльфы", "subrace_name": "Лесные эльфы", "class_name": "Разбойник",
  "subrace_image": "https://...", "subrace_distinctive_features": "...",
  "sex": "female", "age": 120, "weight": "52", "height": "168",
  "appearance": "...", "biography": "...", "personality": "...", "background": "...",
  "origin_id": 7, "registered_at": "2026-09-06T11:00:00",
  "skitaltsy_since_year": 1783, "skitaltsy_since_segment": 2,
  "current_location_id": 1183, "is_npc": false,
  "user_id": 42, "username": "player",
  "granted_kit": { "class_id": 2, "origin_id": 7, "resolved_from": "exact",
                   "items": [{"item_id": 5, "quantity": 1}], "skills": [{"skill_id": 4}],
                   "currency_amount": 100, "granted_at": "2026-09-06T11:00:00Z" },
  "granted_kit_is_snapshot": true
}
```
`granted_kit` is the **frozen** record (rule 12d). When the column is NULL — every character created before this feature (D18) — the endpoint resolves `(id_class, origin_id)` live, returns that instead, and sets `granted_kit_is_snapshot: false` so the client can tell a record from a reconstruction.
**Errors:** `404`. The path is `/{character_id}/public` rather than a bare `/{character_id}` to avoid colliding with the existing static segments `/list`, `/races`, `/metadata`, `/starter-kits`, `/classes`.

#### CHANGED — `GET /characters/list` *(public)*
Rule 26 — the compact passport card must render with **zero** per-row requests. Purely additive keys on each item: `origin_id`, `registered_at`, `skitaltsy_since_year`, `skitaltsy_since_segment`, `height`, `weight`, `current_location_id`, `subrace_image`. Existing keys unchanged.

#### CHANGED — `GET /characters/races` *(public)*
Additive on each subrace object: `distinctive_features`, `height_min`, `height_max`, `typical_origin_ids`. Rules 11, 14, 15, 17.

#### CHANGED — admin subrace endpoints *(`races:create` / `races:update`)*
`POST /characters/admin/subraces` and `PUT /characters/admin/subraces/{id}` accept the four new optional fields. Rules 11, 14, 15.

#### Starter kits keyed by (class × origin), granted kit frozen — rules 12a-12d

**The resolver is one function, used by everyone.** `crud.resolve_starter_kit(db, class_id, origin_id)` in character-service:
```
1. exact row (class_id, origin_id)            → return it,          resolved_from = "exact"
2. else the class default (class_id, 0)       → return it,          resolved_from = "class_default"
3. else                                        → empty kit,          resolved_from = "none"
```
Step 3 reproduces today's behaviour when a class has no kit row at all (`main.py:265` already falls through to empty lists).

**Who calls the resolver, and who does not (rule 12d, D17):**
| Caller | Uses | Why |
|---|---|---|
| Wizard «Путь» preview | **the resolver** | nothing has been granted yet — there is nothing to freeze |
| Approve | **the resolver, exactly once** | the single result is used both to grant the kit *and* to write `characters.granted_kit` — one resolution, so grant and snapshot cannot diverge |
| Passport | **the snapshot** `characters.granted_kit` | it is a record of what was issued, not a live view of a template |
| Passport, when `granted_kit IS NULL` (pre-feature characters) | the resolver, as a fallback | D18 — an honest best-effort reconstruction rather than a fabricated record |

No caller may re-implement the fallback chain locally. The property to preserve across #11, #31 and #33 is **preview == granted == snapshotted** at the moment of approval.

#### CHANGED — `GET /characters/starter-kits` *(public)* — **backward compatible**
Without query params it returns **only the class defaults** (`origin_id = 0`), which is exactly the set of rows that exists today. Each item gains an additive `origin_id` key. The existing admin `StarterKitsPage.tsx:77` (`kitsRes.data.find(k => k.class_id === cid)`) therefore keeps working with **no change at all**.
**New optional query param:** `?include_origins=true` returns every row, defaults and overrides alike.
```json
[{ "id": 1, "class_id": 1, "origin_id": 0, "items": [{"item_id": 5, "quantity": 1}],
   "skills": [{"skill_id": 4}], "currency_amount": 100 }]
```

#### NEW — `GET /characters/starter-kits/resolve?class_id=1&origin_id=7` *(public)*
What the wizard's «Путь» step calls. `origin_id` is optional; omitting it (or passing `0`) resolves the class default.
**Response 200:**
```json
{ "class_id": 1, "origin_id": 7, "resolved_from": "exact",
  "items": [{"item_id": 5, "quantity": 1}], "skills": [{"skill_id": 4}], "currency_amount": 100 }
```
`resolved_from` is `"exact" | "class_default" | "none"`. The wizard may use it for an unobtrusive hint, never to block anything.
**Errors:** `404` when `class_id` does not exist.

#### UNCHANGED — `PUT /characters/starter-kits/{class_id}` *(`characters:update`)*
Still writes the **class default** (`origin_id = 0`). Body and response are untouched, so the existing admin page and `test_starter_kits.py` keep working verbatim.

#### NEW — `PUT /characters/starter-kits/{class_id}/origins/{origin_id}` *(`characters:update`)*
Creates or updates the kit for one (class, origin) pair. Body is the existing `StarterKitUpdate`; response is the existing `StarterKitResponse` plus `origin_id`.
**Errors:** `404` unknown class · `400` `origin_id = 0` (use the endpoint above instead — one way to write a default, not two).
`origin_id` existence is **not** verified cross-service (same graceful policy as `character_requests.origin_id`); the admin UI only ever offers ids it just fetched from `GET /locations/origins`.

#### NEW — `DELETE /characters/starter-kits/{class_id}/origins/{origin_id}` *(`characters:update`)*
Removes an override so that the pair falls back to the class default again. Without this an admin could create an override but never undo one.
**Response 200:** `{ "message": "Стартовый набор для пары класс/происхождение удалён." }` · **`404`** when no override exists.

#### NEW — `GET /characters/starter-kits/coverage` *(`characters:update`)*
Serves the user's seeding checklist directly: which of the (class × origin) combinations are filled and which fall back.
**Response 200:**
```json
{ "classes": [{"id_class": 1, "name": "Воин", "has_default": true}],
  "overrides": [{"class_id": 1, "origin_id": 7}] }
```
The admin page renders this as a coverage matrix; origin names come from `GET /locations/origins`.

#### NEW — `GET /inventory/items/bulk?ids=1,2,3` *(public)*
D10. `ids` — comma-separated ints, **max 100**, deduplicated; unknown ids are silently omitted.
**Response 200:**
```json
[{ "id": 1, "name": "Ржавый меч", "description": "...", "image_url": "...", "rarity": "common", "type": "weapon" }]
```
**Errors:** `400` malformed, or more than 100 ids.

#### NEW — `GET /skills/bulk?ids=1,2,3` *(public)*
Same contract shape.
**Response 200:**
```json
[{ "id": 4, "name": "Рассечение", "description": "...", "icon_url": "...", "class_id": 1 }]
```

#### NEW — `POST /photo/upload_character_request_avatar` *(auth)*
D4. `multipart/form-data`, one field `file`.
**Response 200:** `{ "avatar_url": "https://s3.twcstorage.ru/.../character_avatar_drafts/....webp" }`
**Errors:** `400` disallowed MIME · `413` over 15 MB («Файл слишком большой. Максимальный размер — 15 МБ.») · `401` · `500`.

#### NEW — `GET /locations/starting-points` *(public)*
Rule 19. The curated list only — never the 2260-location catalogue.
**Response 200:**
```json
[{
  "id": 1183, "name": "Причал Цитадели", "image_url": "https://...",
  "starting_blurb": "Здесь новобранцы сходят на берег.",
  "district_name": "Нижний ярус", "region_name": "Цитадель",
  "country_name": "Мидденгерд", "sort_order": 10
}]
```

#### NEW — `GET /locations/starting-points/{location_id}` *(public)*
The validation probe used by character-service on submit and on approve.
**Response 200:** one item, shape as above. **`404`** when the location does not exist or `is_starting = 0`.

#### NEW — `GET /locations/origins` *(public)*
Rules 8-10. Rule 4 is satisfied structurally: this endpoint never reads `Countries.description`.
**Response 200:**
```json
[{
  "id": 7, "name": "Республика Белый Клин", "emblem_url": "https://...",
  "map_image_url": null, "summary": "Северная республика вольных наёмничьих рот.",
  "skitaltsy_attitude": "Почитают Скитальцев как героев.",
  "archive_slug": "belyi-klin", "country_id": null,
  "is_playable": false, "sort_order": 30
}]
```

#### NEW — admin origin CRUD *(locations-service)*
| Method | Path | Permission |
|---|---|---|
| `GET` | `/locations/admin/origins` | `origins:read` |
| `POST` | `/locations/admin/origins` | `origins:create` |
| `PUT` | `/locations/admin/origins/{id}` | `origins:update` |
| `DELETE` | `/locations/admin/origins/{id}` | `origins:delete` |

**POST/PUT request:**
```json
{ "name": "Эльфийские Сады", "emblem_url": null, "map_image_url": null,
  "summary": "...", "skitaltsy_attitude": "...", "archive_slug": "elfiyskie-sady",
  "country_id": null, "is_playable": false, "sort_order": 40 }
```
`DELETE` is a **soft delete** (`is_active = 0`); the public list filters on `is_active`. A hard delete would need a reference check against `characters.origin_id` / `character_requests.origin_id`, which live in another service — and no service may query across that boundary for integrity. Soft delete removes the need entirely.

#### CHANGED — location admin create/update *(`locations:create` / `locations:update`)*
Rule 18 — two additive optional fields on the existing location bodies: `is_starting: bool` (default `false`) and `starting_blurb: Optional[str]`. **No new permission** — the existing `locations:*` module already governs this entity.

#### CHANGED — `GET /locations/game-time` *(public)*
D15 / rule 23. Additive field only; existing keys unchanged, so `frontend/src/utils/gameTime.ts` and every current consumer keep working untouched.
**Response 200:**
```json
{
  "epoch": "2026-01-01T20:00:00", "offset_days": 349988,
  "server_time": "2026-09-06T09:33:49",
  "computed": { "year": 1787, "segment_name": "Зима", "segment_type": "season",
                "week": 11, "is_transition": false }
}
```
Implementation: `GameTimePublicResponse` gains `computed: ComputedGameTime` — the schema and the `compute_game_time` call already exist for `GameTimeAdminResponse` (`schemas.py:656-673`, `crud.py:2281`). No new calendar code.

#### UNCHANGED but consumed by the wizard
`GET /skills/subclasses?class_id=` (rule 13) · `GET /archive/articles/preview/{slug}` (lore tooltips) · `GET /characters/starter-kits`.

---

### 3.2 Input Validation (backend, character-service)

Applied in a shared validator used by both `POST /requests/` and `PUT /requests/{id}`.
**Ordering: ownership (403) → Pydantic (422) → domain (400).**

| Field | Rule | Message (Russian) |
|---|---|---|
| `name` | required, 1–20 chars after strip (D12) | «Имя обязательно и не длиннее 20 символов.» |
| `id_race` | row exists in `races` | «Указанная раса не найдена.» |
| `id_subrace` | row exists in `subraces` **and** `subrace.id_race == id_race` (rule 34) | «Подраса не принадлежит выбранной расе.» |
| `id_class` | row exists in `classes` | «Указанный класс не найден.» |
| `appearance` | required, non-blank (already `nullable=False`) | «Опишите внешность персонажа.» |
| `age` | `1 <= age <= 100000` when present | «Возраст указан некорректно.» |
| `sex` | one of `male` / `female` / `genderless` | «Некорректное значение пола.» |
| `origin_id` | when present: `> 0`. Existence is **not** checked cross-service on submit (graceful; the moderator sees the resolved name) | — |
| `start_location_id` | when present: probe `GET /locations/starting-points/{id}`; `404` → 400; transport failure → **accept** and log | «Выбранная точка не входит в список стартовых.» |
| `skitaltsy_since_year` | see §3.5 | see §3.5 |
| `skitaltsy_since_segment` | when present: `0 <= segment <= 7` (8 `YEAR_SEGMENTS`) | «Некорректный сезон.» |
| character limit | D13 — `users_character` count (graceful) + own `pending` `creation` requests | «Достигнут лимит персонажей (максимум 5).» |
| height vs subrace range | **not enforced server-side** — rule 15 is a soft warning only | client-side hint |
| origin vs subrace affinity | **not enforced** — rule 2, a rare choice is allowed | client-side «редкий выбор» badge |

Free-text fields (`biography`, `personality`, `appearance`, `background`) keep their current unlimited `Text` storage. **No HTML sanitisation is added**, because the passport and the existing detail modal render them as text (`whitespace-pre-wrap`, never `dangerouslySetInnerHTML`). R9's mitigation is a *rendering* invariant, and the Reviewer must confirm it holds in the new passport component.

---

### 3.3 Security Considerations

| Endpoint | Auth | Authorization | Rate limit | Input validation |
|---|---|---|---|---|
| `GET /characters/classes` | none | public | gateway default | — |
| `GET /characters/{id}/public` | none | public | gateway default | `character_id` int |
| `GET /characters/list` (changed) | none | public | gateway default | existing `page_size ≤ 100` |
| `GET /characters/requests/my` | **required** | owner-scoped by `current_user.id`; the caller can never name another user's id | gateway default | — |
| `PUT /characters/requests/{id}` | **required** | `request.user_id == current_user.id` → else **403**; `status == 'rejected'` → else 409 | **Nginx 10 r/m per IP** | full §3.2 set |
| `POST /characters/requests/` | **required** | `request.user_id == current_user.id` → else **403** (check stays first) | **Nginx 10 r/m per IP** | full §3.2 set + character limit |
| `POST /characters/requests/{id}/reject` | **required** | `require_permission("characters:approve")` (unchanged) | gateway default | `reason` optional, ≤1000 chars, stored as text, never interpolated into SQL |
| `POST /characters/requests/{id}/approve` | **required** | `require_permission("characters:approve")` (unchanged) | gateway default | — |
| `GET /characters/starter-kits`, `/starter-kits/resolve` | none | public | gateway default | `class_id` / `origin_id` ints; the resolver never trusts them for anything but a keyed lookup |
| `PUT /characters/starter-kits/{class_id}` (unchanged), `PUT`/`DELETE` `…/origins/{origin_id}` | **required** | existing `require_permission("characters:update")` — **no new permission**, the kits already belong to that module | gateway default | `origin_id > 0` on the pair routes; item/skill ids are ints stored as JSON, never executed |
| `GET /characters/starter-kits/coverage` | **required** | `require_permission("characters:update")` — it reveals the content-seeding state, so it is not public | gateway default | — |
| `GET /inventory/items/bulk`, `GET /skills/bulk` | none | public | gateway default | **`ids` ≤ 100, ints only** — the cap is the DoS control; parameterised `IN`, never string-built SQL |
| `POST /photo/upload_character_request_avatar` | **required** | any authenticated user (same tier as `upload_ticket_attachment`) | **Nginx 12 r/m per IP**, `client_max_body_size 16m` | MIME allowlist + 15 MB cap → **413**. ⚠️ `validate_image_mime` trusts the client `Content-Type` (pre-existing, ISSUES); the effective guard is that `convert_to_webp` re-encodes through Pillow, so a non-image payload fails there and never reaches S3 intact |
| `GET /locations/starting-points`, `/starting-points/{id}`, `/origins`, `/game-time` | none | public | gateway default | read-only, no user input beyond an int |
| `/locations/admin/origins*` | **required** | **`require_permission("origins:read|create|update|delete")`** — never `get_admin_user` (R10) | gateway default | `name` ≤255 required, `archive_slug` ≤255 matching `^[a-z0-9-]+$`, `sort_order` int |
| location create/update (changed) | **required** | existing `locations:create` / `locations:update` | gateway default | `starting_blurb` ≤2000 chars |

**Cross-cutting:**
- The new RBAC permissions (`origins:*`) are **seeded by user-service migration 0026** — not left to the admin-gets-everything shortcut (R10). The unseeded `gametime:*` / `moderation` gaps are neither inherited nor fixed here; they stay in ISSUES.
- No secret is added. `LOCATIONS_SERVICE_URL` is a plain internal URL, added to `docker-compose.yml` and `docker-compose.prod.yml` under `environment:`, with a safe in-code default `http://locations-service:8006`.
- Every new frontend API call must surface its error to the player in Russian (CLAUDE.md — Frontend Error Display). A silent `catch {}` is a review FAIL.
- The rejection reason is authored by a moderator and shown to the player as **text**, never as HTML.

---

### 3.4 DB Changes

#### character-service — migration `019_character_registration`
`version_table = alembic_version_character`, `down_revision = '018_add_mob_packs'`, **`revision = '019_char_registration'` (21 chars ≤ 32 — see the ISSUES entry «Alembic revision IDs ≤32 символов»)**.

```sql
-- character_requests: every column NULLable, no NOT NULL without default (R3)
ALTER TABLE character_requests
  ADD COLUMN origin_id INT NULL,
  ADD COLUMN start_location_id BIGINT NULL,
  ADD COLUMN skitaltsy_since_year INT NULL,
  ADD COLUMN skitaltsy_since_segment TINYINT NULL,
  ADD COLUMN rejection_reason TEXT NULL;

-- characters
ALTER TABLE characters
  ADD COLUMN origin_id INT NULL,
  ADD COLUMN registered_at TIMESTAMP NULL DEFAULT NULL,
  ADD COLUMN skitaltsy_since_year INT NULL,
  ADD COLUMN skitaltsy_since_segment TINYINT NULL;

-- subraces (rules 11, 14, 15, 17)
ALTER TABLE subraces
  ADD COLUMN distinctive_features TEXT NULL,
  ADD COLUMN height_min INT NULL,
  ADD COLUMN height_max INT NULL,
  ADD COLUMN typical_origin_ids JSON NULL;
```
**Downgrade:** symmetric `DROP COLUMN`s.
**Rollback safety:** every column is additive and nullable, so an older service image runs unchanged against the new schema — safe in both directions.
**No FK on `origin_id`** — `origin_countries` is owned by locations-service (D1). This mirrors the existing `characters.current_location_id BIGINT`, which is also a plain column.
⚠️ `characters.registered_at` stays NULL for NPCs and for every pre-existing row. The passport falls back to `character_requests.created_at` when it is NULL, and to «—» when there is no request either. **No backfill.**

#### character-service — migration `020_starter_kit_origin` (rules 12a-12d)
`down_revision = '019_char_registration'`, **`revision = '020_starter_kit_origin'` (24 chars)**. Kept separate from 019 so the (class × origin) change is one reviewable commit (CLAUDE.md §9).

```sql
-- 0. the frozen record of what a character was actually issued (rule 12d, D17)
--    Nullable, NOT backfilled (D18): NULL means "created before this feature",
--    and the passport falls back to a live resolve for those.
ALTER TABLE characters ADD COLUMN granted_kit JSON NULL;

-- 1. every existing row becomes its class's default, with no data rewrite
ALTER TABLE starter_kits ADD COLUMN origin_id INT NOT NULL DEFAULT 0;

-- 2. drop the single-column UNIQUE on class_id.
--    001_initial_baseline.py:124 declared it inline (`unique=True`), so the index name is
--    MySQL-assigned, NOT a name we chose. The migration MUST look it up rather than guess:
--      SELECT INDEX_NAME FROM information_schema.STATISTICS
--       WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'starter_kits'
--         AND NON_UNIQUE = 0 AND INDEX_NAME <> 'PRIMARY'
--       GROUP BY INDEX_NAME HAVING COUNT(*) = 1 AND MAX(COLUMN_NAME) = 'class_id';
--    …then op.drop_constraint(name, 'starter_kits', type_='unique'). No-op if absent.

-- 3. one default per class, one override per pair
ALTER TABLE starter_kits ADD UNIQUE KEY uq_starter_kits_class_origin (class_id, origin_id);
```
The FK `class_id → classes.id_class` stays. `origin_id` gets **no FK** — `origin_countries` belongs to locations-service (D1).

**`characters.granted_kit` shape** — the resolver's own output plus its provenance, so support and QA can see *why* a character got what it got:
```json
{ "class_id": 1, "origin_id": 7, "resolved_from": "exact",
  "items": [{"item_id": 5, "quantity": 1}], "skills": [{"skill_id": 4}],
  "currency_amount": 100, "granted_at": "2026-09-06T11:00:00Z" }
```
It stores ids only — names, icons and rarity are still resolved live (D19).

**Downgrade is lossy and must say so in its docstring:** it drops the pair unique, `DELETE FROM starter_kits WHERE origin_id <> 0` (all overrides are lost), drops `origin_id`, drops `characters.granted_kit` (every frozen record is lost) and restores a single-column unique on `class_id`. The forward direction is fully backward compatible; the reverse is not.
⚠️ Tests build the schema from `Base.metadata.create_all()` on SQLite, so `models.StarterKit` must carry `origin_id` and the `UniqueConstraint('class_id','origin_id')` while **losing `unique=True` on `class_id`** — otherwise `test_starter_kits.py` (15 tests) fails on the second row for a class.

#### locations-service — migration `033_starting_points_origins`
`version_table = alembic_version_locations`, `down_revision = '032_add_action_gates'`, **`revision = '033_start_pts_origins'` (21 chars)**.

```sql
ALTER TABLE Locations
  ADD COLUMN is_starting BOOLEAN NOT NULL DEFAULT 0,
  ADD COLUMN starting_blurb TEXT NULL;
CREATE INDEX ix_locations_is_starting ON Locations (is_starting);

CREATE TABLE origin_countries (
  id                 BIGINT       NOT NULL AUTO_INCREMENT,
  name               VARCHAR(255) NOT NULL,
  summary            TEXT         NULL,
  skitaltsy_attitude TEXT         NULL,
  emblem_url         VARCHAR(255) NULL,
  map_image_url      VARCHAR(255) NULL,
  archive_slug       VARCHAR(255) NULL,
  country_id         BIGINT       NULL,
  is_playable        BOOLEAN      NOT NULL DEFAULT 0,
  is_active          BOOLEAN      NOT NULL DEFAULT 1,
  sort_order         INT          NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uq_origin_countries_name (name),
  KEY ix_origin_countries_active_sort (is_active, sort_order),
  CONSTRAINT fk_origin_countries_country
    FOREIGN KEY (country_id) REFERENCES Countries (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```
`archive_slug` is a **soft** reference to `archive_articles.slug` — no FK, because articles are content and can be renamed. A dangling slug degrades to "no lore link", never to an error.
**Downgrade:** `DROP TABLE origin_countries`, drop the index and the two columns.
**Content seeding is NOT part of the migration.** Flagging starting locations (rules 18-19) and populating `origin_countries` (rule 9) are **content tasks done through the admin UI against the prod dump** — R5: the local seed carries the abandoned setting and must not be used.

#### user-service — migration `0026_add_origin_permissions`
`version_table = alembic_version_user`, `revision = '0026'`, `down_revision = '0025'`. Follows the idempotent SELECT-then-INSERT `ROLE_ACTIONS` idiom of `0025_add_gathering_permissions.py` — **not** the old hardcoded-id `op.bulk_insert` style.
```python
PERMISSIONS = [("origins", "read",   "Просмотр справочника происхождения"),
               ("origins", "create", "Создание записей справочника происхождения"),
               ("origins", "update", "Изменение записей справочника происхождения"),
               ("origins", "delete", "Удаление записей справочника происхождения")]
ROLE_ACTIONS = {3: ["read", "update"], 2: ["read"]}   # admin (4) gets all automatically
```

#### photo-service / skills-service / inventory-service / character-attributes-service
**No schema change → no migration.** photo-service's missing `alembic/versions/` directory is therefore not created here; a no-op `alembic upgrade head` with zero revisions is already what runs today.

#### Alembic summary
| Service | version_table | Current head | New revision id | Length |
|---|---|---|---|---|
| character-service | `alembic_version_character` | `018_add_mob_packs` | `019_char_registration` | 21 |
| character-service | `alembic_version_character` | `019_char_registration` | `020_starter_kit_origin` | 24 |
| locations-service | `alembic_version_locations` | `032_add_action_gates` | `033_start_pts_origins` | 21 |
| user-service | `alembic_version_user` | `0025_add_gathering_permissions` | `0026` | 4 |

---

### 3.5 Rule 23 — In-Game Tenure («в Скитальцах с»)

**The calendar is real and already usable.** Prod's `game_time_config` carries `offset_days = 349988` on top of `epoch = 2026-01-01T20:00:00`, so `compute_game_time` (`locations-service/app/crud.py:2281`, `DAYS_PER_YEAR = 196`, 8 segments, `DAYS_PER_WEEK = 3`) currently yields a four-digit in-game year in the lore era. The `year = elapsed_days // 196 + 1` counter starts at 1 only under the default zero-offset config used locally — on prod the offset is deliberately set so the counter lands in the lore era. Rule 23 is therefore directly implementable against the existing public endpoint; no new calendar concept, no epoch constant, no migration.

> **⚠️ HARD CONSTRAINT — the in-game year is never hardcoded.** Prod is currently an alpha test and its clock will be moved before launch. No literal year may appear in code, validation, seed data, a constant, a test fixture or the passport — every display and every check reads the computed year from `GET /locations/game-time` at runtime. Moving the clock must require **zero** code changes. The Reviewer must grep the diff for four-digit year literals and FAIL on any that is not a value entered by a player.
> The brief's line «Текущий игровой год — 1788» describes the intended state at launch, not the present one; nothing in this design depends on it.

**Storage.** `skitaltsy_since_year INT NULL` + `skitaltsy_since_segment TINYINT NULL` (segment index `0..7` into `YEAR_SEGMENTS`) on both `character_requests` and `characters`. The year is stored as the **in-game year as computed by `compute_game_time`** — the same number the player sees, with no offset applied anywhere.

**Where the year comes from (D15).** `GET /locations/game-time` gains the already-existing `computed` block. Consequences:
- **Frontend** keeps its own `src/utils/gameTime.ts` computation for live ticking (unchanged), and may use `computed` directly where a single snapshot is enough.
- **character-service** calls `GET /locations/game-time` and reads `computed.year` — it never re-implements the calendar. This is the second (and only other) use of the new `LOCATIONS_SERVICE_URL` setting, alongside the start-location probe, so both live in one small client module.
- The calendar constants stay in exactly two places (locations-service Python + frontend TS), as today. **No third copy.**

**Validation.**
| Bound | Where | Failure mode |
|---|---|---|
| `skitaltsy_since_year <= current_game_year` (rule 23, upper) | character-service, using `computed.year` | **Graceful** — if locations-service is unreachable the upper bound is skipped and only the age bound applies. An infrastructure failure never blocks a submission. |
| `current_game_year - skitaltsy_since_year <= age` (rule 23, lower — the character cannot have joined before being born) | character-service, same call | Same graceful behaviour; when the year is unavailable, this bound is skipped too, since it depends on the same number. |
| `0 <= skitaltsy_since_segment <= 7` | character-service, self-contained | Always enforced. |
Both bounds are also checked client-side for an immediate message; the backend check is authoritative. Messages: «Нельзя вступить в Скитальцы позже текущей игровой даты.» / «Указанный стаж больше возраста персонажа.»

**Rule 24 is structural:** neither column is read by any progression code. `characters.level` is set to its column default `1` at creation, exactly as today. The Reviewer should confirm that nothing outside the passport reads `skitaltsy_since_*`.

**Single source of truth.** `game_time_config` (editable from the existing game-time admin page) is the only place the current year is defined. Archive prose that names a year is content, not configuration, and the architecture does not read from or reconcile with it.

---

### 3.6 Start-Location Resolution (rules 18-20; R2, D7, D8)

**At submit** — soft: probe `GET /locations/starting-points/{id}`; a `404` becomes a `400` with a Russian message; a transport failure is accepted and logged.

**At approve** — the fallback chain; every step is **graceful**:
```
1. request.start_location_id is set AND GET /locations/starting-points/{id} → 200
      → characters.current_location_id = that id                            (normal path)
2. otherwise → GET /locations/starting-points → first by sort_order
      → characters.current_location_id = that id
      → location_warning depends on WHY step 1 did not apply:
        2a. the player DID choose a point and it was not confirmed (404, or the
            service could not answer)
              → location_warning = "Выбранная стартовая точка недоступна, назначена точка по умолчанию."
              → logger.warning
        2b. the player chose nothing (start_location_id IS NULL)
              → location_warning = null                                     (normal path)
              → logger.info
3. otherwise (nothing flagged, or locations-service unreachable)
      → characters.current_location_id = NULL                               (status quo)
      → location_warning = "Стартовая локация не назначена — обратитесь к администратору."
      → logger.warning
```
`location_warning` is a **degradation** channel, not an audit trail: it is non-null only when the
outcome is worse than what was asked for. Assigning the curated default to a request that never
named a point is the designed behaviour of rule 20, so step 2b reports nothing — telling a
moderator that a point is «недоступна» when none was ever chosen describes a failure that did not
happen (N14). Nothing is lost by the silence: the caller already has both `start_location_id` on
the request and `current_location_id` in the approve response, so an auto-assignment is fully
derivable, and the INFO log records it server-side.
Step 3 is safe because `move_and_post` already treats `current_location_id IS NULL` as "may move anywhere at cost 0" — the character is never stuck, which is precisely why this call is classified **graceful rather than critical** (D8). No `db.rollback()` is added on this path, and the single `db.commit()` at the end of approve is untouched.

---

### 3.7 Frontend Components

#### Design-system extension (rule 25 — a prerequisite for the passport)
`tailwind.config.js`, new tokens:
```js
colors.parchment = { light: '#faf1dc', DEFAULT: '#f5e6c8', dark: '#e3d0aa' }
colors.ink       = { DEFAULT: '#3b2f1c', muted: '#6b5a3e' }
fontFamily.lore  = ['MedievalSharp', 'Georgia', 'serif']
fontFamily.serif = ['Cormorant Garamond', 'Georgia', 'serif']
boxShadow.page   = 'inset 0 0 40px rgba(90,66,30,0.18), 4px 6px 10px rgba(0,0,0,0.35)'
```
Both font families are **already loaded** by `index.html:8` (MedievalSharp, Cormorant Garamond) — no new network resource.
`src/index.css` `@layer components`, new classes: `book-page`, `book-page-gutter`, `lore-heading`, `lore-divider`, `wax-seal`, `passport-field`.
`ArchiveLinkPreview.tsx:62,86` is refactored to consume `book-page` / `font-lore` instead of the hardcoded `bg-[#f5e6c8]` and the inline `fontFamily` — the app's only existing parchment surface must not stay a one-off.
`docs/DESIGN-SYSTEM.md` gains a section **16. Lore / Book Surfaces**.

#### The passport (rules 25-27) — one component, four call sites
```
src/components/CommonComponents/CharacterPassport/
├── CharacterPassport.tsx        // presentational only; props = PassportData + variant
├── types.ts                     // PassportData — every field optional except `name`
├── adapters.ts                  // fromWizardDraft / fromCharacterPublic /
│                                // fromCharacterListItem / fromModerationRequest
├── PassportStatBlock.tsx        // stats + derived values (rule 6)
├── PassportKitBlock.tsx         // resolved starter kit (rule 12)
└── PassportSeal.tsx             // Скитальцы seal + Megalink number (D11)
```
```ts
type PassportVariant = 'full' | 'compact';

interface PassportData {
  name: string;                       // the only required field
  characterId?: number | null;        // → Megalink «СК-000501», else «будет присвоен»
  avatarUrl?: string | null;
  level?: number | null;              // rendered as «УР»
  raceName?: string | null;
  subraceName?: string | null;
  subraceImage?: string | null;
  className?: string | null;
  origin?: { name: string; emblemUrl?: string | null; archiveSlug?: string | null } | null;
  originIsTypical?: boolean | null;   // false → «редкий выбор» badge (rule 11)
  stats?: Record<string, number> | null;
  derived?: DerivedStats | null;      // computed client-side from the documented formulas
  starterKit?: { items: ResolvedItem[]; skills: ResolvedSkill[]; currency: number } | null;
  // ↑ the kit ISSUED to this character. For an existing character this comes from the FROZEN
  //   characters.granted_kit snapshot (rule 12d) — never re-resolved, so a later admin edit
  //   cannot rewrite the record. In the wizard it is the live /starter-kits/resolve preview,
  //   because nothing has been granted yet. Item names/icons are always resolved live (D19).
  starterKitIsSnapshot?: boolean | null;
  // ↑ false for pre-feature characters whose kit had to be reconstructed (D18)
  startLocation?: { id: number; name: string } | null;
  registeredAt?: string | null;
  skitaltsySince?: { year: number; segment?: number | null } | null;
  sex?: string | null; age?: number | null; height?: string | null; weight?: string | null;
  appearance?: string | null; biography?: string | null;
  personality?: string | null; background?: string | null;
  status?: 'pending' | 'approved' | 'rejected' | null;   // moderator / my-requests only
  rejectionReason?: string | null;
}
```
Every field is optional, so all four sources fit without any of them fabricating data; the component renders «—» for what it lacks. `variant='compact'` (the list card) drops the long free-text blocks and the kit. **All free text renders through `whitespace-pre-wrap`, never `dangerouslySetInnerHTML`** (R9). No `React.FC` anywhere.

Call sites: wizard step 5 · `pages/CharactersPage/CharactersListPage.tsx` (compact card in the grid, full passport in the detail modal — replacing the ad-hoc `page_size:1` refetch with `GET /characters/{id}/public`) · the character profile page · `Admin/Request/Request.tsx`.

#### Wizard rewrite (`src/components/CreateCharacterPage/`)
```
CreateCharacterPage.tsx                 REWRITE — INITIAL_CLASSES deleted, step machine, gating
├── Prologue/Prologue.tsx               NEW — Coordinator intro
├── StepBlood/StepBlood.tsx             NEW — race + subrace in one panel (step 1)
│   ├── (reuses RacePage/RacePage.tsx and SubracePage/StatPreviewPanel.tsx)
│   └── StatExplainer.tsx               NEW — derived values, archetype, comparison (rules 5-7)
├── StepOrigin/StepOrigin.tsx           NEW — origin country, emblem, attitude, rare badge (rules 8-11)
├── StepPath/StepPath.tsx               NEW  ← replaces ClassPage.jsx
│   ├── ClassCard.tsx                   NEW  ← replaces ClassItem.jsx
│   ├── StarterKitPreview.tsx           NEW — kit for the ALREADY-CHOSEN origin via
│   │                                        /starter-kits/resolve + the bulk endpoints (rules 12, 12a-12c)
│   └── SubclassPreview.tsx             NEW — 7 subclasses from GET /skills/subclasses (rule 13)
├── StepPersona/StepPersona.tsx         NEW  ← replaces BiographyPage.jsx
│   ├── AvatarUploader.tsx              NEW — POST /photo/upload_character_request_avatar (rule 21)
│   ├── SubraceLookNote.tsx             NEW — portrait + distinctive features memo (rules 16-17)
│   └── TenureField.tsx                 NEW — «в Скитальцах с» year + segment (§3.5)
├── StepContract/StepContract.tsx       NEW  ← replaces SubmitPage.tsx
│   ├── StartingPointPicker.tsx         NEW — curated list (rules 19-20)
│   └── LawsOfTheOrder.tsx              NEW — Archive link block
├── useCharacterDraft.ts                NEW — localStorage autosave (rule 35)
├── useWizardValidation.ts              NEW — per-step gating (rules 32-33)
└── types.ts                            EXTENDED
```
**T3 migrations (.jsx → .tsx, mandatory):** `ClassPage.jsx`, `ClassPage/ClassItem/ClassItem.jsx`, `BiographyPage/BiographyPage.jsx` — all three carry logic and are being rewritten, so they are replaced by the `.tsx` files above.
**T1 — SCSS deleted, no new SCSS anywhere:** `ClassPage.module.scss`, `ClassItem.module.scss`, `BiographyPage.module.scss`.
**Dead code removed:** `RacePage/RaceCarousel/RaceCarousel.tsx` and `RaceCarousel/ArrowButton/ArrowButton.tsx` — no importers.
**T5 — responsive from 360px** across the whole wizard and the passport; in particular `SubmitPage.tsx`'s `px-[120px]` (L132) must not survive into `StepContract`.
**Lore tooltips:** reuse `CommonComponents/ArchiveLinkPreview` (it already caches and portals). `CommonComponents/Tooltip/Tooltip.jsx` is a 14-line stub that never renders `content` — **do not build on it**.

#### Other frontend work
```
src/components/pages/MyRequestsPage/MyRequestsPage.tsx   NEW — route "my-requests" (rules 29-30)
src/components/Admin/Request/Request.tsx                 CHANGED — passport + reject-reason modal (rule 28)
src/components/Admin/AdminRaces/SubraceForm.tsx          CHANGED — distinctive_features, height range, typical origins
src/components/AdminLocationsPage/EditForms/EditLocationForm/  CHANGED — is_starting + starting_blurb (rule 18)
src/components/Admin/AdminOrigins/AdminOriginsPage.tsx   NEW — origin registry CRUD
src/components/Admin/StarterKitsPage/StarterKitsPage.tsx CHANGED — second dimension (class × origin) + coverage matrix
src/components/App/App.tsx                               CHANGED — 2 routes: my-requests, admin/origins
src/redux/slices/racesSlice.ts                           CHANGED — the wizard finally uses fetchRaces instead of a raw axios.get
src/redux/slices/originsSlice.ts                         NEW
src/api/*                                                NEW/CHANGED — origins, startingPoints, classes, bulk items/skills, myRequests, avatar upload
```
`ProtectedRoute` is applied inline per route (the codebase's existing convention); `hasModuleAccess('origins')` gates the admin-hub tile.

---

### 3.8 Data Flow Diagram

**A. Wizard load (all public, parallel)**
```
Player → /createCharacter
  ├─ GET /characters/races           (character-service)   races + subraces + new fields
  ├─ GET /characters/classes         (character-service)   NEW
  ├─ GET /characters/starter-kits/resolve?class_id=&origin_id=   (character-service) NEW
  │    │   ← called on the «Путь» step, after the origin has been chosen on step 2
  │    ├─ GET /inventory/items/bulk?ids=…    (inventory-service) NEW
  │    └─ GET /skills/bulk?ids=…             (skills-service)    NEW
  ├─ GET /skills/subclasses?class_id=…       (skills-service)
  ├─ GET /locations/origins                  (locations-service) NEW
  ├─ GET /locations/starting-points          (locations-service) NEW
  ├─ GET /locations/game-time                (locations-service) now returns `computed`
  └─ (on hover) GET /archive/articles/preview/{slug}  (locations-service)
localStorage ← draft autosave on every change (rule 35)
```

**B. Avatar (rule 21)**
```
Player picks a file → POST /photo/upload_character_request_avatar   (multipart, auth)
photo-service → Pillow re-encode → S3 character_avatar_drafts/ → { avatar_url }
the frontend keeps avatar_url in the draft;
failure → Russian error, submission still allowed (D5)
```

**C. Submit**
```
Player → POST /characters/requests/            (character-service, auth)
   1. ownership: request.user_id == current_user.id       → else 403   [order is load-bearing]
   2. Pydantic                                            → else 422
   3. domain (§3.2)                                       → else 400
        ├─ GET /locations/starting-points/{id}   (locations-service, graceful)
        └─ GET /locations/game-time → computed.year  (locations-service, graceful)  [§3.5]
   4. limit: COUNT users_character (graceful) + own pending creation requests
   5. INSERT character_requests (status='pending')
```

**D. Approve (existing 12 steps + 3 additions, marked ★)**
```
Moderator → POST /characters/requests/{id}/approve   (characters:approve)
  ├─ ★ resolve_starter_kit(id_class, origin_id)  → exact pair, else class default, else empty
  │        called ONCE; the same function the wizard previewed with.
  │        The one result feeds BOTH the grant below AND ★ characters.granted_kit
  │        ⇒ preview == granted == snapshotted (rule 12d)
  ├─ INSERT characters  ★ granted_kit (frozen), ★ registered_at, origin_id, skitaltsy_since_*, avatar-fallback → subraces.image
  ├─ generate_attributes_for_subrace (subraces.stat_preset)
  ├─ HTTP → inventory-service              (graceful)
  ├─ HTTP → skills-service                 (graceful)
  ├─ HTTP → character-attributes-service   (CRITICAL — rollback)
  ├─ ★ HTTP → locations-service GET /locations/starting-points[/{id}]   (GRACEFUL — §3.6)
  │        → UPDATE characters.current_location_id  (or NULL + warning)
  ├─ UPDATE characters.id_attributes
  ├─ UPDATE character_requests.status='approved'
  ├─ HTTP → user-service assign            (CRITICAL — rollback)
  ├─ db.commit()   ← single commit, unchanged
  ├─ AMQP → general_notifications (approved)
  └─ AMQP → inventory / skills / attributes queues   (unchanged — D9)
```

**E. Reject (rule 28)**
```
Moderator → POST /characters/requests/{id}/reject { reason }
  → UPDATE character_requests SET status='rejected', rejection_reason=:reason
  → AMQP general_notifications {ws_type:"character_request_rejected", ws_data:{request_id, reason}}
       → notification-service consumer → notifications row → ws_manager.send_to_user
       → frontend useWebSocket switch(parsed.type)
```

**F. Resubmit (rule 30)**
```
Player → /my-requests → GET /characters/requests/my
       → prefill the wizard from the rejected request
       → PUT /characters/requests/{id}  → status back to 'pending', rejection_reason cleared
```

---

### 3.9 Questions for the User — **ALL ANSWERED**

| # | Question | Answer | Effect on the design |
|---|---|---|---|
| 1 | Content seeding — who fills the empty registries, and does the release wait? | **The user seeds the content themselves; the admin UI ships first.** They want a precise checklist of what to fill. | No change to the architecture. The empty-state handling stays as designed, and **every editing surface the seeding needs now has a task**: origins (#23), starting locations (#23), subrace features/height/typical origins (#23), and starter kits per (class × origin) (#32, which also renders the coverage matrix so the checklist is visible in the product). The checklist itself is in §3.10. |
| 2 | The exact origin list, and are Archive articles required? | **Exactly the 8 listed.** Articles will be written later where they are missing. | Confirms the design: `archive_slug` stays **nullable**, and a missing article degrades to "no lore link" rather than an error. |
| 3 | Does the passport show the issued kit or live inventory? | **The issued kit** — and, in a later pass, **frozen at approval** (rule 12d). | Per rules 12a-12c that is the kit for the character's own (class, origin) pair, never the bare class default; per rule 12d it is read from the `characters.granted_kit` snapshot rather than re-resolved, so an admin edit cannot rewrite an existing record (D17, D18, D19). |
| 4 | Passport layout on `/characters/list`. | **Compact card in the grid, full passport in the modal.** | Confirms the designed default. |
| 5 | Abandoned-wizard S3 orphans. | **Explicitly out of scope, to become its own task; PM files it in ISSUES.md.** | Removed from section 4 — task #13 no longer files it. |
| 6 | Soft delete for origins. | **Accepted.** | Confirms the designed default. |

**Follow-up requirements introduced by the answers — rules 12a-12d: starter kits become (class × origin), and the granted kit is frozen.** Fully designed in §3.1 (five endpoints), §3.4 (migration `020_starter_kit_origin`) and D16-D19. Both design calls that were raised for the user have since been settled:
- **D16 — `0` sentinel instead of a nullable `origin_id`.** Accepted by the user over the original instruction: MySQL treats NULLs as distinct inside a UNIQUE index, so a nullable column would let two competing defaults exist for one class.
- **D17 — the granted kit is frozen, not re-resolved.** Reversed at the user's direction (rule 12d): the passport is an in-world record of what was issued at recruitment, and a record that rewrites itself when a template is edited is not a record. Approve writes `characters.granted_kit` from the same single resolution it grants from; the passport reads the snapshot. D18 covers pre-feature characters (no backfill — NULL reconstructs rather than fabricates) and D19 the scope of the freeze (ids, not names and icons).

*Rule 23 / the in-game calendar is **not** an open question — see §3.5. It is fully specified and reads the year from `GET /locations/game-time` at runtime, so moving the clock before launch needs no code change.*

---

### 3.10 Content-Seeding Checklist (for the user, once the admin UI ships)

Nothing below is a code task; every item is filled through the admin pages built in tasks #23 and #32.

| Order | What | Where | Why it matters |
|---|---|---|---|
| 1 | **The 8 origin countries** — name, summary, «отношение к Скитальцам», emblem, optional `archive_slug`, `is_playable`, `sort_order` | `admin/origins` (#23) | Blocks wizard step 2 entirely, and is a prerequisite for items 2 and 4 below, which reference origin ids |
| 2 | **Typical origins per subrace** (~35 subraces) | `admin/races` → SubraceForm (#23) | Only drives the «редкий выбор» badge — a subrace with none simply shows no badge, so this can lag |
| 3 | **Distinctive features + height range per subrace** | `admin/races` → SubraceForm (#23) | Rule 17 already falls back to `description`, so this can lag too |
| 4 | **Starter kits** — one **default per class** first (3 rows, and these already exist today), then the (class × origin) overrides you care about | `admin/starter-kits` (#32) | The fallback means a missing override is invisible to the player; the coverage matrix shows which of the 24 combinations are still falling back |
| 5 | **Starting locations** — flag `is_starting` and write `starting_blurb` on a curated handful | `admin/locations` → EditLocationForm (#23) | ⚠️ **The one item with a real failure mode:** with zero flagged locations every approval lands in fallback step 3 and the character is created with a NULL location plus a warning (§3.6). Fill at least one before the first approval. |

---

## 4. Tasks (filled by Architect, updated by PM — in English)

**Build verification is part of every developer task, not a separate step.**
Backend Developer: `python -m py_compile` on every modified file. Frontend Developer: `npx tsc --noEmit` **and** `npm run build`, both green. QA Test: `pytest` green in the affected service. A task whose build check was not run is not DONE.

**Hard constraint for every task that touches the calendar (§3.5).** The in-game year is never hardcoded — not in code, validation, seed data, a constant, a test fixture or the passport. Every display and every check reads the computed year from `GET /locations/game-time` at runtime. Prod is an alpha test and its clock will be moved before launch; that move must require zero code changes.

**Parallelism map.** Wave 1 (no dependencies): #1, #3, #5, #9, #14. Wave 2: #2, #4, #6, #8, #10, #31. Wave 3: #7, #11, #15, #16. Wave 4: frontend features #17–#23, #32. Wave 5: QA #24–#28, #33. Wave 6: docs #29, review #30.

| # | Description | Agent | Status | Files | Depends On | Acceptance Criteria |
|---|-------------|-------|--------|-------|------------|---------------------|
| 1 | **locations-service migration 033.** Add `Locations.is_starting BOOLEAN NOT NULL DEFAULT 0` (+ index `ix_locations_is_starting`) and `Locations.starting_blurb TEXT NULL`; create table `origin_countries` per §3.4. `revision = '033_start_pts_origins'`, `down_revision = '032_add_action_gates'`. Update `app/models.py` (`Location`, new `OriginCountry`). Symmetric `downgrade()`. | Backend Developer | DONE | `services/locations-service/app/alembic/versions/033_starting_points_origins.py`, `app/models.py` | — | `alembic upgrade head` and `downgrade -1` both run clean against a MySQL 8 container; revision id ≤32 chars; `py_compile` OK |
| 2 | **locations-service endpoints.** Public `GET /locations/starting-points` and `GET /locations/starting-points/{location_id}` (404 when absent or `is_starting=0`), public `GET /locations/origins` (filters `is_active`), admin origin CRUD under `require_permission("origins:read\|create\|update\|delete")` with soft delete. Extend the existing location create/update schemas with `is_starting` / `starting_blurb`. Async SQLAlchemy + Pydantic v1, matching service style. | Backend Developer | DONE | `services/locations-service/app/main.py`, `app/schemas.py`, `app/crud.py` | #1 | All 7 endpoints respond as specified in §3.1; admin routes use `require_permission`, never `get_admin_user`; `py_compile` OK |
| 3 | **locations-service — expose `computed` on the public game-time endpoint.** Add `computed: ComputedGameTime` to `GameTimePublicResponse` and populate it from the existing `crud.compute_game_time`. Purely additive; existing keys and every current consumer stay untouched. No new calendar code. | Backend Developer | DONE | `services/locations-service/app/main.py` (L1669), `app/schemas.py` (L650) | — | `GET /locations/game-time` returns `epoch`, `offset_days`, `server_time` **and** `computed`; the frontend's existing `gameTime.ts` still works unchanged; `py_compile` OK |
| 4 | **user-service migration 0026 — RBAC.** Seed the `origins` module (`read`/`create`/`update`/`delete`) using the idempotent SELECT-then-INSERT `ROLE_ACTIONS` idiom of `0025_add_gathering_permissions.py`. `ROLE_ACTIONS = {3: ["read","update"], 2: ["read"]}`. Do **not** use the old `op.bulk_insert` style; do **not** grant admin explicitly. | Backend Developer | DONE | `services/user-service/alembic/versions/0026_add_origin_permissions.py` | — | Migration is re-runnable without duplicates; `test_rbac_permissions.py` still passes; `py_compile` OK |
| 5 | **character-service migration 019.** All ten columns of §3.4 across `character_requests`, `characters` and `subraces`. **Every column nullable, none NOT NULL without a server default** (R3). `revision = '019_char_registration'`, `down_revision = '018_add_mob_packs'`. Update `app/models.py`. No backfill. | Backend Developer | DONE | `services/character-service/app/alembic/versions/019_character_registration.py`, `app/models.py` | — | `upgrade`/`downgrade` clean against MySQL 8; the 13 test modules that construct `CharacterRequest(...)` directly still import and run; revision id ≤32; `py_compile` OK |
| 6 | **character-service — request creation validation.** Extend `CharacterRequestBase` with the four new optional fields, change `avatar` to `Optional[str] = None`, add `max_length=20` on `name`. Implement the shared domain validator of §3.2 (race/subrace/class existence, subrace↔race consistency, age, sex, segment range) and the character limit of D13. **The ownership 403 check must stay before all of it.** Add the `LOCATIONS_SERVICE_URL` setting and a small locations client (start-location probe + `computed.year` read), both graceful on transport failure. **Update the affected existing tests in this same task** (R3): `test_endpoint_auth.py`, `test_admin_character_management.py`, `test_admin_update_level_xp.py`, `test_race_crud.py`, `test_short_info_extended.py`, `test_starter_kits.py`, `conftest.py:_seed_reference_data`. | Backend Developer | DONE | `services/character-service/app/schemas.py`, `app/crud.py`, `app/main.py` (L62), `app/config.py`, `app/tests/conftest.py`, the six test modules above | #3, #5 | `POST /characters/requests/` returns 403 on a `user_id` mismatch (unchanged), 400 with the Russian messages of §3.2 on each domain violation, 200 on a valid payload; the whole existing character-service suite is green; `py_compile` OK |
| 7 | **character-service — new player endpoints.** **Дополнительно (решение пользователя, 2026-09-06):** добавить в эндпоинт reject проверку `status == 'pending'` -> иначе 409 с русским сообщением (правило 30a, устраняет запись в `docs/ISSUES.md`); и заменить 422 от валидатора `reason` на 400 с русским сообщением (правило 30b). Файл `main.py` к этому моменту свободен — #8 и #31 завершены. `GET /characters/classes` (public); `GET /characters/requests/my` (auth, owner-scoped, **declared before every `/requests/{request_id:int}` route**); `PUT /characters/requests/{request_id}` (auth + ownership, only when `status == 'rejected'`, resets to `pending` and clears `rejection_reason`, reuses the #6 validator); `GET /characters/{character_id}/public` — **including `granted_kit` and `granted_kit_is_snapshot`, falling back to a live resolve when the column is NULL** (rule 12d, D18); the additive keys on `GET /characters/list`. | Backend Developer | DONE | `services/character-service/app/main.py`, `app/schemas.py`, `app/crud.py` | #5, #6, #31 | Each endpoint matches §3.1 exactly; `/requests/my` is not swallowed by the int path param; a character with a snapshot returns it verbatim with `granted_kit_is_snapshot: true`, one without returns a live resolve with `false`; `/characters/list` keeps every existing key; `py_compile` OK |
| 8 | **character-service — reject with a reason.** Optional body `{reason}` (optional so the three existing reject tests stay green), persist to `rejection_reason` via `update_character_request_status`, publish to `general_notifications` with `ws_type="character_request_rejected"`. No notification-service change. | Backend Developer | DONE | `services/character-service/app/main.py` (L1073), `app/crud.py` (L86), `app/schemas.py`, `app/producer.py` | #5 | Reject without a body still returns 200; with a reason it persists and publishes; `test_exception_handling.py` reject tests still pass; `py_compile` OK |
| 9 | **inventory-service + skills-service — bulk resolve.** `GET /inventory/items/bulk?ids=` and `GET /skills/bulk?ids=`, both public, `ids` capped at 100, deduplicated, unknown ids omitted, parameterised `IN` query, 400 on malformed input. Each service keeps its own sync/async style. | Backend Developer | DONE | `services/inventory-service/app/main.py` + `schemas.py`, `services/skills-service/app/main.py` + `schemas.py` | — | Both endpoints return the shapes of §3.1; >100 ids → 400; no SQL is string-built; `py_compile` OK |
| 10 | **photo-service — pre-character avatar upload.** `POST /photo/upload_character_request_avatar`, `Depends(get_current_user_via_http)`, no DB write, S3 subdirectory `character_avatar_drafts/`, returns `{avatar_url}`. Modelled on `upload_ticket_attachment` (L696). Catch the `ValueError` from `convert_to_webp` and return **413** with a Russian message (D14, this endpoint only — `utils.py` is not changed). | Backend Developer | DONE | `services/photo-service/main.py` | — | A valid image returns a permanent S3 URL and writes no row; a 20 MB file returns 413 with a Russian message; a non-image MIME returns 400; `py_compile` OK |
| 11 | **character-service — approve rework.** Add the start-location resolution chain of §3.6 (graceful, three steps, never a rollback), set `characters.registered_at`, copy `origin_id` and `skitaltsy_since_*` from the request, and apply the `subraces.image` avatar fallback (D5). **Replace the direct starter-kit query at `main.py:265` with a single `crud.resolve_starter_kit(db, id_class, origin_id or 0)` call, and use that one result both to grant the kit and to write `characters.granted_kit`** (rules 12a-12d, D17). The resolver must be called exactly once in the handler. Extend the response with `current_location_id` and `location_warning`. **Do not touch the duplicate AMQP publishes** (D9). **Update `test_approval_flow.py` in this same task** — it pins the HTTP-call sequence and the commit/rollback behaviour. | Backend Developer | DONE | `services/character-service/app/main.py` (L180-405), `app/crud.py` (`create_preliminary_character` L51), `app/tests/test_approval_flow.py` | #5, #6, #31 | Approve succeeds when locations-service is down, leaving `current_location_id` NULL plus a warning; the normal path sets the chosen id; `registered_at` is populated; a request with an origin that has an override is granted the override, one without falls back to the class default; **`characters.granted_kit` is populated and its contents equal what was granted**; approve contains **no** starter-kit query of its own and calls the resolver exactly once; the 12 tests in `test_approval_flow.py` pass; `py_compile` OK |
| 12 | **DevSecOps — config and gateway.** Add `LOCATIONS_SERVICE_URL=http://locations-service:8006` to character-service in **both** `docker-compose.yml` and `docker-compose.prod.yml`. Add the rate limits of §3.3 to **both** `nginx.conf` and `nginx.prod.conf`: 10 r/m per IP on `POST /characters/requests/` and `PUT /characters/requests/{id}`, 12 r/m per IP plus `client_max_body_size 16m` on `POST /photo/upload_character_request_avatar`. | DevSecOps | DONE | `docker-compose.yml`, `docker-compose.prod.yml`, `docker/api-gateway/nginx.conf`, `docker/api-gateway/nginx.prod.conf` | #6, #10 | `docker compose config` validates; `nginx -t` passes in the gateway container; both dev and prod configs carry identical rules; no secret is added |
| 13 | **DevSecOps — file the follow-up issue.** Add to `docs/ISSUES.md` the not-fixed general oversize→500 path in photo-service `utils.py` (D14, LOW, noting that the new endpoint handles it locally). **The S3 orphan cleanup is NOT filed here** — the user placed it out of scope as its own task and PM files it. Do not re-file anything PM already recorded. | DevSecOps | DONE | `docs/ISSUES.md` | #10 | One new entry with service, file, priority; no duplicates |
| 14 | **Frontend — design-system extension.** Add the `parchment` / `ink` colors, `font-lore`, `font-serif` and `shadow-page` tokens to `tailwind.config.js`; add `book-page`, `book-page-gutter`, `lore-heading`, `lore-divider`, `wax-seal`, `passport-field` to `@layer components` in `index.css`; refactor `ArchiveLinkPreview.tsx:62,86` onto the new classes; document everything in a new section 16 of `docs/DESIGN-SYSTEM.md`. Fonts are already loaded by `index.html:8` — do not add a font link. | Frontend Developer | DONE | `tailwind.config.js`, `src/index.css`, `src/components/CommonComponents/ArchiveLinkPreview/ArchiveLinkPreview.tsx`, `docs/DESIGN-SYSTEM.md` | — | No hardcoded parchment hex remains in `ArchiveLinkPreview`; the hover preview looks unchanged; `tsc --noEmit` and `npm run build` green |
| 15 | **Frontend — API layer and types.** Typed clients and TS interfaces for every new/changed endpoint: classes, my-requests, request PUT, `characters/{id}/public`, items bulk, skills bulk, origins, starting points, game-time `computed`, avatar upload, **starter-kit resolve, the pair PUT/DELETE, and coverage**. New `originsSlice.ts`; wire the wizard onto the existing `fetchRaces` thunk instead of the raw `axios.get('/characters/races')`. **Every call surfaces its error to the user in Russian** — no silent catch. | Frontend Developer | DONE | `src/api/*`, `src/redux/slices/originsSlice.ts`, `src/redux/slices/racesSlice.ts`, `src/redux/store.ts` | #2, #3, #6, #7, #9, #10, #31 | TS interfaces match the Pydantic schemas field for field; every thunk has a rejected branch that reaches the UI; `tsc --noEmit` and `npm run build` green |
| 16 | **Frontend — `CharacterPassport` component.** Build the component tree and the four adapters of §3.7 against the `PassportData` interface. All free text via `whitespace-pre-wrap`, never `dangerouslySetInnerHTML`. Megalink derived as `СК-{id:06d}` (D11). **The kit block reads the frozen `granted_kit` snapshot for an existing character — never the resolver** (rule 12d, D17); the wizard adapter alone feeds it the live `/starter-kits/resolve` preview, because nothing is granted yet. Item names and icons are still resolved live from the frozen ids (D19). Tailwind only, no `React.FC`, responsive from 360px, `full` and `compact` variants. | Frontend Developer | DONE | `src/components/CommonComponents/CharacterPassport/**` | #14, #15 | Renders correctly from all four adapters, including one fed only `{name}`; two characters of the same class but different origins show different kits when an override exists; **editing a kit in the admin does not change an already-created character's passport**; no SCSS file is created; no `React.FC`; readable at 360px; `tsc --noEmit` and `npm run build` green |
| 17 | **Frontend — wizard steps 1-3.** Prologue, StepBlood (race + subrace in one panel, `StatExplainer` with derived values, archetype and comparison — rules 5-7), StepOrigin (emblem, attitude, Archive tooltip, «редкий выбор» badge from `typical_origin_ids` — rules 8-11), StepPath (`ClassCard`, `SubclassPreview` — rule 13, and `StarterKitPreview` which calls `/starter-kits/resolve` with the origin **already chosen on step 2** and then the bulk endpoints — rules 12, 12a-12c). **Delete `INITIAL_CLASSES`.** Migrate `ClassPage.jsx` and `ClassItem.jsx` to `.tsx` and delete their `.module.scss`. Delete the dead `RaceCarousel/` folder. | Frontend Developer | DONE | `src/components/CreateCharacterPage/{Prologue,StepBlood,StepOrigin,StepPath}/**`; delete `ClassPage/**` and `RacePage/RaceCarousel/**` | #15, #16, #31 | No mock data remains anywhere in the wizard; the starter kit renders real icons and names in exactly 3 requests and **changes when the player goes back and picks a different origin**; zero `.jsx` and zero `.scss` files remain under `ClassPage`; 360px clean; `tsc --noEmit` and `npm run build` green |
| 18 | **Frontend — wizard steps 4-5 and submission.** StepPersona (`AvatarUploader` against the new photo endpoint — rule 21; `SubraceLookNote` with the distinctive-features fallback to `description` — rules 16-17; `TenureField` with the year+segment input validated against `computed.year` and age — rule 23; the height hint against `height_min`/`height_max`, soft — rule 15) and StepContract (`StartingPointPicker` from the curated list — rules 19-20; `LawsOfTheOrder`; the passport; submit). Migrate `BiographyPage.jsx` to `.tsx` and delete its `.module.scss`; replace `SubmitPage.tsx` (drop `px-[120px]`). **Remove the `avatar: 'string'` literal.** | Frontend Developer | DONE | `src/components/CreateCharacterPage/{StepPersona,StepContract}/**`; delete `BiographyPage/**` and `SubmitPage/**` | #15, #16, #17 | The avatar really uploads and its URL reaches the request; an upload failure shows a Russian error and still allows submission; the tenure field rejects a future or pre-birth year with a Russian message; **no four-digit year literal appears anywhere in the diff** — the bounds come from `GET /locations/game-time`; no `avatar: 'string'` anywhere; 360px clean; `tsc --noEmit` and `npm run build` green |
| 19 | **Frontend — wizard shell, validation gating and draft autosave.** Rewrite `CreateCharacterPage.tsx` as the 5-step machine; `useWizardValidation` blocks Next on an incomplete step and blocks submit on missing required fields, with Russian messages (rules 32-33); `useCharacterDraft` autosaves to `localStorage` and restores after a reload (rule 35), and clears the draft on a successful submit. | Frontend Developer | DONE | `src/components/CreateCharacterPage/CreateCharacterPage.tsx`, `useWizardValidation.ts`, `useCharacterDraft.ts`, `types.ts`, `Pagination/**` | #17, #18 | Steps cannot be skipped; a reload mid-wizard restores every entered field; the draft is cleared after a successful submit; `tsc --noEmit` and `npm run build` green |
| 20 | **Frontend — «мои заявки» page.** New `MyRequestsPage` on route `my-requests` (inline `ProtectedRoute`, matching the existing convention), listing the caller's requests with status and rejection reason, plus an «Редактировать и отправить снова» action for rejected requests that prefills the wizard and calls `PUT /characters/requests/{id}` (rules 29-30). Add the route and a nav entry. | Frontend Developer | DONE | `src/components/pages/MyRequestsPage/**`, `src/components/App/App.tsx` | #15, #16, #19 | A rejected request shows its reason, can be edited and resubmitted without retyping anything, and returns to `pending`; errors reach the user in Russian; `tsc --noEmit` and `npm run build` green |
| 21 | **Frontend — moderator screen.** Render the full passport in `Admin/Request/Request.tsx` and add a reject-reason modal that posts `{reason}` (rules 26, 28). Show the «редкий выбор» origin badge so the moderator sees what rule 2 left to their judgement. | Frontend Developer | DONE | `src/components/Admin/Request/Request.tsx`, `src/components/Admin/RequestsPage/RequestsPage.tsx` | #8, #15, #16 | The moderator sees the same passport the player signed; rejecting requires or offers a reason and the player receives the notification; `tsc --noEmit` and `npm run build` green |
| 22 | **Frontend — characters list and profile.** Use the compact passport as the card in `CharactersListPage.tsx` and the full passport in the detail modal, replacing the `page_size:1` name-search refetch with `GET /characters/{id}/public` (rule 26). Use the same passport on the character profile page. | Frontend Developer | DONE | `src/components/pages/CharactersPage/CharactersListPage.tsx`, the character profile page component | #7, #15, #16 | The list renders with zero per-row requests; the modal fetches one character by id; free text still renders as text; 360px clean; `tsc --noEmit` and `npm run build` green |
| 23 | **Frontend — admin forms.** `SubraceForm` gains `distinctive_features`, `height_min`/`height_max` and a `typical_origin_ids` multi-select fed by `GET /locations/origins` (rules 11, 14, 15). `EditLocationForm` gains `is_starting` and `starting_blurb` (rule 18). New `AdminOriginsPage` with full CRUD, route `admin/origins`, gated by `hasModuleAccess('origins')` and an inline `ProtectedRoute`, plus an admin-hub tile. | Frontend Developer | DONE | `src/components/Admin/AdminRaces/SubraceForm.tsx`, `src/components/AdminLocationsPage/EditForms/EditLocationForm/**`, `src/components/Admin/AdminOrigins/**`, `src/components/App/App.tsx` | #2, #4, #15 | An admin can flag a starting location, write its blurb, create an origin and mark typical origins for a subrace; a user without `origins:*` sees neither the tile nor the route; `tsc --noEmit` and `npm run build` green |
| 24 | **QA — request creation and validation.** Tests for `POST /characters/requests/`: the 403 ownership check still fires first; each §3.2 domain rule returns 400 with its Russian message; the subrace↔race consistency check; the character limit (template: `test_claim_request.py:211`); and — closing the gap the analysis flagged — **a happy-path test asserting 200 and that the row is actually persisted**, which does not exist today. Mock the locations-service calls and cover the graceful branch when they fail. | QA Test | DONE | `services/character-service/app/tests/test_character_request_validation.py` (new) | #6 | ≥12 tests, all passing; both the reachable and the unreachable locations-service branches are covered |
| 25 | **QA — new player endpoints.** Tests for `GET /characters/classes`, `GET /characters/requests/my` (owner scoping — user A never sees user B's requests), `PUT /characters/requests/{id}` (403 for a non-owner, 409 when not rejected, success path), `GET /characters/{id}/public` (200 and 404), and the additive keys on `GET /characters/list`. Include the security case: an unauthenticated call to the auth-only endpoints returns 401. | QA Test | DONE | `services/character-service/app/tests/test_my_requests.py`, `test_public_character.py` (new) | #7 | ≥14 tests, all passing; owner scoping is proven, not assumed |
| 26 | **QA — approve and reject.** Tests for the §3.6 fallback chain (chosen id valid → used; invalid → default; nothing available → NULL + warning; locations-service down → NULL + warning, approval still succeeds), `registered_at` population, the `subraces.image` avatar fallback, and reject with and without a reason including the AMQP publish. | QA Test | DONE | `services/character-service/app/tests/test_start_location_assignment.py`, `test_reject_reason.py` (new) | #8, #11 | ≥12 tests, all passing; the graceful classification of D8 is proven by a test where locations-service raises and the approval still returns 200 |
| 27 | **QA — locations-service.** Tests for `GET /locations/starting-points` (only flagged locations), `/starting-points/{id}` (200 / 404 on an unflagged location), `GET /locations/origins` (soft-deleted rows are excluded, and `Countries.description` never appears in the payload — rule 4), the admin origin CRUD RBAC (a user lacking `origins:create` gets 403), and `GET /locations/game-time` still returning its original keys plus `computed`. | QA Test | DONE | `services/locations-service/app/tests/test_starting_points.py`, `test_origins.py` (new) | #1, #2, #3 | ≥12 tests, all passing; the RBAC negative case is explicit |
| 28 | **QA — bulk endpoints and avatar upload.** Tests for `GET /inventory/items/bulk` and `GET /skills/bulk` (happy path, unknown ids omitted, >100 ids → 400, malformed → 400, a SQL-injection string in `ids` → 400 and not a query), and for `POST /photo/upload_character_request_avatar` (401 unauthenticated, 400 on a bad MIME, 413 on oversize, 200 returns a URL and writes no row — S3 mocked). | QA Test | DONE | `services/inventory-service/app/tests/test_items_bulk.py`, `services/skills-service/app/tests/test_skills_bulk.py`, `services/photo-service/tests/test_request_avatar_upload.py` (new) | #9, #10 | ≥10 tests, all passing; the injection case is present |
| 29 | **Docs.** Update `docs/services/character-service.md` (new columns, new endpoints, the changed approve flow, the new locations-service dependency, the (class × origin) starter-kit model with its fallback rule, and the frozen `granted_kit` snapshot with its NULL-means-reconstruct semantics) and `docs/services/locations-service.md` (starting points, `origin_countries`, the admin origin endpoints, the `computed` field). Correct the CLAUDE.md §7 drift the analysis found — notification-service and battle-service **do** have Alembic. | Backend Developer | DONE | `docs/services/character-service.md`, `docs/services/locations-service.md`, `CLAUDE.md` | #2, #7, #11, #31 | Both service docs list every new endpoint and column; the CLAUDE.md §7 Alembic list is accurate |
| 31 | **character-service — starter kits by (class × origin).** Migration `020_starter_kit_origin` per §3.4: add `characters.granted_kit JSON NULL` (**nullable, no backfill** — D18), add `starter_kits.origin_id INT NOT NULL DEFAULT 0`, drop the inline single-column UNIQUE on `class_id` **by introspecting `information_schema.STATISTICS`** (001 auto-named it), add `UNIQUE (class_id, origin_id)`; lossy downgrade documented in the docstring. Update `models.StarterKit` (drop `unique=True`, add the `UniqueConstraint`) and `models.Character` (`granted_kit`). Add the shared `crud.resolve_starter_kit(db, class_id, origin_id)` with the exact→default→empty chain. Add `GET /starter-kits/resolve` (public), `PUT`/`DELETE /starter-kits/{class_id}/origins/{origin_id}` and `GET /starter-kits/coverage` (all three admin routes on the existing `characters:update`), and the `?include_origins=` param. **`GET /starter-kits` without params and `PUT /starter-kits/{class_id}` must keep their current behaviour byte for byte.** Update `test_starter_kits.py` in this same task. | Backend Developer | DONE | `services/character-service/app/alembic/versions/020_starter_kit_origin.py`, `app/models.py`, `app/crud.py`, `app/main.py` (L1124-1155), `app/schemas.py`, `app/tests/test_starter_kits.py` | #5 | `upgrade` turns every existing row into a class default with no data loss; two rows for one class with different origins are accepted, two defaults for one class are rejected by the DB; the resolver returns exact → class default → empty; the unchanged endpoints return what they returned before; the existing 15 tests in `test_starter_kits.py` pass; revision id ≤32; `py_compile` OK |
| 32 | **Frontend — starter-kit admin, second dimension.** **Extend the existing `StarterKitsPage`, do not create a new page** — it already loads the classes and the item/skill catalogues, and a second page would duplicate the whole editor. Add an origin selector per class («По умолчанию для класса» plus the origins from `GET /locations/origins`), wire it to the pair `PUT`/`DELETE`, and render a **coverage matrix** from `GET /starter-kits/coverage` showing which (class × origin) combinations are filled and which fall back — this is the user's seeding checklist made visible (§3.10). Deleting an override must state in Russian that the pair will fall back to the class default. | Frontend Developer | DONE | `src/components/Admin/StarterKitsPage/StarterKitsPage.tsx` | #15, #23, #31 | An admin can give a Шинзо warrior different gear from a Мидденгерд warrior and see at a glance which combinations are still on the default; deleting an override restores the fallback; existing default-editing behaviour is unchanged; Tailwind only, no `React.FC`, 360px clean; `tsc --noEmit` and `npm run build` green |
| 33 | **QA — starter-kit resolution.** Tests for `resolve_starter_kit` (exact pair, fallback to the class default, empty when the class has no kit at all), `GET /starter-kits/resolve` including `resolved_from`, the pair `PUT`/`DELETE` (including `origin_id=0` → 400 and RBAC 403 without `characters:update`), `GET /starter-kits/coverage`, and **two backward-compatibility tests**: `GET /starter-kits` with no params returns only defaults, and `PUT /starter-kits/{class_id}` still writes the default. **Plus the rule-12d freeze tests:** (a) approval writes `characters.granted_kit`, and its contents equal both what `/resolve` returned for that pair *and* what was actually sent to inventory/skills — **preview == granted == snapshotted**; (b) editing the kit through the admin endpoint afterwards leaves the existing character's `granted_kit` byte-identical, while a newly approved character gets the new contents; (c) `GET /characters/{id}/public` on a character with `granted_kit IS NULL` falls back to a live resolve and reports `granted_kit_is_snapshot: false` (D18). | QA Test | DONE | `services/character-service/app/tests/test_starter_kit_origins.py`, `test_granted_kit_snapshot.py` (new) | #7, #11, #31 | ≥18 tests, all passing; preview == granted == snapshotted is asserted, not assumed; the retroactivity test proves a later admin edit cannot rewrite an existing passport; the NULL-fallback path is covered; the RBAC negative case is explicit |
| 34 | **Bulk id cap — count before deduplication.** In `_parse_bulk_ids` (one copy per service), check the raw token count against `MAX_BULK_IDS` **before** deduplicating, so a long repeated-id string is rejected rather than parsed in full (N12). Two-line change per service; keep the existing 400 + Russian message. Update QA's `test_the_cap_counts_unique_ids` in both services, which currently pins the old behaviour. | Backend Developer | DONE | `services/inventory-service/app/main.py`, `services/skills-service/app/main.py`, their `tests/test_items_bulk.py` / `tests/test_skills_bulk.py` | #9, #28 | 101 unique ids → 400 (unchanged); 101 raw tokens that dedupe to 2 → 400; 100 unique ids → 200; both suites green at or above 465 / 209 |
| 35 | **Fix the misleading start-location warning (N14).** Split §3.6 step 2 into two messages: when the player chose a point that is no longer valid, keep the current «Выбранная стартовая точка недоступна…»; when the player chose nothing at all and the default was assigned, use a neutral message (or none). Update the §3.6 text and any QA assertion that pins the old string. | Backend Developer | DONE | `services/character-service/app/main.py`, `app/tests/test_approval_flow.py`, feature §3.6 | #11, #26 | A request with `start_location_id = NULL` no longer reports a point as «недоступна»; an invalid chosen id still does; character-service suite green |
| 36 | **Expose the new subrace fields on the races endpoint (N16).** Add `distinctive_features`, `height_min`, `height_max`, `typical_origin_ids` to `schemas.SubraceWithPreset`, `SubraceCreate`, `SubraceUpdate`, `SubraceResponse` (all optional, additive) and populate them in the `/characters/races` handler and the admin subrace CRUD. Columns already exist from migration 019. | Backend Developer | DONE | `services/character-service/app/schemas.py`, `app/main.py`, `app/crud.py` | #5 | `GET /characters/races` returns the four fields on every subrace; admin create/update persists them; existing keys unchanged; character-service suite green at 593+ |
| 37 | **Close the two data gaps the passport exposed (N25, N26).** (a) `crud.get_moderation_requests` must select `origin_id`, `start_location_id`, `skitaltsy_since_year`, `skitaltsy_since_segment`, `rejection_reason` and return them in the response dict — additive, existing keys untouched (`test_moderation_requests.py::test_response_contains_all_expected_fields` pins the shape, extend it). (b) `GET /characters/{character_id}/public` must carry the character's attributes so the passport stat block can render (rule 27) — fetch from character-attributes-service, graceful: a failure returns the passport without stats, never a 500. | Backend Developer | DONE | `services/character-service/app/crud.py`, `app/main.py`, `app/schemas.py`, `app/tests/test_moderation_requests.py`, `app/tests/test_public_character.py` | #7, #11 | Moderation rows carry the five keys; `/public` carries stats and still returns 200 when character-attributes-service is down; character-service suite green at 786+ |
| 38 | **Wire the passport stat block to the new `stats` key (N31).** `GET /characters/{id}/public` now carries `stats`; pass it into `PassportExtras.stats` at the detail-modal call site in `CharactersListPage` (and any other full-passport call site that has a `CharacterPublic`), so rule 27's stat block actually renders. Add `stats` to the `CharacterPublic` TS interface. `stats: null` must degrade to no stat block, never a crash. Compact cards stay without stats by design. | Frontend Developer | DONE | `src/api/charactersPublic.ts`, `src/components/pages/CharactersPage/CharactersListPage.tsx` | #22, #37 | Opening a character's passport shows the stat block with derived values; a character whose attributes service is down still opens, without the block; `tsc --noEmit` and `vite build` clean |
| 39 | **Post-review polish.** Passport `full` restructured into three bands (centred identity header with portrait/seal/Megalink → two-column ledger «Информация о персонаже» + stats/kit → full-width chronicle); `book-page-gutter` no longer applied; single-column fallback when there are no stats. Plus review findings: photo-service generic `except` no longer leaks `str(e)`; a game-time fetch failure now surfaces instead of «часы ещё отвечают» forever; stale `racesSlice` comment removed. | Frontend Developer | DONE | `CharacterPassport.tsx`, `TenureField.tsx`, `gameTimeSlice.ts`, `racesSlice.ts`, `CreateCharacterPage.tsx`, `RequestEditor.tsx`, `photo-service/main.py`, `docs/DESIGN-SYSTEM.md` | #16, #30 | tsc 0 errors; vite build passes; photo-service 193 passed; no empty column with stats present or absent |
| 40 | **Stub the missing subrace skill.** skills-service migration `009_subrace_skill` idempotently seeds skill id 7 «Выживание» (universal, no limitations) — the id `SUBRACE_SKILL_ID` points at, absent from prod data. Temporary until the racial-skills feature. | Backend Developer | DONE | `services/skills-service/app/alembic/versions/009_seed_subrace_placeholder_skill.py` | — | Migration idempotent, upgrade/downgrade verified on the live local DB; skills-service 210 passed; `GET /skills/bulk?ids=7` returns the skill |
| 30 | **Review.** Full checklist. Re-run `py_compile` across every touched service, `npx tsc --noEmit`, `npm run build`, and `pytest` in character-service, locations-service, inventory-service, skills-service and photo-service. **Live verification is mandatory:** walk the whole wizard in the browser and confirm zero console errors, a real avatar upload, a real starter kit, a submitted request, a moderator reject with a reason and the resulting player notification, an approve, and the resulting passport in `/characters/list`. **Verify the kit end to end: create an override for one (class, origin) pair, confirm the wizard previews it, that approval grants exactly that, and that a different origin of the same class still falls back to the class default. Then edit that kit in the admin and confirm the already-created character's passport is unchanged (rule 12d) while a freshly approved one shows the new contents.** Verify the mandatory rules of CLAUDE.md §10: Tailwind only (no new SCSS), `.tsx` only (no new `.jsx`), design-system classes used, 360px responsive, no `React.FC`, `require_permission` on every new admin endpoint, all user-facing strings Russian, every frontend error visible. **Grep the whole diff for four-digit year literals and FAIL on any that is not a value entered by a player** (§3.5 hard constraint). | Reviewer | DONE | all | #1–#29, #31–#33 | Every automated check green **and** live verification recorded in section 5; any FAIL is routed back to the responsible agent (max 3 iterations) |

Task statuses: `TODO` → `IN_PROGRESS` → `DONE` / `FIX_REQUIRED`

### Notes for PM

- **Task #12 (DevSecOps) blocks nothing but must land before the release** — without `LOCATIONS_SERVICE_URL` in compose, task #6's client falls back to its in-code default, which happens to be correct in dev but leaves prod undocumented.
- **Content seeding is not a task here** — the user does it themselves, after the admin UI ships. The checklist is §3.10, and every surface it needs has a task (#23 for origins / subraces / starting locations, #32 for starter kits). The one item with a real failure mode is the starting locations: with none flagged, every approval falls to §3.6 step 3 and creates a character with a NULL location plus a warning.
- **All six questions in §3.9 are now answered.** Five confirmed the designed defaults. The sixth (content seeding) added rules 12a-12c, which produced tasks #31, #32, #33 and amended #11, #13, #15, #16, #17, #29, #30.
- **#31 is on the critical path** — #7, #11, #15, #16, #17, #32 and #33 all depend on it. Schedule it in wave 2 alongside #6.
- **Section 4 is complete and there are no open questions left.** Both earlier design calls were settled by the user: D16's `0` sentinel stands, and D17 was reversed to a frozen `granted_kit` snapshot per rule 12d. The only judgement calls left inside the kit work are D18 (no backfill — a NULL reconstructs rather than fabricates) and D19 (the snapshot freezes ids, not names and icons); both are decided and recorded, not open.

---

---

### Implementation Notes for Downstream Tasks (recorded by PM as work lands)

Facts discovered during implementation that contradict or extend §3.1. **Downstream tasks must follow these, not the original contract text.**

| # | Note | Affects |
|---|---|---|
| N1 | **`GET /skills/bulk` returns `class_limitations` (a comma-separated string), NOT `class_id`.** The `skills` table has no class FK — scoping is done via the `class_limitations` / `subclass_limitations` strings. §3.1 named a field that does not exist. **The frontend must not read `skill.class_id`.** | #15, #16, #17, #32 |
| N2 | `GET /inventory/items/bulk` keeps the §3.1 response key names (`image_url`, `rarity`, `type`); the handler maps them from the model's actual columns (`image`, `item_rarity`, `item_type`). The frontend contract is unchanged — this note exists only so nobody "fixes" the mapping. | #15, #16, #32 |
| N3 | `POST /photo/upload_character_request_avatar` distinguishes oversize (**413**) from invalid image content (**400**) by matching on the exception message, because `convert_to_webp` raises a bare `ValueError` for both. Fragile by construction; the clean fix is a typed exception in `photo-service/utils.py`, which was out of scope. **Reviewer should decide** whether to accept or escalate. | #28, #30 |
| N4 | `origins:*` permissions do not exist in the DB until migration `0026` (task #4) is applied. Until then the admin origin routes return 403 even for an admin. Both have landed, but a running local stack needs the migration applied before the admin CRUD can be verified live. | #23, #27, #30 |
| N5 | `GET /locations/admin/origins` returns `OriginCountryAdminRead` (public fields + `is_active`) and includes soft-deleted rows by default (`include_inactive`, default `true`) — otherwise a hidden origin could never be found and restored. Restore is `PUT` with `is_active: true`; there is no dedicated restore endpoint. §3.1 did not specify this response. | #23, #27 |
| N6 | `is_starting` / `starting_blurb` are accepted in location create/update **request** bodies and returned by `GET /locations/{id}/details`, but deliberately **not** added to the location response schemas — adding them broke 8 tests that mock the location object, and returning a hardcoded `false`/`null` would misinform. The admin form must read current values from `/details`. | #23, #27 |
| N7 | `crud.update_character_request_status` accepts `rejection_reason` with an `_UNSET` sentinel: omitted = column untouched, string = written, explicit `None` = cleared. Task #7's edit-and-resubmit flow should pass explicit `None` to clear the reason; no signature change needed. | #7 |
| N9 | **§3.4's DDL order for migration 020 is wrong and would fail on prod MySQL.** Dropping the old single-column unique on `starter_kits.class_id` first raises `(1553, "Cannot drop index 'class_id': needed in a foreign key constraint")` — the FK `class_id → classes.id_class` requires an index on the column. The implemented migration creates the pair unique `(class_id, origin_id)` FIRST (class_id is leftmost, so it takes over serving the FK), then drops the old one; `downgrade()` mirrors it. **Not a deviation to flag in review — the spec text is what is wrong.** | #29, #30 |
| N10 | `resolve_starter_kit(db, class_id, origin_id=None)` returns a plain dict `{class_id, origin_id, resolved_from: "exact"\|"class_default"\|"none", items, skills, currency_amount}` — usable both as an API response and as the `characters.granted_kit` snapshot. Task #11 only needs to add `granted_at`. Requesting `origin_id=0` directly is reported as `"exact"`, not `"class_default"` (nothing was fallen back to). | #7, #11, #17 |
| N11 | **Bulk endpoints: a missing `?ids=` returns 422 (FastAPI required-param), not the 400 §3.1 promises.** Only a *malformed* `ids` value gives 400. The frontend must handle both codes. | #15, #17, #32 |
| N12 | **The 100-id cap is applied AFTER deduplication**, so `?ids=1,1,1,…` with 50 000 repeats passes the cap and the parse loop walks the whole string. SQL stays tiny and Nginx caps URL length, so impact is low — but the cap does not do the job §3.3 assigned it. Fixed by task #34. | #34, #30 |
| N13 | `GET /characters/{id}/public` also serves NPCs (the response carries `is_npc`); no filtering was specified or added. The characters-list page already shows NPCs today, so this is consistent — but if the passport should hide or differently present NPCs, that is a PM/design decision, not a bug. | #22, #30 |
| N14 | **Wording bug in the §3.6 step-2 warning.** «Выбранная стартовая точка недоступна, назначена точка по умолчанию.» is also shown when the player never picked one (`start_location_id IS NULL`) — assigning the default is then normal, not degradation. Implemented literally per spec so QA's «invalid → default» case matches. **Needs either two distinct messages or a neutral rewording — task #35.** | #35, #30 |
| N15 | **Claim flow deliberately left alone — confirmed by the user (2026-09-06).** `POST /requests/claim` and its approve branch do not set a start location, a starter kit, `registered_at` or `granted_kit`, because the character already exists. The user's answer: existing characters will not be playable and are to be re-created from scratch, so there is nothing to backdate. **Not a gap — do not raise it in review.** By the same token, the `granted_kit IS NULL` fallback of D18 is a transitional path only. | #30 |
| N16 | **GAP in the task breakdown, found by #15: `GET /characters/races` never exposes the new subrace fields.** Migration 019 added `distinctive_features`, `height_min`, `height_max`, `typical_origin_ids` to `subraces` and `models.py` has them, but `schemas.SubraceWithPreset` / `SubraceCreate` / `SubraceUpdate` / `SubraceResponse` do not, and the endpoint never populates them. No task (#5, #6, #7) was assigned this. **Blocks #17, #18, #23.** Fixed by task #36. | #36, #17, #18, #23 |
| N17 | `resolveStarterKit` omits `origin_id` entirely when it is 0/null rather than sending 0, so the response reads `class_default` instead of N10's `exact` — otherwise the «Путь» step would tell a player with no origin that the kit was picked specially for their country. | #17, #32 |
| N18 | `DELETE /locations/admin/origins/{id}` actually returns `{id, is_active}`, not `{message}` as §3.1 says. Typed to match reality. | #23, #27 |
| N19 | **inventory-service test isolation is order-dependent.** `tests/conftest.py:163` cannot `drop_all` cleanly because `items` ↔ `recipes` form a circular FK, so state leaks between tests; with a shuffling plugin installed the suite fails. **Not a CI risk — `pytest-randomly` is not in any `requirements.txt`, and a clean container run gives 466 passed** (verified by PM). Latent fragility only; filed as LOW in `docs/ISSUES.md`. | #30 |
| N20 | **`name` longer than 20 chars returned 422 with Pydantic's English text, not the 400 + Russian message §3.2 promises** — `Field(..., max_length=20)` fires before the domain validator, exactly the trap rule 30b fixed for the rejection reason. Flagged independently by the #6 developer and by QA. Fixed by task #36. | #36, #24 |
| N21 | Removing `Field(max_length=20)` from `name` (N20 fix) opened a subtle hole: `"   " + 20 chars` passes the domain check after `strip()` but would reach the `String(20)` column as 23 chars and raise MySQL 1406. The validator now **writes the cleaned name back** onto the payload, so the DB gets exactly what was validated. Keep that behaviour if the validator is refactored. | #24, #30 |
| N22 | **Derived-stat formulas had no documented source** — §3.7 refers to «the documented formulas» but no such document exists. Task #16 mirrored them from `character-attributes-service/constants.py` + `crud.py::compute_derived_stats` and `ProfilePage/StatsTab/DerivedStatsSection` (initiative) into `CharacterPassport/derived.ts`. **#17 must import `computeDerivedStats` from there**, or the wizard's StatExplainer and the passport will print different numbers for the same character. | #17, #29, #30 |
| N23 | Passport shows the kit block header from a three-state flag: `null` (wizard, nothing granted yet) → «Что будет выдано»; `true` → «Выдано при вступлении»; `false` → same header plus a muted «Запись восстановлена по реестру — оригинал выдачи не сохранился». Per N15 the `false` path is transitional only. PM approved keeping it visible: passing a live recalculation off as the original would lie exactly where rule 12d promises truth. | #22, #30 |
| N24 | A moderation request carries no starter kit (the kit is resolved at approval), so `fromModerationRequest` leaves `starterKit` undefined — the moderator sees the application, not promised loot. Not a gap. | #21, #30 |
| N25 | **GAP: `GET /characters/moderation-requests` never selects the new columns.** `crud.get_moderation_requests` (`crud.py:613-706`) omits `origin_id`, `start_location_id`, `skitaltsy_since_year/segment` and `rejection_reason`, so the moderator passport renders «—» for origin, tenure, first assignment and the «редкий выбор» badge. The frontend is already wired and lights up the moment the keys appear. Fixed by task #37. | #37, #21, #30 |
| N26 | **GAP vs rule 27: the passport cannot show stats.** Attributes live in character-attributes-service and are carried by neither `GET /characters/{id}/public` nor the moderation row, so the stat block never renders outside the wizard. Rule 27 lists «статы с производными» as passport content. Fixed by task #37. | #37, #22, #30 |
| N27 | `Admin/Request/RequestButton/` became dead code once #21 moved the buttons into the passport `footer`; PM deleted the directory. | #30 |
| N28 | `GET /locations/origins` returns only active origins, so a starter-kit override belonging to a hidden origin disappears from the coverage matrix and the selector. The row itself is intact and resumes working if the origin is restored. Cosmetic; a warning for «orphaned» overrides would be its own small task. | #30 |
| N29 | **Checked and dismissed — do not raise in review.** #17 flagged that `` `rarity-${x}` `` template classes (in `LootSection`, `EquipmentSlot`, `FastSlots`, `InventoryDndContext`, `ItemCell`) are invisible to Tailwind's content scan and might be purged, with no `safelist` in `tailwind.config.js`. **PM verified against the built bundle: all five `.rarity-*` rules are present in `dist/assets/*.css`.** They sit outside `@layer components`, so Tailwind never tree-shakes them. Not a bug; nothing filed. #17's own new code uses a static literal map anyway, which is safe either way. | #30 |
| N30 | R3 warned that `test_moderation_requests.py` mocks `crud.get_moderation_requests` wholesale, so a changed SELECT would leave those tests green while no longer reflecting reality — silent staleness. Task #37 closed that hole itself by adding `TestModerationRowShape`, which calls the real crud function against the in-memory session. Keep that test if the function is refactored. | #30 |
| N31 | `GET /characters/{id}/public` now returns `stats` (the ten preset keys, or `null` when character-attributes-service is unreachable). The frontend call sites still pass nothing into `PassportExtras.stats`, so the stat block stays hidden until task #38 wires it. | #38, #30 |
| N32 | The `background` field was repurposed: it used to be a 20-char «Происхождение» input, and origin is now a registry entity (rule 8), so #18 turned it into a free-text «Предыстория» textarea. The DB column was always unlimited `Text` — only the old JSX capped it at 20. Flagged in case a different label is wanted. | #30 |
| N33 | The `skitaltsy` Archive slug used by `LawsOfTheOrder` is **confirmed correct against prod** (PM fetched `/archive/articles/skitaltsy` earlier in this session). No not-found state to worry about. | #30 |
| N34 | **The origin step's gate lifts when `/locations/origins` is empty or unreachable** — otherwise a player would be permanently stuck in the wizard, and on day one the registry IS empty until the content is seeded (§3.10). `origin_id` is nullable on the backend, so this is safe. Deliberate trade-off of rule 33 against lock-out. | #30 |
| N35 | The saved draft is treated as **untrusted input**: `parseDraft` rebuilds the object field by field with type coercion, a corrupt field degrades to empty instead of killing the draft, the step index is clamped, and another user's or a >30-day-old draft is discarded. `kitPreview` is deliberately NOT saved — a stale kit in localStorage would be exactly the lie rule 12d forbids. Every `localStorage` access is wrapped in try/catch. | #30 |
| N36 | **«Халдея» in the wizard header is CORRECT — do not flag it.** PM mistook it for a leftover of the discarded setting and asked the user. The user's answer: **Халдея is the name of the world itself**, and other parts of the map with other names are planned. The line predates this feature (`CreateCharacterPage.tsx`, unchanged from HEAD) and stays as is. Эйдонэя is a continent/region within it, not a replacement. | #30 |
| N37 | The passport's band 2 collapses to a **single capped column** when there are neither stats nor a kit — the moderator screen and «Мои заявки» always hit this, and the list modal does too when character-attributes-service is unreachable. Without it, fixing the empty column on one screen would have recreated it mirrored on two others. | — |
| N38 | `book-page-gutter` now has **zero consumers**; kept defined in `index.css` and marked «Currently unused» in DESIGN-SYSTEM §16 rather than retired. PM's call to leave it. | — |
| N39 | **Browser/console verification was never performed** — no Claude-in-Chrome extension and no working MCP browser in this session (`pencil` failed with CONNECTION_CLOSED). Both the reviewer and the polish task said so plainly. Static checks, API-level live verification and the user's own screenshots stand in for it. **A console check remains outstanding before release.** | — |
| N8 | user-service tests need build deps for `mysqlclient` — run `apt-get install -y gcc pkg-config default-libmysqlclient-dev` before `pip install` in a bare `python:3.10-slim` container. Pre-existing, unrelated to this feature. | #25, #30 |


## 5. Review Log (filled by Reviewer — in English)

### Review #1 — 2026-09-06
**Result:** PASS

All 37 development tasks were re-verified against the running stack (24 containers, gateway on
`http://localhost`, local MySQL carrying the restored prod dump with all FEAT-154 migrations
applied). Every automated check was re-run from scratch rather than taken from the task reports.
Live verification was performed end to end through the API gateway; **browser verification was not
possible** — see the caveat below.

#### Automated Check Results
| Check | Result | Detail |
|---|---|---|
| `python -m py_compile` (37 changed/new `.py` files across 6 services + 4 migrations) | **PASS** | clean |
| `pytest` character-service | **PASS** | 796 passed, 1 skipped |
| `pytest` locations-service | **PASS** | 693 passed |
| `pytest` inventory-service | **PASS** | 466 passed |
| `pytest` skills-service | **PASS** | 210 passed |
| `pytest` photo-service | **PASS** | 193 passed |
| `pytest` user-service | **PASS** | 464 passed (needs `gcc pkg-config default-libmysqlclient-dev` — N8) |
| `npx tsc --noEmit` | **PASS** | 0 errors |
| `npx vite build` | **PASS** | built in 33.95s |
| `docker compose config` | **PASS** | valid |
| `nginx -t` on `nginx.conf` | **PASS** | syntax ok (tested against the repo file inside the compose network) |
| `nginx -t` on `nginx.prod.conf` | **PASS** | parses; fails only on the absent Let's Encrypt certificate, which is expected off-prod |

All six suites match the expected counts exactly.

#### Feature-Invariant Checks
| Invariant | Result | Evidence |
|---|---|---|
| **No hardcoded in-game year** (§3.5 hard constraint) | **PASS** | Grep of the whole diff for `1[0-9]{3}` returns only: `STUB_CURRENT_GAME_YEAR = 1787` (named constant, `test_create_request_validation.py:49`), one inline mock return in `test_my_requests.py:49`, player-entered tenure values `1783`/`1780` in fixtures, and one illustrative comment in `CharacterPassport.tsx:65`. **No production code path contains a year literal.** The year is read at runtime from `GET /locations/game-time` → `computed.year` (verified live: `1787`). |
| **Resolver called exactly once in approve** | **PASS** | `main.py:407` is the only `crud.resolve_starter_kit` call in the approve handler; `granted_kit_snapshot` (`:414-418`) is built from that same result, and `kit_items` / `kit_skills` are exactly what is sent to inventory and skills. **preview == granted == snapshotted** proven live (below). |
| **Derived stats computed by one function** | **PASS** | `computeDerivedStats` is defined once (`CharacterPassport/derived.ts:52`) and imported by both the passport adapters and the wizard's `StatExplainer.tsx:105`. No duplicated formula. |
| **No `avatar: 'string'`** | **PASS** | Only two matches repo-wide, both explanatory comments. `avatar` is `Optional[str] = None`; the live submit sent `null` and approve fell back to `subraces.image` (D5). |
| **`whitespace-pre-wrap`, never `dangerouslySetInnerHTML`** | **PASS** | All four free-text blocks render through `FreeText` (`CharacterPassport.tsx:129`, `:285`). Zero `dangerouslySetInnerHTML` in the new code — only comments forbidding it. |
| **Rule 24 — tenure has no mechanical effect** | **PASS** | Grep across all 14 backend services: `skitaltsy_since_*` is read only by validation, persistence and serialisation. No progression, XP, level or reward code touches it. On the frontend it appears only in the passport and request surfaces. |

#### Code-Standards Checklist
- Pydantic v1 throughout (`class Config: orm_mode = True`); no v2 construct anywhere — **PASS**
- sync/async not mixed: the inventory bulk route is sync `def`, the skills bulk route is `async` on `AsyncSession`, the new locations CRUD is fully awaited — **PASS**
- No `React.FC` in any changed or new `.tsx` — **PASS**
- No new `.jsx`; `ClassPage.jsx`, `ClassItem.jsx` and `BiographyPage.jsx` deleted (T3) — **PASS**
- No new SCSS; the three `.module.scss` files deleted; only `index.css` `@layer components` was extended, which task #14 authorises (T1) — **PASS**
- Design system extended rather than bypassed: `parchment` / `ink` / `font-lore` / `shadow-page` tokens plus `book-page`, `lore-*`, `wax-seal`, `passport-field`; `ArchiveLinkPreview` refactored off its hardcoded `#f5e6c8` — **PASS**
- Responsive from 360px: every grid has a `grid-cols-1` base, all arbitrary sizes are `max-w-*` or breakpoint-prefixed, `CoverageMatrix` ships a wrapping chip layout below `sm`, and `SubmitPage`'s `px-[120px]` is gone with the file (T5) — **PASS**
- No `any` in TypeScript anywhere in scope — **PASS**
- No TODO / FIXME / HACK in new backend or frontend code — **PASS**
- Alembic: revision ids 21 / 22 / 21 / 4 characters, chains correct (019→018, 020→019, 033→032, 0026→0025), every added column nullable or carrying a `server_default`, downgrades symmetric, 020's lossy downgrade documented in its docstring, and the old `class_id` unique looked up via `information_schema` and dropped **after** the pair unique is created (N9 — the spec text was wrong, the implementation is right) — **PASS**
- `models.StarterKit` carries `origin_id` and `UniqueConstraint('class_id','origin_id')`, and no longer `unique=True` on `class_id` — **PASS**

#### Security Checklist
- New admin routes all use `require_permission`, never `get_admin_user` (R10): `origins:read|create|update|delete` on the four locations routes, `characters:update` on the three starter-kit admin routes — **PASS**
- `origins:*` seeded by migration `0026` with the idempotent SELECT-then-INSERT `ROLE_ACTIONS` idiom; admin not granted explicitly — **PASS** (verified in the DB: permission ids 83–86)
- Rate limiting live-verified after rebuilding the gateway image: `POST /characters/requests/` returned `422×6, 429×6`; `PUT /characters/requests/{id}` returned `429×10` (same zone, already exhausted); `GET /characters/requests/my` and `/requests/claim` are **not** matched by the regex locations and stayed 200 — **PASS**
- `client_max_body_size 16m` on the avatar route: an 18.8 MB upload was rejected by nginx with 413 — **PASS**
- Bulk endpoints: ids parsed to `int`, deduplicated, capped at 100 counted **before** dedup (#34), parameterised `.in_()`. Live: 101 ids → 400; `ids=1;DROP TABLE skills` → 400 with a Russian message — **PASS**
- No SQL is string-built from user input anywhere in the new code — **PASS**
- The ownership check stays first on `POST /requests/`: a live `user_id` mismatch → **403**, unauthenticated → **401** — **PASS**
- All new user-facing API errors are Russian (12 domain messages verified live) — **PASS**
- Every new frontend API call surfaces its error to the player in Russian — **PASS** (one degraded-hint case in Minor Findings)
- No secret added; `LOCATIONS_SERVICE_URL` is a plain internal URL present in both compose files and safely defaulted in `config.py` — **PASS**

#### QA Coverage Verification
Backend was modified, and QA tasks #24–#28 and #33 all exist and are DONE. The new suites are present
and green: `test_create_request_validation.py`, `test_my_requests.py`, `test_public_character.py`,
`test_reject_reason.py`, `test_start_location_assignment.py`, `test_starter_kit_origins.py`,
`test_granted_kit_snapshot.py` (character-service); `test_starting_points.py`, `test_origins.py`,
`test_game_time_computed.py` (locations-service); `test_items_bulk.py`, `test_skills_bulk.py`,
`test_request_avatar_upload.py`. **PASS.**

#### Live Verification Results
⚠️ **Browser verification could NOT be performed.** Neither the `chrome-devtools` MCP server nor the
Claude-in-Chrome extension is available in this session (the only configured MCP server, `pencil`,
failed to connect). **The browser console was therefore never inspected, and no UI rendering,
click-through or visual 360px check was made.** Everything below was exercised against the live stack
through the API gateway with PowerShell. The static evidence for the UI (tsc, vite build, and a code
review of every new component) is recorded above and must not be read as a substitute for the console
check — a UI console pass is still outstanding and should be done before release.

Authenticated as `chaldea@admin.com` (`POST /users/login`, field `identifier`), user id 4, role admin.

**Read surface (all 200):** `/characters/classes`, `/characters/races` (now carrying
`distinctive_features`, `height_min`, `height_max`, `typical_origin_ids` — N16 / #36 confirmed),
`/characters/starter-kits`, `/characters/starter-kits/resolve`, `/inventory/items/bulk`,
`/skills/bulk` (returns `class_limitations`, not `class_id` — N1 confirmed), `/locations/origins`,
`/locations/starting-points`, `/locations/game-time` (now carries `computed`, existing keys intact).

**Origin registry (admin CRUD, rule 8, #23):** created «Республика Белый Клин» → id 1; the public
`/locations/origins` returned it without any `Countries.description` (rule 4 holds structurally);
`DELETE` → `{id, is_active: false}` (N18 confirmed) and the public list went empty;
`PUT is_active: true` restored it and the public list came back. **PASS.**

**Archive lore link (rules 8–10, N33):** `GET /archive/articles/preview/respublika-belyj-klin` →
**200** with title, summary and cover image, and `…/preview/skitaltsy` (used by `LawsOfTheOrder`) →
**200** as well. The origin row's `archive_slug` was set to the real prod slug and the lore-link path
was exercised end to end. **PASS.**

**Starting points (rules 18–20, #23):** flagged location 1183 through `PUT /locations/1183/update`
with `is_starting` + `starting_blurb`; `GET /locations/{id}/details` reflected both (N6 confirmed);
`/locations/starting-points` returned the curated single row with district / region / country names;
`/starting-points/1183` → 200 and `/starting-points/1184` (unflagged) → **404**. **PASS.**

**Starter kits by (class × origin), rules 12a–12c (#31, #32):** `PUT /starter-kits/1/origins/1`
created an override (item 2 ×3, skill 2, 777 gold). `resolve?class_id=1&origin_id=1` → `exact` plus
the override; `resolve?class_id=1` → the class default; `resolve?class_id=1&origin_id=99` →
`class_default` plus the default. `origin_id=0` on the pair route → **400** with the Russian redirect
message. `GET /starter-kits` with no params returned **only** the three class defaults, byte-compatible
with the old shape; `?include_origins=true` returned all four rows. `GET /starter-kits/coverage`
returned the three classes plus the one override. `DELETE` on the override → Russian confirmation and
`resolve` fell back to `class_default`; a second `DELETE` → **404**. **PASS.**

**Submission validation (§3.2, rules 31–34, #6, #24):** every rule returns **400 with its Russian
message** — subrace↔race mismatch, unknown class, invalid `sex`, tenure later than the current game
year, tenure before birth, a `start_location_id` that is not a starting point, a name over 20
characters (N20 / N21 fix confirmed — 400, not Pydantic's 422), blank appearance, out-of-range segment,
and an invalid age. An ownership mismatch → **403** (checked before domain validation, so the order is
preserved). Unauthenticated → **401**. The character limit at submit → **400** «Достигнут лимит
персонажей (максимум 5).» once the account reached five. The happy path → **200**, with the request
persisted carrying `origin_id`, `start_location_id` and `skitaltsy_since_year/segment`. **PASS.**

**Moderation (rules 28, 29, 30, 30a, 30b — #7, #8, #21, #37):**
`GET /characters/moderation-requests` now carries `origin_id`, `start_location_id`,
`skitaltsy_since_year`, `skitaltsy_since_segment` and `rejection_reason` (N25 / #37 confirmed).
Rejecting with a reason over 1000 characters → **400** «Причина отклонения не должна превышать 1000
символов.» (rule 30b). Rejecting with a reason → 200, and `GET /characters/requests/my` showed
`status=rejected` with the reason. Rejecting again → **409** «Отклонить можно только заявку, ожидающую
рассмотрения.» (rule 30a). `PUT /characters/requests/{id}` on the rejected request set the status back
to `pending` and cleared `rejection_reason` (N7 confirmed); `PUT` on the now-pending request → **409**.
**PASS.**

**Approval (rules 12d, 20, 22 — #11, #33):** approve returned `{"message": "Персонаж с ID 761 …",
"current_location_id": 1183, "location_warning": null}`. `GET /characters/761/public` returned
`registered_at`, `origin_id`, the tenure, `granted_kit_is_snapshot: true` and `stats`
(N26 / #37 / #38), and the avatar fell back to `subraces.image` because the request carried none (D5).
**preview == granted == snapshotted, proven live:** the snapshot
(`{items:[{2,3}], skills:[{2}], currency_amount:777, resolved_from:"exact"}`) is byte-identical to what
`/starter-kits/resolve` had returned, while `GET /inventory/761/items` shows exactly item 2 ×3,
`GET /skills/characters/761/skills` exactly skill 2, and `short_info.currency_balance` exactly 777.
**PASS.**

**Rule 12d retroactivity, proven live:** once the character existed, the override was edited to item 1
×9 / skill 1 / 5 gold. `GET /characters/761/public` returned its `granted_kit` **unchanged**, with
`granted_at` untouched. A freshly submitted and approved request for the same (class, origin) pair
(character 762) received the **new** contents. An admin edit therefore cannot rewrite an existing
passport. **PASS.**

**D18 fallback:** `GET /characters/699/public` (created before this feature) returned a live resolve
with `granted_kit_is_snapshot: false`, `registered_at: null` and `origin_id: null`. **PASS.**

**Avatar (rule 21, #10):** `POST /photo/upload_character_request_avatar` with a real PNG → **200**
`{"avatar_url": ".../character_avatar_drafts/char_draft_….webp"}`, and no DB row written. A
`text/plain` MIME → **400** with the Russian allowlist message. Unauthenticated → **401**. An 18.8 MB
file → **413** at the gateway. **PASS.**

**Subrace admin fields (rules 11, 14, 15 — #23, #36):** `PUT /characters/admin/subraces/3` persisted
`distinctive_features`, `height_min`, `height_max` and `typical_origin_ids`, and
`GET /characters/races` returned all four. **PASS.**

**`GET /characters/list`:** every additive key is present (`origin_id`, `registered_at`,
`skitaltsy_since_*`, `height`, `weight`, `current_location_id`, `subrace_image`) with all existing keys
intact. **PASS.**

**Service logs during the whole run:** zero 5xx from any FEAT-154 endpoint, and zero tracebacks in
character-service, locations-service, inventory-service or skills-service attributable to this feature.

**DB state after the migrations:** `alembic_version_character = 020_starter_kit_origin`,
`alembic_version_locations = 033_start_pts_origins`, `alembic_version_user = 0026`. `starter_kits` now
carries only `PRIMARY` and `uq_starter_kits_class_origin (class_id, origin_id)` — the old
single-column unique is gone and the foreign key is served by the pair index (N9). Permissions 83–86
are `origins:read|create|update|delete`.

#### Implementation Notes — dispositions
N1, N2, N5, N6, N7, N9, N10, N13, N14→#35, N15, N16→#36, N17, N18, N19, N20 / N21→#36, N22, N23, N24,
N25→#37, N26→#37, N28, N29, N30, N31→#38, N32, N33, N34 and N35 were all reviewed and accepted as
recorded; several were re-confirmed live above.

**N3 (413-vs-400 distinguished by matching the exception message) — Reviewer's call: ACCEPTED for this
feature, with a follow-up filed.** The fragility is real but contained: `convert_to_webp` is the only
raiser, both branches return correct sanitised Russian messages, and QA covers them. The clean fix (a
typed exception in `photo-service/utils.py`) touches a file every upload path shares and belongs in the
ISSUES entry that task #13 already opened, not here.

#### Minor Findings — none blocking, all recommended as follow-ups
| # | File:line | Description | Severity |
|---|---|---|---|
| 1 | `services/photo-service/main.py:765` | The catch-all in the new avatar endpoint returns `detail=str(e)`, so an unexpected boto3 / S3 / Pillow message (bucket names, paths) would reach the client. The 400 and 413 branches above it are correctly sanitised. It matches the 31 other occurrences in this file, so it is the file's pre-existing style — but this is new code. Suggest a static Russian message plus a server-side log. | LOW |
| 2 | `redux/actions/gameTimeActions.ts:21` + `StepPersona/TenureField.tsx:111-113` | When `GET /locations/game-time` fails, `fetchGameTime` rejects with a Russian message that `gameTimeSlice` stores but no FEAT-154 page reads, and the tenure hint keeps saying «Игровые часы ещё отвечают.» indefinitely. This is not a silent catch and not a lockout — the field stays optional, the backend still enforces both bounds, and a violation comes back as a visible 400 — but the wording misdescribes a hard failure. `gameTimeActions.ts` is **not** in this feature's diff; only the new consumers are. Suggest surfacing `gameTime.error` and rewording the fallback hint. | LOW |
| 3 | `redux/slices/racesSlice.ts:24-30` | The comment «`GET /characters/races` does not serialize them yet» is stale — task #36 closed that gap and the fields are now returned. | NIT |
| 4 | `033_starting_points_origins.py:21` vs `character-service/app/models.py` | `origin_countries.id` is `BigInteger` while `characters.origin_id`, `character_requests.origin_id` and `starter_kits.origin_id` are `Integer`. It only matters past 2^31 origins, but the two sides do not agree. | NIT |
| 5 | `services/skills-service/app/main.py:412`, `services/inventory-service/app/main.py:196` | A missing `?ids=` returns FastAPI's English 422 rather than a Russian 400 (N11, already recorded). Never reachable from the UI, which always sends the parameter. Accepted. | NIT |

#### Pre-existing issues noted (not caused by this feature, not blocking)
- `SUBRACE_SKILL_ID = 7` does not exist in the prod dataset, so every approval logs
  `Ошибка при массовом назначении навыков: 404 - {"detail":"Навык 7 не найден"}` and the universal
  subrace skill is silently not granted. The call is graceful by design, so approval still succeeds.
  This is a **content / data gap in the prod dump**, not a FEAT-154 regression — but it does mean new
  characters currently receive only their starter-kit skills.
- `utils.py:130` rejects any image that compresses to under 100 bytes as «Invalid WEBP conversion
  result», so a tiny flat-colour avatar is refused with a 400. Pre-existing in `convert_to_webp`,
  untouched here, and it only affects degenerate images.
- The running `api-gateway` image was stale at the start of the review (built before task #12), so the
  new rate limits and the 16 MB body cap were not active. The **configuration files are correct** — the
  image simply had not been rebuilt. The Reviewer rebuilt it (`docker compose build api-gateway`) and
  then verified the limits live. **Deployment must rebuild the gateway image**; a plain
  `docker compose up -d` will not pick these up.

#### Review-created data in the local dev database
Verification wrote real rows into the local prod-dump database. If a clean seeding baseline is wanted,
remove: `origin_countries` id 1 («Республика Белый Клин», `archive_slug = respublika-belyj-klin`); the `is_starting` flag and `starting_blurb`
on location 1183; characters 761 and 762 with their requests 39 and 40; the `distinctive_features`,
`height_min`, `height_max` and `typical_origin_ids` values written onto subrace 3; and one orphaned
object under the S3 prefix `character_avatar_drafts/`. The starter-kit override created for
(class 1 × origin 1) was already deleted during the run.

---

## 6. Logging (filled by all agents — in Russian)

```
[LOG] 2026-09-06 — PM: фича создана по итогам обсуждения с пользователем, статус OPEN
[LOG] 2026-09-06 — PM: предварительный анализ текущего флоу и лора мира выполнен, результаты учтены в брифе
[LOG] 2026-09-06 — PM: зафиксировано критическое ограничение — локальный сид содержит устаревший сеттинг, источник данных только прод
[LOG] 2026-09-06 — Analyst: начал анализ, изучаю character-service, locations-service, photo-service, user-service (RBAC) и фронтенд
[LOG] 2026-09-06 — Analyst: подтверждено — эндпоинта «мои заявки» нет; у Location нет признака стартовой точки; у character-service нет LOCATIONS_SERVICE_URL
[LOG] 2026-09-06 — Analyst: ключевая проблема аватара — /photo/change_character_avatar_photo требует существующего персонажа с владельцем (404/403); найдены 4 generic-эндпоинта загрузки как прецедент
[LOG] 2026-09-06 — Analyst: игровое время — счётчик {год с 1, сегмент, неделя}, года 1788 в коде нет; правило 23 требует решения Архитектора
[LOG] 2026-09-06 — Analyst: обнаружено 9 посторонних багов (незащищённые мутирующие эндпоинты, EQUIPMENT_SERVICE_URL, двойная выдача стартового набора) — вынесены в секцию 2, требуется занести в ISSUES.md
[LOG] 2026-09-06 — Analyst: анализ завершён, затронуто 7 сервисов (4 с изменениями кода, 3 только на чтение)
[LOG] 2026-09-06 — Architect: начал проектирование, сверил модели, схемы, головы Alembic и RBAC-паттерн по коду
[LOG] 2026-09-06 — Architect: справочник происхождения отдан locations-service (новая таблица origin_countries), character-service хранит только origin_id без FK — ни один сервис не пишет в чужие таблицы (R6)
[LOG] 2026-09-06 — Architect: аватар — новый обезличенный эндпоинт в photo-service по образцу upload_ticket_attachment; если аватара нет — при одобрении подставляется арт подрасы (R1)
[LOG] 2026-09-06 — Architect: вызов locations-service при одобрении классифицирован как graceful, а не critical; при любом сбое — цепочка фолбэков, персонаж не застревает (R2, R4)
[LOG] 2026-09-06 — Architect: дублирующие HTTP+RabbitMQ публикации в approve решено НЕ трогать — проверено, что consumer'ы идемпотентны; остаётся в ISSUES.md
[LOG] 2026-09-06 — Architect: N+1 на стартовых наборах решается двумя публичными bulk-эндпоинтами (items и skills), резолвит фронт — 3 запроса вместо N (R7)
[LOG] 2026-09-06 — Architect: получена поправка от PM — игровой год на проде считается корректно через offset_days; правило 23 спроектировано напрямую, без открытого вопроса (R8 снят)
[LOG] 2026-09-06 — Architect: в публичный GET /locations/game-time добавляется готовый блок computed — календарь не дублируется в третий раз
[LOG] 2026-09-06 — Architect: зафиксировано жёсткое ограничение: игровой год нигде не хардкодится, только runtime из game-time; перевод часов перед релизом не должен требовать правок кода
[LOG] 2026-09-06 — Architect: все новые колонки nullable, все новые Pydantic-поля Optional, проверка владельца остаётся первой — 13 тестовых модулей не ломаются (R3)
[LOG] 2026-09-06 — Architect: новые админ-эндпоинты — только require_permission, модуль origins заводится миграцией 0026 (R10)
[LOG] 2026-09-06 — Architect: спроектировано расширение дизайн-системы (токены parchment/ink, шрифты lore/serif, классы book-page) и единый компонент паспорта на 4 места с 4 адаптерами
[LOG] 2026-09-06 — Architect: проектирование завершено — 30 задач, 21 API-контракт, 3 миграции, 5 QA-задач, 6 открытых вопросов к пользователю (главный — наполнение контентом)
[LOG] 2026-09-06 — Architect: получены ответы на все 6 вопросов — 5 подтвердили спроектированные решения, шестой добавил правила 12a-12c
[LOG] 2026-09-06 — Architect: стартовые наборы перепроектированы на пару (класс × происхождение) с фолбэком на набор класса; добавлена миграция 020_starter_kit_origin
[LOG] 2026-09-06 — Architect: вместо nullable origin_id взят сентинел 0 — MySQL считает NULL разными в UNIQUE, иначе у класса могло бы быть два дефолта; отклонение от брифа явно обосновано в D16
[LOG] 2026-09-06 — Architect: резолв набора вынесен в одну функцию resolve_starter_kit — мастер, одобрение и паспорт вызывают её же, игрок не может получить не то, что видел
[LOG] 2026-09-06 — Architect: старые эндпоинты наборов сохранены без изменений — существующая админка и 15 тестов продолжают работать; добавлены resolve, pair PUT/DELETE и coverage
[LOG] 2026-09-06 — Architect: добавлена §3.10 — чек-лист наполнения контентом для пользователя, каждый пункт имеет свою админ-задачу
[LOG] 2026-09-06 — Architect: ревизия завершена — 33 задачи, 27 API-контрактов, 4 миграции, 6 QA-задач, открытых вопросов нет
[LOG] 2026-09-06 — Architect: по решению пользователя D17 развёрнут — выданный набор замораживается в characters.granted_kit при одобрении (правило 12d)
[LOG] 2026-09-06 — Architect: одобрение вызывает resolve_starter_kit ровно один раз, один результат идёт и в выдачу, и в снимок — свойство preview == granted == snapshotted
[LOG] 2026-09-06 — Architect: бэкфилл снимков сознательно НЕ делается (D18): NULL честно означает реконструкцию, а не выдуманную запись; в API есть флаг granted_kit_is_snapshot
[LOG] 2026-09-06 — Architect: снимок фиксирует id предметов и навыков, а не их названия и иконки — переименованный предмет остаётся тем же предметом (D19)
[LOG] 2026-09-06 — Architect: обновлены задачи #7, #11, #16, #29, #30, #31, #33; в QA добавлен тест на то, что правка набора в админке не меняет паспорт уже созданного персонажа
[LOG] 2026-09-06 — Architect: секции 3 и 4 готовы к разработке — 33 задачи, 27 API-контрактов, 4 миграции, 6 QA-задач, открытых вопросов нет
[LOG] 2026-09-06 — PM: архитектура утверждена, запущена волна 1 разработки
[LOG] 2026-09-06 — Backend Dev: задача #5 выполнена (миграция 019, 13 колонок, все nullable); 591 тест зелёный, регрессий нет
[LOG] 2026-09-06 — Backend Dev: задачи #1 и #3 выполнены (миграция 033, origin_countries, computed в game-time); 637 тестов зелёных, миграция проверена на живом MySQL 8 циклом upgrade/downgrade/upgrade
[LOG] 2026-09-06 — PM: задачи #6 придержана до завершения #31 и #8 — конфликт по файлам character-service
[LOG] 2026-09-06 — Frontend Dev: задача #14 выполнена (токены parchment/ink/font-lore/shadow-page, 7 классов book-page/lore-*/wax-seal/passport-field, DESIGN-SYSTEM.md секция 16); tsc 0 ошибок, vite build успешен
[LOG] 2026-09-06 — Backend Dev: задача #8 выполнена (reject с необязательной причиной, уведомление character_request_rejected в general_notifications); 591 тест, базовая линия удержана
[LOG] 2026-09-06 — Backend Dev: задача #2 выполнена (7 эндпоинтов: стартовые точки, публичные и админские происхождения с мягким удалением); 637 тестов, базовая линия удержана
[LOG] 2026-09-06 — Backend Dev: задачи #4, #9, #10 выполнены (RBAC origins, bulk-резолв в двух сервисах, загрузка аватара до создания персонажа); тесты зелёные: inventory 444, skills 186, photo 175, user 464
[LOG] 2026-09-06 — PM: заведён раздел Implementation Notes (N1-N8) — расхождения реализации со спецификацией для последующих задач
[LOG] 2026-09-06 — Backend Dev: задача #31 выполнена (миграция 020, киты по паре класс×происхождение, resolve_starter_kit, 5 эндпоинтов); 593 теста против базовой линии 591, обратная совместимость старых эндпоинтов подтверждена тестами
[LOG] 2026-09-06 — Backend Dev: при реализации #31 обнаружено, что порядок DDL в §3.4 упал бы на проде (FK держит индекс) — порядок переставлен, зафиксировано в N9
[LOG] 2026-09-06 — PM: критический путь пройден, запущены #6 и QA-задачи #27, #28
[LOG] 2026-09-06 — Backend Dev: задача #6 выполнена (валидатор заявки, клиент к locations-service, лимит персонажей при подаче); 593 теста, базовая линия удержана, существующие тесты править не потребовалось
[LOG] 2026-09-06 — PM: запущены #7 (игровые эндпоинты + правила 30a/30b) и #11 (переработка одобрения) параллельно в character-service
[LOG] 2026-09-06 — QA: задачи #27 и #28 выполнены, +118 тестов (locations 693, inventory 465, skills 209, photo 193), все зелёные
[LOG] 2026-09-06 — QA: найдено, что лимит в 100 id считается после дедупликации — заведена задача #34
[LOG] 2026-09-06 — Backend Dev: задача #7 выполнена (классы, мои заявки, редактирование отклонённой, публичный паспорт персонажа, правила 30a/30b); 593 теста, базовая линия удержана; запись про reject закрыта в ISSUES.md
[LOG] 2026-09-06 — PM: фронтенд разблокирован, запущена #15 (слой API и типы)
[LOG] 2026-09-06 — Backend Dev: задача #11 выполнена (цепочка стартовой локации graceful, registered_at, granted_kit); резолвер вызывается ровно один раз, выдача равна слепку — зафиксировано тестами; 593 теста, 12 тестов одобрения зелёные
[LOG] 2026-09-06 — PM: костяк бэкенда закрыт; запущены QA #25/#26/#33 и DevSecOps #12/#13; заведена задача #35 по формулировке предупреждения (N14)
[LOG] 2026-09-06 — PM: пользователь подтвердил, что существующие персонажи не станут игровыми и будут созданы заново — ветка присвоения намеренно не трогается (N15)
[LOG] 2026-09-06 — DevSecOps: задачи #12, #13 выполнены (LOCATIONS_SERVICE_URL в оба compose, rate limiting в оба конфига Nginx, nginx -t зелёный на обоих)
[LOG] 2026-09-06 — Backend Dev: задача #34 выполнена (лимит bulk считается до дедупликации); inventory 466, skills 210
[LOG] 2026-09-06 — Frontend Dev: задача #15 выполнена (9 новых модулей API, слайс происхождений, типы сверены с Pydantic-схемами бэкенда); tsc 0 ошибок, build успешен
[LOG] 2026-09-06 — PM: обнаружен пробел в разбивке — эндпоинт рас не отдаёт новые поля подрасы (N16); заведена и запущена задача #36
[LOG] 2026-09-06 — QA: задачи #25, #26, #33 выполнены, +130 тестов (723 passed против базовой линии 593), сломанного кода не найдено
[LOG] 2026-09-06 — QA: заморозка набора проверена побайтовым сравнением слепка до и после редактирования набора в админке
[LOG] 2026-09-06 — PM: запущены #36 (поля подрасы + русское сообщение для длины имени) и #16 (компонент паспорта)
[LOG] 2026-09-06 — Backend Dev: задача #36 выполнена (4 поля подрасы в API, русское 400 на длинное имя); 723 теста, базовая линия удержана
[LOG] 2026-09-06 — PM: запущены #23 (админские формы — без них пользователь не сможет наполнить фичу контентом) и QA #24
[LOG] 2026-09-06 — Frontend Dev: задача #16 выполнена (CharacterPassport, 4 адаптера, формулы производных вынесены в derived.ts, классы lore-badge* в дизайн-систему); tsc 0 ошибок, build успешен
[LOG] 2026-09-06 — PM: запущены #17 (пролог и шаги 1-3 мастера), #21 (экран модератора) и #22 (список персонажей)
[LOG] 2026-09-06 — QA: задача #24 выполнена, +63 теста (786 passed против 723); закрыт пробел — теста на успешное создание заявки в проекте не было вовсе
[LOG] 2026-09-06 — Frontend Dev: задача #23 выполнена (админка происхождений со скрытием/возвратом, поля подрасы, стартовая точка в форме локации); tsc чисто, build успешен
[LOG] 2026-09-06 — PM: запущены #29+#35 (документация и формулировка предупреждения) и #32 (админка стартовых наборов)
[LOG] 2026-09-06 — Frontend Dev: задачи #21 и #22 выполнены (паспорт у модератора с модалкой причины отказа, компактные карточки в списке — 0 запросов на карточку); tsc чисто, build успешен
[LOG] 2026-09-06 — PM: обнаружены два пробела данных (N25, N26) — модерация не отдаёт новые поля, паспорт негде взять статы; заведена и запущена задача #37
[LOG] 2026-09-06 — Frontend Dev: задача #32 выполнена (матрица покрытия 3x8 с тремя состояниями ячейки, возврат к набору класса, обратная совместимость редактирования дефолта); tsc чисто в своей зоне, build успешен
[LOG] 2026-09-06 — Frontend Dev: задача #17 выполнена (пролог, шаги Кровь/Родина/Путь, StatExplainer на общих формулах, предпросмотр 7 подклассов и реального набора); удалены INITIAL_CLASSES и все .jsx/.scss мастера кроме BiographyPage; tsc 0 ошибок, build успешен
[LOG] 2026-09-06 — PM: проверил по собранному бандлу подозрение #17 на вырезание классов редкости — ложная тревога, все пять правил на месте (N29)
[LOG] 2026-09-06 — Backend Dev: задачи #35 и #29 выполнены (предупреждение разделено на два случая, документация трёх сервисов + CLAUDE.md + ARCHITECTURE.md приведены к реальности); 786 тестов, базовая линия удержана
[LOG] 2026-09-06 — Backend Dev: задача #37 выполнена (5 колонок в выборке модерации, статы в публичном паспорте graceful); 796 тестов против 786
[LOG] 2026-09-06 — Backend Dev: закрыт риск R3 — добавлен тест на реальную функцию выборки вместо мока, который не заметил бы пропажу колонки
[LOG] 2026-09-06 — PM: заведена и запущена задача #38 — подключить блок статов в паспорте на фронте
[LOG] 2026-09-06 — Frontend Dev: задача #38 выполнена (блок статов подключён в модалке паспорта, stats: null деградирует без блока); tsc 0 ошибок, build успешен
[LOG] 2026-09-06 — Frontend Dev: задача #18 выполнена (шаги Личность и Контракт, загрузка аватара, памятка о внешности, подсказка по росту, законы Скитальцев, паспорт с подписью контракта); удалены BiographyPage.jsx+SCSS и весь старый SubmitPage; в мастере не осталось ни одного .jsx/.scss; tsc 0 ошибок, build успешен
[LOG] 2026-09-06 — Frontend Dev: задача #19 выполнена (машина из 5 шагов, useWizardValidation как единственный источник правил блокировки, черновик в localStorage с очисткой после отправки); закрыта дыра с прыжком по кружкам пагинации на финальный шаг; tsc 0 ошибок, build успешен
[LOG] 2026-09-06 — Frontend Dev: задача #20 выполнена (страница «Мои заявки», редактор отклонённой заявки на переиспользованных шагах мастера, переход после отправки на my-requests); tsc 0 ошибок, build успешен
[LOG] 2026-09-06 — PM: все 37 задач разработки закрыты, остаётся ревью (#30)
[LOG] 2026-09-06 — Reviewer: начал финальную проверку (#30)
[LOG] 2026-09-06 — Reviewer: автопроверки перезапущены с нуля — py_compile чисто, tsc 0 ошибок, vite build успешен, тесты 796/693/466/210/193/464, всё сошлось с ожидаемыми цифрами
[LOG] 2026-09-06 — Reviewer: год нигде не захардкожен, резолвер в одобрении вызывается ровно один раз, производные считаются одной функцией, avatar: 'string' нет
[LOG] 2026-09-06 — Reviewer: живая проверка через шлюз — создание/скрытие/возврат происхождения, стартовая точка, валидация заявки, отказ с причиной, 409 на повторный отказ, редактирование и переотправка, одобрение, загрузка аватара, ссылка на статью Архива
[LOG] 2026-09-06 — Reviewer: правило 12d подтверждено живьём — выдано ровно то, что показывал резолвер, а правка набора в админке не изменила паспорт уже созданного персонажа
[LOG] 2026-09-06 — Reviewer: образ api-gateway оказался устаревшим — пересобран, после этого лимиты запросов и кап 16 МБ работают; при деплое нужна пересборка шлюза
[LOG] 2026-09-06 — Reviewer: браузерная проверка НЕ выполнялась — ни chrome-devtools MCP, ни расширения Claude-in-Chrome в сессии нет, консоль не проверена
[LOG] 2026-09-06 — Reviewer: проверка завершена, результат PASS; 5 неблокирующих замечаний записаны в секцию 5
[LOG] 2026-09-06 — PM: уточнено у пользователя — «Халдея» это название мира, а не остаток старого сеттинга; текст в шапке мастера остаётся без изменений (N36)
[LOG] 2026-09-06 — Reviewer: ревью завершено, вердикт PASS; все автопроверки перезапущены (796/693/466/210/193/464, tsc 0, build OK); живая проверка через API, браузерная консоль не проверялась
[LOG] 2026-09-06 — Reviewer: обнаружено, что образ api-gateway был собран до задачи #12 — лимиты частоты не работали; после пересборки проверены и работают
[LOG] 2026-09-06 — Frontend Dev: задача #39 выполнена (паспорт перекомпонован в три полосы, корешок убран, три находки ревью закрыты)
[LOG] 2026-09-06 — Backend Dev: задача #40 выполнена (миграция-заглушка навыка id 7); попутно найден баг обрыва батча в assign_multiple, занесён в ISSUES.md
[LOG] 2026-09-06 — PM: все задачи закрыты, ревью PASS, итоговая сводка заполнена; фича готова к визуальной проверке пользователем и коммиту
```

---

## 7. Completion Summary (filled by PM on close — in Russian)

### Что сделано

Создание персонажа переделано из формы в сценарий вступления в организацию «Скитальцы»: пролог от Координатора на Цитадели, пять шагов (Кровь → Родина → Путь → Личность → Контракт) и паспорт Скитальца вместо сухого превью.

**Погружение.** Расы и подрасы с лором и артами, страна происхождения с гербом и строкой «как здесь смотрят на Скитальцев», лорные тултипы из Архива, блок о законах организации, УР как внутримировое объяснение уровней, номер Мегалинка, дата регистрации по игровому календарю.

**Осмысленность.** Характеристики объясняются с производными значениями (HP, мана, инициатива), архетипом билда и сравнением со средним по подрасам; проговаривается, что пресет — это 100 очков, столько же набирается за 10 уровней. Класс показывает 7 подклассов как ветки развития и реальный стартовый набор из БД вместо фиктивных `item1`/`skill3`.

**Новые сущности.** Происхождение стало справочником (`origin_countries`, 8 стран, шире карты). Стартовая локация выбирается из курируемого списка (`Locations.is_starting`). Стартовые наборы задаются парой (класс × происхождение) с откатом к набору класса. У подрасы появились отличительные особенности и диапазон роста.

**Заморозка выданного.** `characters.granted_kit` — снимок того, что персонажу действительно выдали. Резолвер вызывается в одобрении ровно один раз, из одного результата собирается и выдача, и снимок: разойтись они не могут по построению. Позднее редактирование набора не меняет паспорта уже созданных персонажей.

**Починено попутно.** Аватар реально загружается (был литерал `avatar: 'string'`). Стартовая локация назначается (было NULL). Появилась валидация на обоих концах с русскими сообщениями. Лимит персонажей проверяется при подаче, а не только при одобрении. Отказ получил причину, уведомление и страницу «Мои заявки» с правкой и переотправкой. Черновик анкеты автосохраняется.

**Долг закрыт.** Все `.jsx` и SCSS мастера мигрированы на TSX+Tailwind; удалён мёртвый код (`RaceCarousel`, `RequestButton`, старый `SubmitPage`); дизайн-система расширена секцией книжных поверхностей.

### Что изменилось от первоначального плана

- **Стартовые наборы стали зависеть от происхождения** (правила 12a-12c) — требование появилось по ходу обсуждения, потребовало миграции 020 и второго измерения в админке.
- **Выданный набор замораживается** (правило 12d, решение D17 развёрнуто) — паспорт задуман как достоверная запись, а пересчёт задним числом ей противоречил.
- **Правило 23 не потребовало новой механики** — вопреки анализу, лорный год уже вычисляется существующими часами через `offset_days`.
- **Расовые навыки вынесены в отдельную фичу** по решению пользователя; вместо них временная заглушка (задача #40).
- **Появилось 8 незапланированных задач** (#31-#40) — часть по новым требованиям, часть закрывала пробелы, найденные исполнителями: эндпоинт рас не отдавал новые поля подрасы (N16), модерация не отдавала новые колонки (N25), паспорту негде было взять статы (N26).

### Оставшиеся риски и follow-up

1. **Браузерная консоль не проверена** (N39) — в сессии не было подключения к браузеру. Проверить перед выкатом.
2. **При деплое обязательно пересобрать api-gateway** — конфиги с rate limiting верны, но образ собирается отдельно; `up -d` без пересборки оставит лимиты мёртвыми.
3. **Контент не заведён** — справочник происхождений, стартовые точки, поля подрас и наборы по парам заполняет пользователь через админку (чек-лист в §3.10). До заполнения шаги «Родина» и «Начало пути» показывают пустые состояния, обработанные корректно.
4. **Осиротевшие аватары в S3** — уборщик не делался, вынесен отдельной задачей в `docs/ISSUES.md`.
5. **`assign_multiple` обрывает батч** на первом неизвестном навыке — триггер устранён заглушкой, хрупкость осталась, запись в `docs/ISSUES.md`.
6. **Прод-дефолт CORS небезопасен** у пяти сервисов — найдено попутно, к фиче не относится, запись в `docs/ISSUES.md`.
7. **Расовые навыки** — отдельная фича, механика (ограничения по расе/подрасе + админ-категории) уже готова, нужен контент.
