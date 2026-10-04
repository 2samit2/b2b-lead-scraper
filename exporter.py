"""Генерация двухстраничного стилизованного отчёта Excel (.xlsx).

Лист 1 «База Лидов»:
    * тёмно-изумрудная шапка с белым текстом;
    * автофильтр, закреплённая верхняя строка;
    * чередование строк, кликабельные ссылки на сайты и email;
    * «Да/Нет»-индикаторы наличия email/мессенджеров.

Лист 2 «Статистика»:
    * сводная таблица (всего собрано, % с сайтом, % с email,
      % с мессенджерами, топ категорий).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional, Sequence

from loguru import logger
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

import config
from models import Lead


# ---------------------------------------------------------------------------
# Стили (создаются один раз)
# ---------------------------------------------------------------------------

def _header_fill() -> PatternFill:
    return PatternFill(start_color=config.EMERALD_DARK, end_color=config.EMERALD_DARK, fill_type="solid")


def _zebra_fill() -> PatternFill:
    return PatternFill(start_color=config.EMERALD_LIGHT, end_color=config.EMERALD_LIGHT, fill_type="solid")


def _soft_fill() -> PatternFill:
    return PatternFill(start_color=config.EMERALD_SOFT, end_color=config.EMERALD_SOFT, fill_type="solid")


_WHITE_BOLD = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
_DARK_TEXT = Font(name="Calibri", size=11, color="1A2E24")
_GRAY_TEXT = Font(name="Calibri", size=10, color=config.GRAY_TEXT)
_LINK_FONT = Font(name="Calibri", size=11, color=config.HYPERLINK_BLUE, underline="single")
_STAT_VALUE_FONT = Font(name="Calibri", size=12, bold=True, color="0B6E4F")

_THIN_GRAY = Side(style="thin", color="B8CFC4")
_CELL_BORDER = Border(left=_THIN_GRAY, right=_THIN_GRAY, top=_THIN_GRAY, bottom=_THIN_GRAY)

_CENTER = Alignment(horizontal="center", vertical="center")
_LEFT_WRAP = Alignment(horizontal="left", vertical="center", wrap_text=True)


# ---------------------------------------------------------------------------
# Лист 1: База Лидов
# ---------------------------------------------------------------------------

LEAD_COLUMNS: tuple[tuple[str, str, int], ...] = (
    # (заголовок, ключ, ширина колонки в символах)
    ("№", "index", 5),
    ("Организация", "name", 38),
    ("Категория", "category", 22),
    ("Адрес", "address", 42),
    ("Телефон", "phone", 18),
    ("Сайт", "website", 30),
    ("Email", "emails", 34),
    ("Telegram", "telegram", 28),
    ("WhatsApp", "whatsapp", 28),
    ("VK", "vk", 28),
    ("Источник", "source", 14),
)


def _lead_row_values(lead: Lead, index: int) -> list:
    emails = "\n".join(lead.contact_info.emails)
    return [
        index,
        lead.name,
        lead.category,
        lead.address or "—",
        lead.phone or "—",
        lead.website or "—",
        emails or "—",
        lead.contact_info.telegram or "—",
        lead.contact_info.whatsapp or "—",
        lead.contact_info.vk or "—",
        lead.source,
    ]


def _apply_hyperlinks(sheet: Worksheet, lead: Lead, row: int) -> None:
    """Делает сайт и email-адреса кликабельными."""
    if lead.website:
        site_cell = sheet.cell(row=row, column=6)
        site_cell.hyperlink = lead.website
        site_cell.font = _LINK_FONT

    emails_cell = sheet.cell(row=row, column=7)
    if lead.contact_info.emails:
        primary = lead.contact_info.emails[0]
        emails_cell.hyperlink = f"mailto:{primary}"
        emails_cell.font = _LINK_FONT

    for column, value in (
        (8, lead.contact_info.telegram),
        (9, lead.contact_info.whatsapp),
        (10, lead.contact_info.vk),
    ):
        if value:
            cell = sheet.cell(row=row, column=column)
            cell.hyperlink = value
            cell.font = _LINK_FONT


def _build_leads_sheet(sheet: Worksheet, leads: Sequence[Lead]) -> None:
    sheet.title = config.SHEET1_NAME
    sheet.sheet_view.showGridLines = False

    # Шапка.
    for col, (title, _, width) in enumerate(LEAD_COLUMNS, start=1):
        letter = get_column_letter(col)
        sheet.column_dimensions[letter].width = width
        cell = sheet.cell(row=1, column=col, value=title)
        cell.font = _WHITE_BOLD
        cell.fill = _header_fill()
        cell.alignment = _CENTER
        cell.border = _CELL_BORDER

    # Закрепление шапки и автофильтр.
    sheet.freeze_panes = "A2"
    last_col_letter = get_column_letter(len(LEAD_COLUMNS))
    sheet.auto_filter.ref = f"A1:{last_col_letter}{max(len(leads), 1) + 1}"

    # Данные.
    for i, lead in enumerate(leads, start=1):
        row = i + 1
        values = _lead_row_values(lead, i)
        for col, value in enumerate(values, start=1):
            cell = sheet.cell(row=row, column=col, value=value)
            cell.font = _DARK_TEXT
            cell.alignment = _LEFT_WRAP
            cell.border = _CELL_BORDER
            if i % 2 == 0:
                cell.fill = _zebra_fill()
        # Номер строки по центру.
        sheet.cell(row=row, column=1).alignment = _CENTER
        sheet.cell(row=row, column=5).alignment = _CENTER
        _apply_hyperlinks(sheet, lead, row)

    # Высота строк — компактная, но с запасом на перенос текста.
    for i in range(len(leads)):
        sheet.row_dimensions[i + 2].height = 22
    sheet.row_dimensions[1].height = 24


# ---------------------------------------------------------------------------
# Лист 2: Статистика
# ---------------------------------------------------------------------------

def _percent(part: int, total: int) -> float:
    return round(part / total * 100, 1) if total else 0.0


def _stat_label_cell(sheet: Worksheet, row: int, text: str) -> None:
    cell = sheet.cell(row=row, column=2, value=text)
    cell.font = _DARK_TEXT
    cell.alignment = _LEFT_WRAP
    cell.fill = _soft_fill()
    cell.border = _CELL_BORDER


def _stat_value_cell(sheet: Worksheet, row: int, value, *, is_percent: bool = False) -> None:
    cell = sheet.cell(row=row, column=3, value=value)
    cell.font = _STAT_VALUE_FONT
    cell.alignment = _CENTER
    cell.border = _CELL_BORDER
    if is_percent:
        cell.number_format = "0.0\"%\""


def _build_stats_sheet(sheet: Worksheet, leads: Sequence[Lead]) -> None:
    sheet.title = config.SHEET2_NAME
    sheet.sheet_view.showGridLines = False
    sheet.column_dimensions["A"].width = 3
    sheet.column_dimensions["B"].width = 44
    sheet.column_dimensions["C"].width = 16
    sheet.column_dimensions["D"].width = 10

    total = len(leads)
    with_website = sum(1 for lead in leads if lead.has_website)
    with_email = sum(1 for lead in leads if lead.has_email)
    with_messengers = sum(1 for lead in leads if lead.has_messengers)
    with_phone = sum(1 for lead in leads if lead.phone)
    enriched_visits = sum(len(lead.contact_info.visited_pages) for lead in leads)

    # Заголовок листа.
    title_cell = sheet.cell(
        row=1, column=2, value="Сводная статистика по базе лидов"
    )
    title_cell.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    title_cell.fill = _header_fill()
    title_cell.alignment = _CENTER
    sheet.merge_cells(start_row=1, start_column=2, end_row=1, end_column=3)
    sheet.cell(row=1, column=3).fill = _header_fill()
    sheet.row_dimensions[1].height = 26

    # Дата отчёта.
    date_cell = sheet.cell(row=2, column=2, value=f"Дата формирования: {date.today().isoformat()}")
    date_cell.font = _GRAY_TEXT

    rows = (
        ("Всего собрано организаций", total, False),
        ("Лидов с сайтом", with_website, False),
        ("Лидов с email", with_email, False),
        ("Лидов с мессенджерами (TG/WA/VK)", with_messengers, False),
        ("Лидов с телефоном", with_phone, False),
        ("% лидов с сайтом", _percent(with_website, total), True),
        ("% лидов с email", _percent(with_email, total), True),
        ("% лидов с мессенджерами", _percent(with_messengers, total), True),
    )

    row = 4
    for label, value, is_percent in rows:
        _stat_label_cell(sheet, row, label)
        _stat_value_cell(sheet, row, value, is_percent=is_percent)
        row += 1

    row += 1
    header = sheet.cell(row=row, column=2, value="Топ-5 категорий")
    header.font = Font(name="Calibri", size=12, bold=True, color="0B6E4F")
    row += 1

    categories: dict[str, int] = {}
    for lead in leads:
        categories[lead.category] = categories.get(lead.category, 0) + 1
    top_categories = sorted(categories.items(), key=lambda item: item[1], reverse=True)[:5]
    for name, count in top_categories:
        _stat_label_cell(sheet, row, name)
        _stat_value_cell(sheet, row, count)
        row += 1

    row += 1
    footer = sheet.cell(
        row=row, column=2,
        value=f"Обогащение: посещено страниц сайтов организаций — {enriched_visits}",
    )
    footer.font = _GRAY_TEXT


# ---------------------------------------------------------------------------
# Публичная точка входа
# ---------------------------------------------------------------------------

def export_to_excel(leads: Sequence[Lead], output_path: Optional[Path] = None) -> Path:
    """Собирает отчёт из двух листов и сохраняет по указанному пути."""
    if output_path is None:
        output_path = config.OUTPUT_DIR / f"leads_{date.today().isoformat()}.xlsx"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()

    leads_sheet = workbook.active
    _build_leads_sheet(leads_sheet, leads)

    stats_sheet = workbook.create_sheet()
    _build_stats_sheet(stats_sheet, leads)

    workbook.save(output_path)
    logger.success(f"Отчёт сохранён: {output_path} ({len(leads)} лидов)")
    return output_path