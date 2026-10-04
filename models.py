"""Pydantic-модели данных проекта.

ContactInfo — обогащённые контакты, найденные на сайте организации.
Lead       — карточка организации целиком (данные каталога + контакты).
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Валидация и нормализация значений
# ---------------------------------------------------------------------------

_PHONE_DIGITS_RE = re.compile(r"\D+")


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """Приводит телефон к формату ``+7XXXXXXXXXX`` (Россия) или ``+<код>...``.

    Правила:
      * убираются все символы, кроме цифр и ведущего ``+``;
      * 8XXXXXXXXXX (11 цифр) и 10 цифр без кода страны
        приводятся к +7XXXXXXXXXX;
      * некорректные последовательности (слишком короткие/длинные)
        отбрасываются (``None``).
    """
    if not raw:
        return None

    cleaned = _PHONE_DIGITS_RE.sub("", str(raw))
    if not cleaned:
        return None

    # Номера с кодом страны.
    if len(cleaned) == 11 and cleaned.startswith("8"):
        cleaned = "7" + cleaned[1:]
    elif len(cleaned) == 10:
        # 10 цифр — формат без кода страны, считаем российским номером.
        cleaned = "7" + cleaned

    if len(cleaned) == 11 and cleaned.startswith("7"):
        return f"+{cleaned}"

    # Международный формат, не РФ (например, 998... Узбекистан).
    if 11 <= len(cleaned) <= 15 and not cleaned.startswith("0"):
        return f"+{cleaned}"

    return None


def normalize_website(raw: Optional[str]) -> Optional[str]:
    """Оставляет от URL только ``https://host`` (без www, пути, схемы http)."""
    if not raw:
        return None

    value = str(raw).strip().rstrip("/")
    if not value or value.lower() in {"http://", "https://", "www"}:
        return None
    if not value.lower().startswith(("http://", "https://")):
        value = "https://" + value

    host = value.split("//", 1)[1]
    host = host.split("/", 1)[0]
    if host.lower().startswith("www."):
        host = host[4:]
    host = host.strip(".")

    return f"https://{host}" if host else None


def extract_domain(url: str) -> str:
    """Возвращает домен URL без схемы и www."""
    host = url.split("//", 1)[-1].split("/", 1)[0]
    if host.lower().startswith("www."):
        host = host[4:]
    return host


# ---------------------------------------------------------------------------
# Модели
# ---------------------------------------------------------------------------

class ContactInfo(BaseModel):
    """Контакты, найденные на сайте организации."""

    emails: list[str] = Field(default_factory=list)
    telegram: Optional[str] = None
    whatsapp: Optional[str] = None
    vk: Optional[str] = None

    # Страницы сайта, которые удалось посетить в ходе обогащения.
    visited_pages: list[str] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.emails or self.telegram or self.whatsapp or self.vk)

    @property
    def messengers(self) -> list[str]:
        items = [
            ("Telegram", self.telegram),
            ("WhatsApp", self.whatsapp),
            ("VK", self.vk),
        ]
        return [label for label, value in items if value]


class Lead(BaseModel):
    """Карточка организации из каталога + обогащённые контакты."""

    name: str = Field(min_length=1, description="Название организации")
    category: str = Field(default="Без категории", description="Категория/сфера деятельности")
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    contact_info: ContactInfo = Field(default_factory=ContactInfo)
    source: str = Field(default="unknown", description="Источник данных")

 #-- валидаторы ----------------------------------------------------------

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = re.sub(r"\s+", " ", v).strip()
        if not v:
            raise ValueError("Название организации не может быть пустым")
        return v

    @field_validator("phone", mode="before")
    @classmethod
    def _normalize_phone_field(cls, v):
        if v is None or v == "":
            return None
        return normalize_phone(v)

    @field_validator("website", mode="before")
    @classmethod
    def _normalize_website_field(cls, v):
        if v is None or v == "":
            return None
        return normalize_website(v)

    @model_validator(mode="after")
    def _drop_invalid_phone(self) -> "Lead":
        # Если телефон не собрался в валидный формат — убираем его.
        if self.phone is not None and not re.fullmatch(r"\+\d{11,15}", self.phone):
            self.phone = None
        return self


    # Удобные вычисляемые свойства для отчёта.
    @property
    def has_website(self) -> bool:
        return bool(self.website)

    @property
    def has_email(self) -> bool:
        return bool(self.contact_info.emails)

    @property
    def has_messengers(self) -> bool:
        return bool(self.contact_info.messengers)