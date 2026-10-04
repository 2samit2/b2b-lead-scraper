# B2B Lead Scraper & Contact Enricher

Production-ready проект (с комментариями) для сбора коммерческих B2B-лидов: поиск организаций
в открытом каталоге, асинхронное обогащение их сайтов контактами
(email, мессенджеры) и выгрузка в стилизованный двухстраничный Excel-отчёт.

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Async](https://img.shields.io/badge/asyncio-httpx-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## 🇷🇺 Русский

### Возможности

- **Сбор организаций** по ключевому слову и городу (название, категория,
  адрес, телефон, сайт).
- **Модульный скрейсер**: `BaseScraper` → подключайте любые источники
  (2GIS, Yandex Maps и т.д.) без изменения пайплайна.
- **Асинхронное обогащение**: если у организации есть сайт, скрипт
  обходит его главную страницу и страницы контактов (`/contacts`, `/about`)
  и извлекает:
  - email-адреса (валидация регулярками, отсев картинок `.png/.jpg` и мусора);
  - ссылки на Telegram, WhatsApp, VK.
- **Нормализация телефонов**: очистка от лишних символов, приведение
  к формату `+7XXXXXXXXXX`.
- **Демо-режим `--demo`**: мгновенный запуск на моковых данных без
  обращения к внешним сервисам и риска блокировок.
- **Excel-отчёт**: тёмно-изумрудная шапка, автофильтры, закреплённая
  строка заголовков, кликабельные ссылки, лист «Статистика».

### Стек

| Компонент | Технология |
|---|---|
| Язык | Python 3.11+ |
| HTTP | httpx + asyncio (Semaphore для контроля конкурентности) |
| Парсинг | BeautifulSoup4 |
| Валидация | pydantic v2 |
| Отчёт | openpyxl |
| Логирование | loguru |

### Быстрый старт

```bash
# 1. Клонировать и установить зависимости
cd b2b_lead_scraper
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Мгновенная проверка (моковые данные, офлайн)
python main.py --demo --enrich

# 3. Реальный сбор (открытый каталог OpenStreetMap)
python main.py --query "Автосервис" --city "Казань" --limit 30 --enrich

# 4. Свой путь сохранения
python main.py --query "Стоматология" --city "Москва" --limit 20 --enrich \
    --output output/dentists.xlsx
```

### CLI-параметры

| Флаг | Описание | По умолчанию |
|---|---|---|
| `--query, -q` | Ключевое слово для поиска | `Автосервис` |
| `--city, -c` | Город поиска | `Казань` |
| `--limit, -l` | Максимум организаций в выборке | `30` |
| `--enrich, -e` | Обогащение (обход сайтов) | выкл. |
| `--demo` | Демо-режим (офлайн, моковые данные) | выкл. |
| `--source, -s` | Источник: `demo-catalog` / `openstreetmap` | авто |
| `--output, -o` | Путь к отчёту | `output/leads_YYYY-MM-DD.xlsx` |
| `--verbose, -v` | Подробный лог (DEBUG) | выкл. |

### Архитектура

```text
main.py      ← CLI (argparse), пайплайн: scrape → enrich → export
scraper.py   ← BaseScraper + DemoScraper + OsmScraper (Overpass API + Nominatim)
enricher.py  ← Асинхронный обход сайтов, извлечение email/TG/WA/VK
exporter.py  ← Двухстраничный стилизованный Excel-отчёт (openpyxl)
models.py    ← Pydantic-модели Lead / ContactInfo, нормализация телефонов
config.py    ← Все настройки: сеть, парсинг, стиль отчёта

Конвейер:

```text
CLI → [Scraper] → list[Lead] → [Enricher] → list[Lead] → [Exporter] → .xlsx
```

### Структура Excel-отчёта

**Лист 1 «База Лидов»** — тёмно-изумрудная шапка, автофильтр, закреплённая
верхняя строка, зебра-строки, кликабельные ссылки (сайт, email, Telegram,
WhatsApp, VK), телефоны в формате `+7...`.

**Лист 2 «Статистика»** — сводная таблица: всего собрано, лидов с сайтом,
с email, с мессенджерами, с телефоном, проценты, топ-5 категорий,
количество посещённых при обогащении страниц.

### Демо-режим

`--demo` подменяет HTTP-транспорт локальными мок-страницами: пять
виртуальных сайтов с разным набором контактов (у одного — два email и все
мессенджеры, у другого — только картинка, похожая на email, и т.д.).
Результат детерминирован: одна и та же команда всегда даёт одинаковый отчёт.

### Docker

```bash
# Демо-режим (по умолчанию, офлайн)
docker compose up --build

# Реальный сбор: передайте аргументы в command или через `run`
docker compose run lead-scraper --query "Автосервис" --city "Казань" \
    --limit 30 --enrich
```

### Контакты и заметки

- Реальный источник — OpenStreetMap (Overpass API / Nominatim): открытые
  данные под ODbL-лицензией. Уважайте условия использования API
  (умеренная частота запросов).
Соблюдайте robots.txt и законы о персональных данных при работе
с реальными сайтами.
<img width="1815" height="775" alt="Снимок экрана_20261004_222027" src="https://github.com/user-attachments/assets/d16f4fae-bf27-47ef-9647-78146cf68f54" />

---

## 🇬🇧 English

### Features

- **Collect organizations** by keyword and city (name, category, address,
  phone, website).
- **Modular scraper**: `BaseScraper` lets you plug in any source
  (2GIS, Yandex Maps, etc.) without touching the pipeline.
- **Async enrichment**: if an organization has a website, the script
  visits its home page and contact pages (`/contacts`, `/about`) and
  extracts:
  - emails (regex validation, filtering out `.png/.jpg` image noise);
  - Telegram, WhatsApp, VK links.
- **Phone normalization**: cleanup and conversion to `+7XXXXXXXXXX`.
- **`--demo` mode**: instant offline run on mock data, zero risk of
  being blocked by external services.
- **Excel report**: dark emerald header, autofilter, frozen header row,
  clickable links, and a Statistics sheet.

### Stack

Python 3.11+ · httpx + asyncio (Semaphore-based concurrency) ·
BeautifulSoup4 · pydantic v2 · openpyxl · loguru.

### Quick Start

```bash
cd b2b_lead_scraper
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Instant offline check
python main.py --demo --enrich

# Real collection (OpenStreetMap open catalog)
python main.py --query "Автосервис" --city "Казань" --limit 30 --enrich
```

### Architecture

```text
main.py      ← CLI (argparse), pipeline: scrape → enrich → export
scraper.py   ← BaseScraper + DemoScraper + OsmScraper (Overpass API + Nominatim)
enricher.py  ← Async website crawling, email/TG/WA/VK extraction
exporter.py  ← Two-sheet styled Excel report (openpyxl)
models.py    ← Pydantic models Lead / ContactInfo, phone normalization
config.py    ← All settings: networking, parsing, report styling
```

```text
CLI → [Scraper] → list[Lead] → [Enricher] → list[Lead] → [Exporter] → .xlsx
```

### Docker

```bash
docker compose up --build            # demo mode by default
docker compose run lead-scraper --query "Автосервис" --city "Казань" --limit 30 --enrich
```

### Notes

- Real source is OpenStreetMap (Overpass API / Nominatim), open data under
  ODbL. Respect the API usage policy (moderate request rate).
- When crawling real websites, respect robots.txt and personal data laws.
<img width="1815" height="775" alt="Снимок экрана_20261004_222027" src="https://github.com/user-attachments/assets/d16f4fae-bf27-47ef-9647-78146cf68f54" />
