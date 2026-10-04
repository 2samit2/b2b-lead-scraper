"""Обогащение лидов: асинхронный обход сайтов организаций.

Для каждого лида с найденным сайтом Enricher:
    1. Загружает главную страницу.
    2. Ищет на ней ссылки на страницы контактов/о компании
       (/contacts, /about и т.п.) и посещает их.
    3. Парсит email-адреса (с отсевом мусора: картинки .png/.jpg,
       системные и примерные ящики) и ссылки на мессенджеры
       (Telegram, WhatsApp, VK).

Конкурентность ограничена ``config.ENRICHMENT_CONCURRENCY`` через
``asyncio.Semaphore``. В демо-режиме HTTP-транспорт подменяется
локальными моками — сеть не используется.
"""

from __future__ import annotations

import asyncio
import re
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from loguru import logger

import config
from models import ContactInfo, Lead, extract_domain
from scraper import get_demo_site_store


# ---------------------------------------------------------------------------
# Компилированные регулярные выражения
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(config.EMAIL_RE)
_PHONE_IN_TEXT_RE = re.compile(r"\+?\d[\d\s\-\(\)]{8,17}\d")

# Мусорные слова, которые часто совпадают с TG-паттерном в тексте страниц.
_TG_JUNK = {
    "twitter", "facebook", "instagram", "youtube", "sitemap", "index",
    "login", "admin", "yandex", "google", "github", "mailto", "skype",
}


# ---------------------------------------------------------------------------
# Утилиты извлечения контактов из HTML
# ---------------------------------------------------------------------------

def is_junk_email(email: str) -> bool:
    """True, если email — мусор: картинка, пример из документации и т.п."""
    email = email.lower().strip().strip(".")
    local, _, domain = email.partition("@")

    # 1. Регулярка зацепила имя файла картинки: logo@2x.png, banner.jpg...
    if any(local.endswith(ext) for ext in config.IMAGE_EXTENSIONS):
        return True
    if any(domain.endswith(ext) for ext in config.IMAGE_EXTENSIONS):
        return True

    # 2. Домены-примеров и системные адреса.
    if domain in config.EMAIL_JUNK_DOMAINS:
        return True
    if local in config.EMAIL_JUNK_LOCAL_PARTS:
        return True
    if local.startswith("no-reply") or local.startswith("noreply"):
        return True

    return False


def extract_emails(html: str) -> list[str]:
    """Собирает и валидирует email-адреса из HTML-кода страницы."""
    found: list[str] = []
    for raw in _EMAIL_RE.findall(html):
        email = raw.lower().strip().strip(".")
        if is_junk_email(email):
            logger.debug(f"Отсеян мусорный email: {raw}")
            continue
        if email not in found:
            found.append(email)
    return found


def _clean_messenger_url(url: str) -> str:
    """Приводит найденную ссылку к каноническому виду."""
    url = url.strip()
    if url.startswith("tg://"):
        return url
    return url.rstrip("/")


def extract_messengers(html: str, base_url: str) -> dict[str, Optional[str]]:
    """Ищет ссылки на Telegram, WhatsApp и VK в HTML страницы.

    Возвращает словарь вида ``{"telegram": ..., "whatsapp": ..., "vk": ...}``,
    где значения — URL или ``None``.
    """
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, Optional[str]] = {"telegram": None, "whatsapp": None, "vk": None}

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        lowered = href.lower()
        absolute = urljoin(base_url, href)

        # --- Telegram ---------------------------------------------------
        if result["telegram"] is None:
            if lowered.startswith("tg:") or "t.me/" in lowered:
                if lowered.startswith("tg:"):
                    result["telegram"] = href
                else:
                    # Проверим, что после t.me/ идёт валидный username.
                    path = urlparse(absolute).path.lstrip("/")
                    username = path.split("/")[0] if path else ""
                    if username and username not in _TG_JUNK and username != "share":
                        result["telegram"] = _clean_messenger_url(absolute)

        # --- WhatsApp ---------------------------------------------------
        if result["whatsapp"] is None:
            if lowered.startswith(("https://wa.me/", "http://wa.me/")) or \
                    lowered.startswith("whatsapp://") or "api.whatsapp.com" in lowered:
                phone = urlparse(absolute).path.lstrip("/").split("/")[0]
                digits = re.sub(r"\D", "", phone)
                if digits.startswith("8") and len(digits) == 11:
                    digits = "7" + digits[1:]
                if 11 <= len(digits) <= 15:
                    result["whatsapp"] = f"https://wa.me/{digits}"

        # --- VK ---------------------------------------------------------
        if result["vk"] is None:
            host = urlparse(absolute).netloc.lower()
            if host in {"vk.com", "www.vk.com", "m.vk.com", "vkontakte.ru", "www.vkontakte.ru"}:
                path = urlparse(absolute).path.lstrip("/")
                slug = path.split("/")[0] if path else ""
                if slug and slug not in {"share", "login", "away"}:
                    result["vk"] = f"https://vk.com/{slug}"

    return result


def find_contact_links(html: str, base_url: str) -> list[str]:
    """Ищет на странице внутренние ссылки на страницы контактов/о компании."""
    soup = BeautifulSoup(html, "html.parser")
    base_domain = extract_domain(base_url)
    links: list[str] = []

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urljoin(base_url, href)
        if extract_domain(absolute) != base_domain:
            continue  # внешние ссылки не интересуют
        text = (tag.get_text() or "").strip().lower()
        href_lower = href.lower()
        hint = any(h in text or h in href_lower for h in config.CONTACT_LINK_HINTS)
        if hint and absolute not in links:
            links.append(absolute)

    return links


def extract_phones_from_text(text: str) -> list[str]:
    """Ищет телефоны в тексте страницы (запасной источник для лида)."""
    from models import normalize_phone  # локальный импорт во избежание циклов

    phones: list[str] = []
    for raw in _PHONE_IN_TEXT_RE.findall(text):
        normalized = normalize_phone(raw)
        if normalized and normalized not in phones:
            phones.append(normalized)
    return phones


# ---------------------------------------------------------------------------
# HTTP-транспорт (реальный и демо)
# ---------------------------------------------------------------------------

class FetchResult:
    """Результат загрузки страницы: HTML или причина отказа."""

    __slots__ = ("url", "html", "error")

    def __init__(self, url: str, html: Optional[str] = None, error: Optional[str] = None):
        self.url = url
        self.html = html
        self.error = error

    @property
    def ok(self) -> bool:
        return self.html is not None


class DemoTransport:
    """Транспорт для демо-режима: отдаёт HTML из локального реестра."""

    async def fetch(self, url: str) -> FetchResult:
        await asyncio.sleep(0.05)  # имитация сетевой задержки
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path or "/"

        store = get_demo_site_store()
        site = store.get(host)
        if site is None:
            return FetchResult(url, error="not found (demo)")

        pages = site["pages"]
        if path in pages:
            return FetchResult(url, html=pages[path])
        # Неизвестные пути считаем 404 — так демо ведёт себя как реальный сайт.
        return FetchResult(url, error=f"404 (demo): {path}")

    async def close(self) -> None:
        return None


class HttpTransport:
    """Реальный httpx-транспорт с таймаутами и повторами."""

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(
                config.READ_TIMEOUT,
                connect=config.CONNECT_TIMEOUT,
            )
            self._client = httpx.AsyncClient(
                timeout=timeout,
                headers={
                    "User-Agent": config.USER_AGENT,
                    "Accept-Language": "ru,en;q=0.9",
                },
                follow_redirects=True,
            )
        return self._client

    async def fetch(self, url: str) -> FetchResult:
        client = await self._get_client()
        last_error: Optional[str] = None

        for attempt in range(config.HTTP_RETRIES + 1):
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    return FetchResult(url, html=response.text)
                last_error = f"HTTP {response.status_code}"
                if response.status_code < 500:
                    break  # 4xx повторять бессмысленно
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"

            if attempt < config.HTTP_RETRIES:
                await asyncio.sleep(0.5 * (attempt + 1))

        return FetchResult(url, error=last_error or "unknown error")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# ---------------------------------------------------------------------------
# Enricher
# ---------------------------------------------------------------------------

class Enricher:
    """Асинхронное обогащение лидов контактами с их сайтов."""

    def __init__(self, demo: bool = False) -> None:
        self._transport = DemoTransport() if demo else HttpTransport()
        self._semaphore = asyncio.Semaphore(config.ENRICHMENT_CONCURRENCY)

    async def enrich_lead(self, lead: Lead) -> Lead:
        """Обходит сайт организации и заполняет ``lead.contact_info``."""
        if not lead.website:
            logger.debug(f"«{lead.name}»: сайта нет, обогащение пропущено")
            return lead

        base_url = lead.website
        domain = extract_domain(base_url)
        contact = ContactInfo()

        # Очередь страниц: главная + типовые пути контактов.
        queue: list[str] = [base_url]
        visited: set[str] = set()

        # Сначала пробуем главную, чтобы найти реальные ссылки на контакты.
        first = await self._fetch_page(base_url)
        if first is not None:
            visited.add(base_url)
            contact.visited_pages.append(base_url)
            self._collect_contacts(first, base_url, contact)

            # Ссылки на страницы контактов с главной имеют приоритет.
            for link in find_contact_links(first, base_url):
                if link not in queue:
                    queue.append(link)

        # Добавляем типовые пути, если ссылок найдено мало.
        if len(queue) <= 2:
            for path in config.CONTACT_PAGE_PATHS:
                candidate = urljoin(base_url, path)
                if candidate not in queue:
                    queue.append(candidate)

        for url in queue:
            if url in visited:
                continue
            if len(visited) >= config.MAX_PAGES_PER_SITE:
                break

            page = await self._fetch_page(url)
            if page is None:
                continue
            visited.add(url)
            contact.visited_pages.append(url)
            self._collect_contacts(page, url, contact)

        # Итоги.
        if contact.is_empty:
            logger.warning(f"[{domain}] Контакты не найдены "
                           f"(просмотрено {len(contact.visited_pages)} стр.)")
        else:
            found = ", ".join(
                [f"{len(contact.emails)} email"] + contact.messengers
            )
            logger.success(f"[{domain}] Найдено: {found}")

        lead.contact_info = contact
        return lead

    async def enrich_all(self, leads: Iterable[Lead]) -> list[Lead]:
        """Обогащает лиды параллельно с ограничением конкурентности."""
        lead_list = list(leads)
        with_website = [lead for lead in lead_list if lead.website]
        logger.info(
            f"Обогащение: {len(with_website)} из {len(lead_list)} лидов имеют сайт"
        )

        async def worker(lead: Lead) -> Lead:
            async with self._semaphore:
                try:
                    return await self.enrich_lead(lead)
                except Exception as exc:  # noqa: BLE001 — обогащение не должно ронять пайплайн
                    logger.error(f"Ошибка обогащения «{lead.name}»: {exc}")
                    return lead

        enriched = await asyncio.gather(*(worker(lead) for lead in lead_list))
        return list(enriched)

    async def close(self) -> None:
        await self._transport.close()

    # -- внутренние ------------------------------------------------------

    async def _fetch_page(self, url: str) -> Optional[str]:
        try:
            result = await self._transport.fetch(url)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Сбой запроса {url}: {exc}")
            return None

        if not result.ok:
            logger.debug(f"Не получена страница {url}: {result.error}")
            return None
        return result.html

    def _collect_contacts(self, html: str, page_url: str, contact: ContactInfo) -> None:
        """Извлекает email и мессенджеры из HTML, аккумулируя в contact."""
        for email in extract_emails(html):
            if email not in contact.emails:
                contact.emails.append(email)

        messengers = extract_messengers(html, page_url)
        for key in ("telegram", "whatsapp", "vk"):
            if messengers[key] and getattr(contact, key) is None:
                setattr(contact, key, messengers[key])

        # Телефоны со страницы контактов могут дополнить пустой телефон лида.
        if not contact.emails and not any(
            getattr(contact, key) for key in ("telegram", "whatsapp", "vk")
        ):
            phones = extract_phones_from_text(BeautifulSoup(html, "html.parser").get_text())
            if phones:
                logger.debug(f"[{page_url}] Найдены телефоны в тексте: {phones[:2]}")