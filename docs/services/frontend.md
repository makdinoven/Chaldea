# Frontend

**Порт:** 5555
**Технологии:** React 18, Vite, Redux Toolkit, React Router v6, Axios, ReactFlow, SCSS
**Путь:** `/home/dudka/chaldea/services/frontend/app-chaldea/`

## Назначение

SPA-клиент для браузерной RPG. Аутентификация, создание персонажей, карта мира, PvP-бои, админ-панели.

## Структура файлов

```
src/
├── main.jsx                   # Entry point (Provider + App)
├── api/
│   ├── api.js                 # Base URLs (захардкожены с domain:port)
│   ├── client.js              # Axios instance для inventory
│   ├── items.js               # Item API methods
│   └── characters.js          # Character API methods
├── redux/
│   ├── store.js               # Redux store (10 slices)
│   ├── slices/                # userSlice, countriesSlice, adminLocationsSlice, skillsAdminSlice...
│   ├── actions/               # 8 async thunks
│   └── selectors/             # locationSelectors
├── components/
│   ├── App/Layout/            # Header + Outlet
│   ├── StartPage/             # Login/Register
│   ├── HomePage/              # Dashboard
│   ├── CreateCharacterPage/   # 4-step character creation
│   ├── WorldPage/             # Interactive world map
│   ├── CountryPage/           # Country details
│   ├── pages/
│   │   ├── LocationPage/      # Location details, players, posts
│   │   └── BattlePage/        # PvP combat UI
│   ├── AdminLocationsPage/    # CRUD иерархии мира
│   ├── AdminSkillsPage/       # Skill tree editor (ReactFlow)
│   ├── ItemsAdminPage/        # Item CRUD + issue to characters
│   ├── Admin/RequestsPage/    # Character moderation
│   └── CommonComponents/      # Button, Modal, Input, PlayerCard, Tooltip, Loader...
├── hooks/
│   ├── useNavigateTo          # Navigation wrapper
│   ├── useRequireAuth         # Auth guard
│   ├── useBodyBackground      # Dynamic background images
│   └── useDebounce            # Debounce utility
├── helpers/
│   ├── commonConstants.js     # Translations, skill keys, colors
│   └── helpers.js             # Time/resource formatting
└── assets/                    # Images, SVG icons
```

## Роуты

| Путь | Компонент | Описание |
|------|-----------|----------|
| `/` | StartPage | Login/Register |
| `/home` | HomePage | Dashboard |
| `/createCharacter` | CreateCharacterPage | 4-step wizard |
| `/world` | WorldPage | World map |
| `/world/country/:countryId/` | CountryPage | Country details |
| `/location/:locationId` | LocationPage | Location + players + posts |
| `/location/:locationId/battle/:battleId` | BattlePage | PvP combat |
| `/admin/locations` | AdminLocationsPage | Location editor |
| `/home/admin/skills` | AdminSkillsPage | Skill tree editor |
| `/admin/items` | ItemsAdminPage | Item editor |
| `/requestsPage` | RequestsPage | Character moderation |

## State Management (Redux)

10 slices:
- **userSlice** - auth, profile, `getMe` thunk
- **countriesSlice** - список стран, `fetchCountries`
- **countryDetailsSlice** - детали страны
- **regionsSlice** - `fetchRegionDetails`
- **adminLocationsSlice** - CRUD для admin panel
- **countryEditSlice / regionEditSlice / districtEditSlice / locationEditSlice** - формы редактирования
- **skillsAdminSlice** - `fetchSkills`, `fetchSkillFullTree`, `updateSkillFullTree`

## Ключевые страницы

### BattlePage (самая сложная)
- 2-player PvP interface (left | controls | right)
- Polling каждые 5 секунд для обновления состояния
- Выбор навыков: attack / defense / support
- Использование предметов из быстрых слотов
- Отображение HP/Mana/Energy/Stamina баров
- Активные эффекты (баффы/дебаффы)
- Таймер хода
- **Autobattle toggle** (3 mode: balanced/attack/defence)
- Modal победы/поражения

### CreateCharacterPage
- 4 шага: раса -> класс -> биография -> review
- Предпросмотр стартовых навыков и предметов по классу

### AdminSkillsPage
- Визуальный редактор дерева навыков через ReactFlow
- Drag-and-drop нод
- Загрузка изображений рангов

## API Integration

**Захардкоженные URL** в api.js (используется конкретный домен + порты):
- `http://4452515-co41851.twc1.net:8006` - locations
- `http://4452515-co41851.twc1.net:8000` - users
- `http://4452515-co41851.twc1.net:8010` - battles
- `http://4452515-co41851.twc1.net:8011` - autobattle
- и т.д.

**Auth:** Token в localStorage, Bearer header.

## Известные проблемы

1. **Захардкоженные URL** - не через env variables, разбросаны по файлам
2. **Нет Error Boundaries** - компоненты могут крэшнуть без graceful fallback
3. **Микс axios и fetch** - непоследовательный подход
4. **alert() для UX** - вместо toast/notification system
5. **Polling вместо WebSocket** - BattlePage опрашивает каждые 5 сек
6. **refreshKey={Math.random()}** - антипаттерн для принудительного ре-рендера
7. **Нет refresh token rotation** - нет обработки expired tokens
8. **Неимплементированные роуты** - auction, guide, learning, shop - упоминаются в меню
9. **Захардкоженные данные** - HomePage stats, class previews
10. **Нет accessibility** - ARIA labels, keyboard navigation
