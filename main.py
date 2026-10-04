"""CLI-точка входа B2B Lead Scraper & Contact Enricher.

Примеры запуска:
    python main.py --demo
    python main.py --query "Автосервис" --city "Казань" --limit 30 --enrich
    python main.py --query "Стоматология" --city "Москва" --limit 20 --enrich \
        --output output/dentists.xlsx
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

from loguru import logger

import config
from enricher import Enricher
from exporter import export_to_excel
from models import Lead
from scraper import get_scraper


# ---------------------------------------------------------------------------
# Логирование
# ---------------------------------------------------------------------------

def setup_logging(verbose: bool) -> None:
    """Настраивает loguru: консоль + файл с ротацией."""
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(
        sys.stderr,
        level="DEBUG" if verbose else "INFO",
        format=(
            "<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )
    logger.add(
        config.LOGS_DIR / "scraper_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="b2b-lead-scraper",
        description=(
            "B2B Lead Scraper & Contact Enricher — сбор организаций, "
            "обогащение контактами с их сайтов и выгрузка в Excel."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--query", "-q",
        default="Автосервис",
        help="Ключевое слово для поиска организаций",
    )
    parser.add_argument(
        "--city", "-c",
        default="Казань",
        help="Город поиска",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int, default=30,
        help="Максимум организаций в выборке",
    )
    parser.add_argument(
        "--enrich", "-e",
        action="store_true",
        help="Обогащать лидов (обход сайтов: email, мессенджеры)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Демо-режим: моковые данные, без обращения к сети",
    )
    parser.add_argument(
        "--source", "-s",
        default=None,
        choices=[config.DEMO_SOURCE_NAME, config.OSM_SOURCE_NAME],
        help="Источник данных",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Путь сохранения отчёта (по умолчанию output/leads_YYYY-MM-DD.xlsx)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Подробный вывод (DEBUG)",
    )
    return parser


def default_output_path() -> Path:
    return config.OUTPUT_DIR / f"leads_{date.today().isoformat()}.xlsx"


# ---------------------------------------------------------------------------
# Пайплайн
# ---------------------------------------------------------------------------

async def run(args: argparse.Namespace) -> Path:
    # 1. Выбор источника.
    source_name = args.source
    if source_name is None:
        source_name = config.DEMO_SOURCE_NAME if args.demo else config.OSM_SOURCE_NAME

    if args.demo and source_name == config.OSM_SOURCE_NAME:
        logger.warning("--demo активен: источник переключён на demo-catalog")
        source_name = config.DEMO_SOURCE_NAME

    logger.info(
        f"Старт: query=«{args.query}», city=«{args.city}», "
        f"limit={args.limit}, enrich={args.enrich}, source={source_name}"
    )

    # 2. Сбор организаций.
    scraper = get_scraper(source_name)
    try:
        leads: list[Lead] = await scraper.search(args.query, args.city, args.limit)
    finally:
        await scraper.close()

    if not leads:
        logger.warning("Ничего не найдено — отчёт не будет сформирован")
        return Path()

    logger.info(f"Собрано организаций: {len(leads)}")

    # 3. Обогащение.
    if args.enrich:
        enricher = Enricher(demo=args.demo)
        try:
            leads = await enricher.enrich_all(leads)
        finally:
            await enricher.close()

    # 4. Экспорт.
    output_path = Path(args.output) if args.output else default_output_path()
    report_path = export_to_excel(leads, output_path)

    # 5. Краткий итог в консоль.
    with_email = sum(1 for lead in leads if lead.has_email)
    with_messengers = sum(1 for lead in leads if lead.has_messengers)
    with_website = sum(1 for lead in leads if lead.has_website)
    total = len(leads)
    logger.info(
        f"Итог: {total} лидов | с сайтом: {with_website} | "
        f"с email: {with_email} | с мессенджерами: {with_messengers}"
    )
    return report_path


def main() -> None:
    args = build_parser().parse_args()
    setup_logging(args.verbose)

    try:
        report_path = asyncio.run(run(args))
    except KeyboardInterrupt:
        logger.warning("Остановлено пользователем (Ctrl+C)")
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 — финальный перехват с понятным сообщением
        logger.error(f"Сбой пайплайна: {type(exc).__name__}: {exc}")
        if args.verbose:
            raise
        sys.exit(1)

    if report_path and str(report_path) != ".":
        logger.success(f"Готово! Отчёт: {report_path.resolve()}")


if __name__ == "__main__":
    main()