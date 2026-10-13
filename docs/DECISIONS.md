# Решения по пробелам в ТЗ

- [3.2] Корень репозитория — каталог проекта (содержит `backend/`, `frontend/`, `docs/`), отдельная папка `jobpulse/` не создаётся — так проще для пользователя.
- [17, этап 1] В ТЗ указано «все 8 таблиц», но описано 7: vacancies, technologies, vacancy_technologies, vacancy_cities, vacancy_salary_history, search_queries, parsing_runs. Создано 7 — восьмой таблицы в спецификации нет.
- [11.1] Общие фильтры (`apply_common_filters`) размещены в `services/vacancy_service.py` и импортируются в `stats_service.py` — структура файлов в ТЗ не допускает отдельного модуля.
- [9] Генерация/удаление демо-вакансий (`seed_demo`, `clear_demo`) вынесена в `services/parser_service.py`, так как CLI по 3.1 вызывает только `parser_service` и `query_service`.
- [12.8] Данные `is_parsing_now`, `scheduler_running`, `next_run_at` собираются в роутере health (из `parser_service` и `scheduler`) и передаются в `health_service.get_health` — сервисы не импортируют планировщик.
- [10] `run_parsing_job(trigger, force=False)` получил необязательный параметр `force`, чтобы ручной запуск учитывал `force` (12.7).
- [7.3] `QueryResult.complete = False`, если `total_pages == 0`: пустая выдача не считается полным обходом и не деактивирует вакансии.
- [7.3/8.3] «Первая страница получена» определяется как `pages_attempted > pages_failed`.
- [7.4] Запасной разбор `salary.formatted` применяется, только если `salary.from` и `salary.to` оба `null` (раздел 7.2), а не при любой невалидной границе.
- [8.4] «Кэш технологий» живёт в рамках одной транзакции сохранения (пачка вакансий одного запроса): технологии загружаются одним запросом и создаются недостающие.
- [11.2] Порядок `tech_stack` и `cities` в API — по `id` записей (порядок вставки).
- [12.2] Ответы 404/405 на неизвестные пути приведены к единому формату ошибок.
- [12.7] Неверный токен выбрасывает внутреннее `ForbiddenError`, превращаемое в 403 общим обработчиком.
- [вне ТЗ, по просьбе пользователя] Режим статичного снимка: `cli.py export-snapshot` выгружает вакансии в `frontend/data/snapshot.json`, а при `API_BASE_URL = null` (или `?static=1`) фронтенд считает статистику в браузере (`static-stats.js`). Нужен, чтобы сайт на GitHub Pages работал без платного бэкенда. Окно «days» отсчитывается от даты снимка, а не от текущего времени.
- [9] `export-snapshot` вызывает `vacancy_service.export_snapshot` напрямую (CLI читает данные, а не парсит).
