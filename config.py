"""Конфигурация проекта B2B Lead Scraper & Contact Enricher.

Все настраиваемые параметры (сеть, парсинг, экспорт, стиль отчёта)
собраны в одном месте, чтобы код оставался предсказуемым и легко
изменяемым без правок бизнес-логики.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Пути
# ---------------------------------------------------------------------------

BASE_DIR: Path = Path(__file__).resolve().parent
OUTPUT_DIR: Path = BASE_DIR / "output"
LOGS_DIR: Path = BASE_DIR / "logs"

# ---------------------------------------------------------------------------
# Сеть (httpx / asyncio)
# ---------------------------------------------------------------------------

# Сколько сайтов организаций обходим одновременно (asyncio.Semaphore).
ENRICHMENT_CONCURRENCY: int = 8

# Сколько раз повторяем неудавшийся HTTP-запрос.
HTTP_RETRIES: int = 2

CONNECT_TIMEOUT: float = 10.0   # сек, установка соединения
READ_TIMEOUT: float = 15.0      # сек, ожидание тела ответа

# Максимум внутренних страниц сайта, которые посещает Enricher
# (главная + найденные ссылки на контакты/о компании).
MAX_PAGES_PER_SITE: int = 5

USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Enricher: правила парсинга контактов
# ---------------------------------------------------------------------------

# Куда смотрим в первую очередь, если на главной странице нет ссылок.
CONTACT_PAGE_PATHS: tuple[str, ...] = (
    "/contacts",
    "/contact",
    "/kontakty",
    "/kontakti",
    "/about",
    "/about-us",
    "/o-nas",
    "/o-kompanii",
)

# Подсказки для поиска ссылок на страницы контактов прямо в тексте главной.
CONTACT_LINK_HINTS: tuple[str, ...] = (
    "contact",
    "kontakt",
    "about",
    "o-nas",
    "o-kompanii",
    "обратн",
    "связ",
    "контакт",
    "о нас",
    "о компании",
)

# Регулярное выражение для «сырых» email-адресов.
EMAIL_RE: str = (
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}"
)

# Email/домены-мусор: счётчики метрик, системные ящики, примеры из доков.
EMAIL_JUNK_DOMAINS: tuple[str, ...] = (
    "example.com",
    "example.org",
    "example.net",
    "sentry.io",
    "sentry-next.wixpress.com",
    "wixpress.com",
    "domain.com",
    "yourdomain.com",
    "email.com",
    "test.com",
    "yoursite.com",
    "site.com",
)

EMAIL_JUNK_LOCAL_PARTS: tuple[str, ...] = (
    "example",
    "no-reply",
    "noreply",
    "donotreply",
    "test",
    "user",
    "name",
    "email",
    "your",
    "youremail",
    "e-mail",
)

# Расширения, которые чаще всего выдаёт регулярка по тексту страницы,
# когда email на самом деле является именем картинки.
IMAGE_EXTENSIONS: tuple[str, ...] = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".bmp",
    ".tiff",
)

# ---------------------------------------------------------------------------
# Скрейсер источников данных
# ---------------------------------------------------------------------------

# Демо-источник (моки, без сети).
DEMO_SOURCE_NAME: str = "demo-catalog"

# Реальный открытый источник: каталог организаций OpenStreetMap.
OSM_SOURCE_NAME: str = "openstreetmap"

NOMINATIM_SEARCH_URL: str = "https://nominatim.openstreetmap.org/search"
OVERPASS_API_URL: str = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT_SEC: int = 60
# Радиус поиска организаций вокруг центра города, метры.
CITY_SEARCH_RADIUS_M: int = 15000

# ---------------------------------------------------------------------------
# Экспорт в Excel: стиль отчёта
# ---------------------------------------------------------------------------

SHEET1_NAME: str = "База Лидов"
SHEET2_NAME: str = "Статистика"

EMERALD_DARK: str = "0B6E4F"      # тёмно-изумрудная шапка таблицы
EMERALD_LIGHT: str = "E8F3EE"     # чередование строк (зебра)
EMERALD_SOFT: str = "C8E6D9"      # акцентные ячейки статистики
GRAY_TEXT: str = "546E62"         # второстепенный текст
HYPERLINK_BLUE: str = "0B5ED7"    # цвет ссылок на сайты