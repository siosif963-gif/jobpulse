# JobPulse

**JobPulse** — веб-приложение, которое раз в сутки собирает IT-вакансии с Habr Career, хранит их и историю изменения зарплат в БД и показывает аналитику на интерактивном дашборде: динамику зарплат, распределение по технологиям, городам и грейдам, сводные метрики и таблицу свежих вакансий.

Помогает ответить на вопросы: «Растут ли зарплаты Python-разработчиков?», «Где больше вакансий для Middle — Москва или удалёнка?», «Какие технологии сейчас в топе?».

## 1. Архитектура

```
[Routers]   HTTP: валидация параметров (Pydantic), вызов сервисов, HTTP-статусы
    ↓
[Services]  бизнес-логика, ORM, агрегации. Ничего не знают об HTTP
    ↓
[Parsers]   внешний источник: HTTP-запросы, разбор JSON. Ничего не знают о БД
    ↓
[Models + Database]  ORM-модели, движок, сессии
```

```
backend/    FastAPI + SQLAlchemy 2.0 + APScheduler (main.py, scheduler.py, cli.py, models/, parsers/, services/, routers/, tests/)
frontend/   HTML + CSS + Vanilla JS (ES-модули) + Chart.js 4.4.1
docs/       DECISIONS.md — решения по пробелам в ТЗ
```

Только `services/parser_service.py` импортирует парсеры; фронтенд делает сетевые запросы только в `frontend/api.js`.

## 2. Какие данные собираются и откуда

- Источник — **внутренний JSON-эндпоинт фронтенда Habr Career** `GET /api/frontend/vacancies?q=...&page=...` (без авторизации, 25 вакансий на странице). HTML не парсится.
- Сохраняются: название, компания, вилка зарплаты и валюта, города, признак удалёнки, грейд, навыки (технологии), тип занятости, ссылка, дата публикации.
- Поле `predictedSalary` (прогноз Habr) **не используется** — только зарплата, указанная работодателем.
- Эндпоинт **не документирован и может измениться**: парсер определяет смену структуры, останавливает запуск и пишет CRITICAL-сообщение в лог.
- Бережная нагрузка: один запуск в сутки, случайные задержки 1–3 с, не более 2 параллельных запросов, один User-Agent.
- Используйте приложение с учётом пользовательского соглашения Habr Career.

## 3. Методика расчётов

- **Точка зарплаты** вакансии: среднее вилки «от–до»; если указана одна граница — она сама. Вилки только «от» занижают оценку, только «до» — завышают/занижают в зависимости от практики работодателей.
- **Группировка по дате публикации** (`published_at`) в часовом поясе `APP_TIMEZONE`: день, неделя (с понедельника) или месяц.
- **Окно анализа** — `days` (1–365; по умолчанию 30): учитываются вакансии, опубликованные в этот период (в том числе уже неактивные).
- **Проценты** в распределениях считаются от числа вакансий окна; у вакансии несколько технологий/городов, поэтому сумма процентов может превышать 100%.
- **Зарплатная статистика — только в выбранной валюте** (конвертации нет).
- **Неактивность**: после полного обхода запроса `__all__` не встреченные вакансии становятся неактивными; кроме того, вакансия, не встречавшаяся `STALE_AFTER_DAYS` дней, деактивируется. Вакансии не удаляются.

## 4. Быстрый старт локально

Нужен Python 3.11 или 3.12.

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
python cli.py seed-demo          # демо-данные (или см. раздел 5)
uvicorn main:app --reload --workers 1
```

Фронтенд (в другом терминале):

```bash
cd frontend
python -m http.server 8080
```

Откройте `http://localhost:8080`. API и Swagger: `http://localhost:8000/docs`.

## 5. Первый сбор данных

```bash
cd backend
python cli.py parse --force              # полный сбор по всем активным запросам
python cli.py parse --force --max-pages 2   # быстрая проверка
python cli.py seed-demo [--count 300]    # демо-вакансии (только APP_ENV=development)
python cli.py clear-demo                 # удалить демо-вакансии
```

При пустой БД и включённом планировщике парсинг стартует сам через 10 секунд после запуска (`PARSING_RUN_ON_STARTUP_IF_EMPTY`).

## 6. Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `APP_ENV` | `development` | `development` или `production` |
| `DATABASE_URL` | `sqlite:///./database.db` | URL БД |
| `LOG_DIR` | `./logs` | каталог логов |
| `LOG_LEVEL` | `INFO` | уровень логирования |
| `APP_TIMEZONE` | `Europe/Moscow` | таймзона планировщика и группировки по датам |
| `ALLOWED_ORIGINS` | `http://localhost:8080,http://127.0.0.1:8080,http://localhost:5500,http://127.0.0.1:5500` | CORS, через запятую |
| `ADMIN_TOKEN` | пусто | токен для `POST /api/admin/parse`; пусто = эндпоинт выключен |
| `HABR_CAREER_URL` | `https://career.habr.com` | базовый URL |
| `HABR_API_PATH` | `/api/frontend/vacancies` | путь JSON-выдачи |
| `HTTP_USER_AGENT` | `JobPulse/1.0 (+https://github.com/siosif963-gif/jobpulse)` | User-Agent (один, без ротации) |
| `REQUEST_TIMEOUT_SECONDS` | `10` | таймаут запроса |
| `REQUEST_DELAY_MIN_SECONDS` | `1.0` | мин. случайная задержка перед запросом |
| `REQUEST_DELAY_MAX_SECONDS` | `3.0` | макс. случайная задержка |
| `MAX_CONCURRENT_REQUESTS` | `2` | одновременных запросов к источнику |
| `MAX_PAGES_PER_QUERY` | `60` | лимит страниц на один запрос |
| `MIN_REPARSE_HOURS` | `20` | не парсить запрос повторно чаще |
| `STALE_AFTER_DAYS` | `7` | вакансия, не встречавшаяся столько дней, становится неактивной |
| `SCHEDULER_ENABLED` | `true` | включать ли планировщик |
| `PARSING_SCHEDULE` | `daily` | `daily` или `interval` |
| `PARSING_DAILY_HOUR` | `3` | час запуска для `daily` (в `APP_TIMEZONE`) |
| `PARSING_INTERVAL_HOURS` | `24` | интервал для `interval` |
| `PARSING_RUN_ON_STARTUP_IF_EMPTY` | `true` | если в БД 0 вакансий — запустить парсинг через 10 с после старта |
| `RETRY_DELAY_MINUTES` | `60` | задержка повтора упавшего запуска |
| `MAX_JOB_RETRIES` | `3` | макс. повторов подряд |
| `DEFAULT_STATS_DAYS` | `30` | окно статистики по умолчанию |

## 7. Расписание

- `PARSING_SCHEDULE=daily` — раз в сутки в `PARSING_DAILY_HOUR`:00 по `APP_TIMEZONE`;
- `PARSING_SCHEDULE=interval` — каждые `PARSING_INTERVAL_HOURS` часов.
- Если запуск завершился `failed`/`blocked` и повтор имеет смысл, он планируется через `RETRY_DELAY_MINUTES`, не более `MAX_JOB_RETRIES` раз подряд.
- **Запускайте только с `--workers 1`**: иначе планировщик стартует в каждом воркере (так уже указано в `Procfile`).

## 8. Поисковые запросы

Управляются только через CLI:

```bash
python cli.py queries list
python cli.py queries add "Rust"
python cli.py queries disable "Java"
python cli.py queries enable "Java"
```

Ключ `__all__` — «весь каталог» (запрос без параметра `q`). Именно по его полному обходу определяется, какие вакансии исчезли из выдачи.

## 9. Ручной запуск через API

```bash
curl -X POST -H "X-Admin-Token: <ваш токен>" "https://<backend>/api/admin/parse?force=false"
```

Ответ `202`; статус смотрите в `/api/health`. Без `ADMIN_TOKEN` эндпоинт всегда отвечает `403`.

## 10. Мониторинг

- `GET /api/health` — статус (`ok` / `degraded` / `no_data`), итоги последнего парсинга, `next_run_at`.
- Логи: `LOG_DIR/app.log` и `LOG_DIR/parsing_errors.log` (ошибки источника, формат `дата | ERROR | query='…' page=N type=… | сообщение`).

## 11. Тесты

```bash
cd backend
pytest
pytest --cov=services --cov=parsers
```

Сеть в тестах не используется (источник подменяется через `httpx.MockTransport`).

## 12. Деплой

**Бэкенд — Railway** (с постоянным диском):

1. Создайте сервис из репозитория, Root Directory — `backend` (запуск берётся из `Procfile`).
2. Подключите **Volume**, например в `/data`.
3. Переменные: `APP_ENV=production`, `DATABASE_URL=sqlite:////data/database.db`, `LOG_DIR=/data/logs`, `ADMIN_TOKEN=<секрет>`, `ALLOWED_ORIGINS=https://<user>.github.io` (origin без пути).
4. Одна реплика и `--workers 1`.

Render free tier **не рекомендуется**: сервис засыпает (планировщик не работает), а диск эфемерный — БД теряется при редеплое.

**Фронтенд — GitHub Pages через Actions:**

1. Settings → Pages → Source: **GitHub Actions**.
2. В `frontend/config.js` замените `https://YOUR-BACKEND.up.railway.app` на адрес вашего бэкенда.
3. Пуш в `main` с изменениями в `frontend/**` запустит `.github/workflows/pages.yml`.

## 13. Ограничения и допущения

- Только один источник — Habr Career; архитектура (`source`, `BaseParser`) позволяет добавить другие, но их парсеры не реализованы.
- Внутренний API Habr может измениться без предупреждения.
- Синонимы технологий («Go» и «Golang») не объединяются; валюты не конвертируются.
- Нет авторизации, уведомлений, миграций (таблицы создаются `create_all`).
- SQLite с одним воркером — рассчитана на небольшую нагрузку.
- Решения по пробелам в ТЗ — в [docs/DECISIONS.md](docs/DECISIONS.md).
