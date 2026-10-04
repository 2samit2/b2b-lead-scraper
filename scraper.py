"""Сбор организаций из источников данных.

Архитектура:
    BaseScraper — абстрактный контракт: поиск по ключевому слову и городу.
    DemoScraper — детерминированный мок-источник для режима ``--demo``.
    OsmScraper  — открытый каталог OpenStreetMap (Overpass API + Nominatim).
    get_scraper — фабрика по имени источника.

Режим ``--demo`` не обращается в сеть вовсе, поэтому проект можно
запускать и проверять без риска блокировок со стороны внешних сервисов.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Optional, Sequence

import httpx
from loguru import logger
from pydantic import ValidationError

import config
from models import Lead


# ---------------------------------------------------------------------------
# Базовый класс
# ---------------------------------------------------------------------------

class BaseScraper(ABC):
    """Контракт источника данных об организациях.

    Любой новый источник (2GIS, Yandex Maps, каталог услуг и т.п.)
    реализует :meth:`search` и возвращает список :class:`Lead`.
    """

    name: str = "base"

    @abstractmethod
    async def search(
        self,
        query: str,
        city: Optional[str] = None,
        limit: int = 30,
    ) -> list[Lead]:
        """Ищет организации по ключевому слову ``query`` в городе ``city``."""

    async def close(self) -> None:
        """Освобождает ресурсы (по умолчанию не требуется)."""


# ---------------------------------------------------------------------------
# Демонстрационный источник (моки)
# ---------------------------------------------------------------------------

# Категории, из которых собираются демо-организации.
_DEMO_CATEGORIES: tuple[tuple[str, ...], ...] = (
    ("Автосервис", "Ремонт ходовой части", "Замена масла", "Шиномонтаж"),
    ("Стоматология", "Протезирование", "Имплантация", "Гигиена полости рта"),
    ("Юридическая фирма", "Регистрация ООО", "Банкротство", "Сопровождение сделок"),
    ("Строительная компания", "Капитальный ремонт", "Отделочные работы", "Кладка"),
    ("Турфирма", "Пляжный отдых", "Экскурсионные туры", "Визовая поддержка"),
)
_DEMO_CITIES: tuple[str, ...] = ("Казань", "Москва", "Санкт-Петербург")
_DEMO_BRANDS: tuple[str, ...] = (
    "ПроРемонт-Авто", "Дентал Смайл", "ЮрКонсульт",
    "СтройМастер", "Санни Турс", "Мега-Сервис", "ЭкспертПрофи",
    "Вектор-Люкс", "Альфа-Плюс", "Оникс-Групп",
)
_DEMO_STREETS: tuple[str, ...] = (
    "ул. Победы", "пр. Мира", "ул. Ленина", "ул. Гагарина", "ул. Строителей",
)

# Шаблоны демо-сайтов: host + HTML страниц, которые «отдаёт» демо-транспорт.
# Сайты специально разные: где-то есть email и VK на странице контактов,
# где-то только мессенджеры, где-то картинка с именем, похожим на email.
_DEMO_SITES: tuple[dict, ...] = (
    {
        "host": "proremont-auto.ru",
        "pages": {
            "/": (
                '<!DOCTYPE html><html><head><title>ПроРемонт-Авто</title></head><body>'
                '<a href="/contacts">Контакты</a>'
                '<a href="https://t.me/proremont_auto">Telegram</a>'
                '<a href="https://wa.me/79991234567">WhatsApp</a>'
                '<footer>Сервис и диагностика</footer></body></html>'
            ),
            "/contacts": (
                '<!DOCTYPE html><html><head><title>Контакты</title></head><body>'
                '<h1>Наши контакты</h1>'
                '<p>Пишите: info@proremont-auto.ru, service@proremont-auto.ru</p>'
                '<p>Тел: +7 (843) 233-44-55</p>'
                '<a href="https://vk.com/proremont_auto">Мы в VK</a>'
                '<img src="/static/logo.png" alt="logo">'
                '</body></html>'
            ),
        },
    },
    {
        "host": "dental-smile24.ru",
        "pages": {
            "/": (
                '<!DOCTYPE html><html><head><title>Dental Smile</title></head><body>'
                '<a href="/about">О клинике</a>'
                '<a href="https://vk.com/dental_smile24">VK</a>'
                '<a href="https://t.me/dental_smile24_bot">Telegram</a>'
                '</body></html>'
            ),
            "/about": (
                '<!DOCTYPE html><html><head><title>О клинике</title></head><body>'
                '<p>Приём и консультации: info@dental-smile24.ru</p>'
                '<p>Телефоны регистратуры: 8 (843) 511-55-66, +7 999 000 11 22</p>'
                '<a href="https://wa.me/79990001122">Записаться в WhatsApp</a>'
                '</body></html>'
            ),
        },
    },
    {
        "host": "yur-consult.ru",
        "pages": {
            "/": (
                '<!DOCTYPE html><html><head><title>ЮрКонсульт</title></head><body>'
                '<a href="/kontakty">Контакты</a>'
                '<a href="https://t.me/yur_consult">Telegram</a>'
                '</body></html>'
            ),
            "/kontakty": (
                '<!DOCTYPE html><html><head><title>Контакты</title></head><body>'
                '<p>Почта: office@yur-consult.ru</p>'
                '<a href="https://ok.ru/yurconsult">Одноклассники</a>'
                '</body></html>'
            ),
        },
    },
    {
        "host": "stroy-master.su",
        "pages": {
            "/": (
                '<!DOCTYPE html><html><head><title>СтройМастер</title></head><body>'
                '<h1>Строим дома под ключ</h1>'
                '<p>Заявки: zakaz@stroy-master.su</p>'
                '<a href="https://wa.me/79001234567">WhatsApp</a>'
                '<img src="banner.jpg" alt="banner">'
                '</body></html>'
            ),
        },
    },
    {
        "host": "sunny-tours.com",
        "pages": {
            "/": (
                '<!DOCTYPE html><html><head><title>Sunny Tours</title></head><body>'
                '<a href="https://vk.com/sunny_tours">VK</a>'
                '<a href="https://t.me/sunny_tours">Telegram</a>'
                '</body></html>'
            ),
        },
    },
)

# Реестр демо-сайтов: используется демо-транспортом в enricher.py.
_DEMO_SITE_STORE: dict[str, dict] = {site["host"]: site for site in _DEMO_SITES}


def get_demo_site_store() -> dict[str, dict]:
    """Возвращает реестр демо-сайтов для подмены HTTP-транспорта."""
    return _DEMO_SITE_STORE


class DemoScraper(BaseScraper):
    """Детерминированный источник данных без обращения к сети."""

    name = config.DEMO_SOURCE_NAME

    async def search(
        self,
        query: str,
        city: Optional[str] = None,
        limit: int = 30,
    ) -> list[Lead]:
        """Генерирует стабильный набор организаций на основе запроса.

        Данные строятся из хеша (query, city, limit), поэтому при повторном
        запуске одной и той же команды отчёт воспроизводится идентично —
        удобно для отладки и демонстрации заказчику.
        """
        city = city or "Казань"
        seed = int(
            hashlib.sha256(f"{query}|{city}|{limit}".encode("utf-8")).hexdigest()[:8],
            16,
        )

        leads: list[Lead] = []
        for i in range(limit):
            category_block = _DEMO_CATEGORIES[i % len(_DEMO_CATEGORIES)]
            site = _DEMO_SITES[i % len(_DEMO_SITES)]
            street = _DEMO_STREETS[(i + seed) % len(_DEMO_STREETS)]
            building = 10 + (seed + i) % 90
            phone_digits = 79990000000 + ((seed + i) % 10_000_000)

            category = category_block[0]
            brand = _DEMO_BRANDS[(i + seed) % len(_DEMO_BRANDS)]
            name = f"{category} «{brand}»"
            address = f"{city}, {street}, д. {building}"
            website = f"https://{site['host']}"

            try:
                leads.append(
                    Lead(
                        name=name,
                        category=category,
                        address=address,
                        phone=f"+{phone_digits}",
                        website=website,
                        source=self.name,
                    )
                )
            except ValidationError as exc:
                logger.warning(f"[demo] Пропущена запись {i + 1}: {exc}")

        logger.info(f"[demo] Сгенерировано {len(leads)} организаций по запросу «{query}» (город {city})")
        return leads


# ---------------------------------------------------------------------------
# Реальный источник: OpenStreetMap (Overpass API)
# ---------------------------------------------------------------------------

class OsmScraper(BaseScraper):
    """Сбор организаций из открытой базы OpenStreetMap через Overpass API.

    Overpass — официальный публичный API OSM, свободный для умеренного
    использования. Схема: город геокодируется через Nominatim, затем вокруг
    его центра запрашиваются POI (points of interest), у которых в тегах
    есть имя и желательно телефон/сайт.
    """

    name = config.OSM_SOURCE_NAME

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(
                config.OVERPASS_TIMEOUT_SEC,
                connect=config.CONNECT_TIMEOUT,
            )
            self._client = httpx.AsyncClient(
                timeout=timeout,
                headers={"User-Agent": f"{config.USER_AGENT} b2b-lead-scraper/1.0"},
                follow_redirects=True,
            )
        return self._client

    async def _geocode_city(self, city: str) -> tuple[float, float]:
        """Возвращает (lat, lon) центра города через Nominatim."""
        client = await self._get_client()
        params = {
            "q": city,
            "format": "json",
            "limit": 1,
            "accept-language": "ru",
        }
        response = await client.get(config.NOMINATIM_SEARCH_URL, params=params)
        response.raise_for_status()
        data = response.json()
        if not data:
            raise RuntimeError(f"Город «{city}» не найден в Nominatim")
        first = data[0]
        return float(first["lat"]), float(first["lon"])

    async def search(
        self,
        query: str,
        city: Optional[str] = None,
        limit: int = 30,
    ) -> list[Lead]:
        if not city:
            raise ValueError("Для источника openstreetmap укажите --city")

        client = await self._get_client()
        lat, lon = await self._geocode_city(city)
        radius = config.CITY_SEARCH_RADIUS_M
        around = f"(around:{radius},{lat},{lon})"

        # Ищем POI с именем, содержащим запрос. Приоритет отдаётся объектам,
        # у которых уже есть теги телефона, email или сайта: такие карточки
        # сразу дают полезные лиды даже без последующего обогащения.
        overpass_query = f"""
[out:json][timeout:{config.OVERPASS_TIMEOUT_SEC}];
(
  nwr["name"~"{query}",i]["phone"~".",i]{around};
  nwr["name"~"{query}",i]["website"~".",i]{around};
  nwr["name"~"{query}",i]["contact:phone"~".",i]{around};
  nwr["name"~"{query}",i]["contact:email"~".",i]{around};
  nwr["name"~"{query}",i]{around};
);
out center tags {limit};
"""

        logger.info(
            f"[osm] Запрос к Overpass API: «{query}» в {city} "
            f"(центр {lat:.4f}, {lon:.4f}, радиус {radius} м)"
        )
        response = await client.post(
            config.OVERPASS_API_URL,
            data={"data": overpass_query},
        )
        response.raise_for_status()
        data = response.json()

        elements = data.get("elements", [])
        logger.info(f"[osm] Overpass вернул {len(elements)} объектов")
        return self._elements_to_leads(elements, limit)

    def _elements_to_leads(
        self,
        elements: Sequence[dict],
        limit: int,
    ) -> list[Lead]:
        leads: list[Lead] = []
        seen_names: set[str] = set()
        for element in elements:
            if len(leads) >= limit:
                break
            tags = element.get("tags", {})
            name = tags.get("name")
            if not name or name in seen_names:
                continue
            seen_names.add(name)

            category = (
                tags.get("shop")
                or tags.get("amenity")
                or tags.get("office")
                or tags.get("craft")
                or tags.get("healthcare")
                or tags.get("tourism")
                or tags.get("leisure")
                or "Организация"
            )

            address_parts = [
                tags.get("addr:city") or tags.get("addr:town"),
                tags.get("addr:street"),
                tags.get("addr:housenumber"),
            ]
            address = ", ".join(p for p in address_parts if p) or None

            phones = [
                tags.get(key)
                for key in ("phone", "contact:phone", "contact:mobile")
                if tags.get(key)
            ]
            phone = phones[0] if phones else None

            website = (
                tags.get("website")
                or tags.get("contact:website")
                or tags.get("url")
            )

            try:
                lead = Lead(
                    name=name,
                    category=category,
                    address=address,
                    phone=phone,
                    website=website,
                    source=self.name,
                )
                leads.append(lead)
            except ValidationError as exc:
                logger.warning(f"[osm] Пропущен объект с невалидными данными: {exc}")
        return leads

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# ---------------------------------------------------------------------------
# Фабрика
# ---------------------------------------------------------------------------

def get_scraper(source_name: str) -> BaseScraper:
    """Возвращает скрейсер по имени источника из CLI."""
    scrapers: dict[str, type[BaseScraper]] = {
        config.DEMO_SOURCE_NAME: DemoScraper,
        config.OSM_SOURCE_NAME: OsmScraper,
    }
    try:
        return scrapers[source_name]()
    except KeyError as exc:
        raise ValueError(
            f"Неизвестный источник «{source_name}». Доступны: "
            + ", ".join(sorted(scrapers))
        ) from exc