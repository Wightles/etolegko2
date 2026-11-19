# Keitaro Campaign Wrapper

Небольшая обёртка над Keitaro Admin API для первой части тестового задания.

Сейчас реализовано:

- создание кампании по названию, GEO-коду и ID оффера;
- выбор домена, группы и источника из справочников Keitaro;
- два потока:
  - GEO-поток принимает пользователей из выбранной страны и редиректит на Google;
  - default-поток отправляет остальных пользователей на выбранный оффер;
- сохранение результата создания в SQLite через SQLAlchemy;
- русский HTML/CSS/JS-интерфейс без frontend-фреймворка;
- автоматические проверки валидации и API-оркестрации.

Редактор существующей кампании (часть 2) пока не реализован по договорённости.

## Быстрый запуск

Требуется Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Заполни в `.env` ключ Admin API Keitaro:

```dotenv
KEITARO_BASE_URL=https://tlgk.host
KEITARO_API_KEY=твой_ключ_из_админки_keitaro
```

Запусти приложение:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

Открой <http://127.0.0.1:8000>.

## Миграции

Приложение использует SQLite по умолчанию (`data/app.db`) и Alembic.

```bash
# применить миграции
alembic upgrade head

# посмотреть текущую ревизию
alembic current

# создать новую ревизию после изменения моделей
alembic revision --autogenerate -m "описание изменения"

# откатить последнюю миграцию
alembic downgrade -1
```

Можно переопределить базу переменной `DATABASE_URL`, например для PostgreSQL.

## Как работает интеграция

Backend не отдаёт ключ в браузер. Он сам обращается к Keitaro Admin API с заголовками `Api-Key` и `Authorization: Bearer`.

Используемые endpoints:

- `GET /admin_api/v1/offers`;
- `GET /admin_api/v1/domains`;
- `GET /admin_api/v1/groups?type=campaigns`;
- `GET /admin_api/v1/traffic_sources`;
- `POST /admin_api/v1/campaigns`;
- `POST /admin_api/v1/streams`.

Если в установленной версии Keitaro отличаются имя GEO-фильтра или схема offer-потока, их можно переопределить в `.env` через `KEITARO_GEO_FILTER_NAME` и `KEITARO_OFFER_STREAM_SCHEMA`.

## Проверки

```bash
pytest
ruff check .
```

## Структура

```text
app/
  main.py       # FastAPI routes
  config.py     # настройки из .env
  database.py   # SQLAlchemy engine/session
  models.py     # журнал созданных кампаний
  schemas.py    # входные/выходные модели
  keitaro.py    # клиент и оркестрация вызовов Keitaro
  static/       # HTML, CSS, JS
alembic/        # миграции
tests/          # unit tests
```
