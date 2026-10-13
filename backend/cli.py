"""CLI JobPulse: парсинг, запросы, демо-данные."""
import argparse
import asyncio
import sys

import database
from config import settings
from logging_config import setup_logging
from services import parser_service, query_service
from services.exceptions import NotFoundError


def _prepare() -> None:
    setup_logging()
    database.init_db()
    with database.SessionLocal() as db:
        query_service.seed_initial_queries(db)


def cmd_parse(args) -> int:
    report = asyncio.run(parser_service.run_parsing("cli", force=args.force, max_pages=args.max_pages))
    print(f"Статус: {report.status}")
    print(f"Запросов: всего {report.queries_total}, обработано {report.queries_processed}, пропущено {report.queries_skipped}")
    print(f"Страниц: {report.pages_attempted}, с ошибками {report.pages_failed}")
    print(
        f"Вакансий: увидено {report.vacancies_seen}, добавлено {report.added}, "
        f"обновлено {report.updated}, без изменений {report.unchanged}, деактивировано {report.deactivated}"
    )
    print(f"Ошибок: {report.errors_count}")
    for message in report.error_messages[:10]:
        print(f"  - {message}")
    return 0 if report.status in ("success", "partial", "skipped") else 1


def cmd_queries(args) -> int:
    with database.SessionLocal() as db:
        if args.action == "list":
            print(f"{'keyword':<30} {'is_active':<10} last_parsed_at")
            for q in query_service.list_queries(db):
                print(f"{q.keyword:<30} {str(q.is_active):<10} {q.last_parsed_at or '-'}")
            return 0
        if args.action == "add":
            _query, created = query_service.add_query(db, args.keyword)
            print("Запрос добавлен" if created else "Запрос уже существует (включён)")
            return 0
        try:
            query_service.set_query_active(db, args.keyword, args.action == "enable")
        except NotFoundError as exc:
            print(f"Ошибка: {exc.message}", file=sys.stderr)
            return 1
        print("Запрос включён" if args.action == "enable" else "Запрос отключён")
        return 0


def cmd_seed_demo(args) -> int:
    if settings.APP_ENV != "development":
        print("Ошибка: seed-demo доступна только при APP_ENV=development", file=sys.stderr)
        return 1
    added, updated, unchanged = parser_service.seed_demo(args.count)
    print(f"Демо-вакансии: добавлено {added}, обновлено {updated}, без изменений {unchanged}")
    return 0


def cmd_clear_demo(_args) -> int:
    print(f"Удалено демо-вакансий: {parser_service.clear_demo()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cli.py", description="JobPulse CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse", help="запустить парсинг")
    p_parse.add_argument("--force", action="store_true", help="игнорировать MIN_REPARSE_HOURS")
    p_parse.add_argument("--max-pages", type=int, default=None, help="лимит страниц на запрос")
    p_parse.set_defaults(func=cmd_parse)

    p_queries = sub.add_parser("queries", help="управление поисковыми запросами")
    q_sub = p_queries.add_subparsers(dest="action", required=True)
    q_sub.add_parser("list")
    for name in ("add", "enable", "disable"):
        q_sub.add_parser(name).add_argument("keyword")
    p_queries.set_defaults(func=cmd_queries)

    p_seed = sub.add_parser("seed-demo", help="создать демо-вакансии (только development)")
    p_seed.add_argument("--count", type=int, default=300)
    p_seed.set_defaults(func=cmd_seed_demo)

    p_clear = sub.add_parser("clear-demo", help="удалить демо-вакансии")
    p_clear.set_defaults(func=cmd_clear_demo)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _prepare()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
