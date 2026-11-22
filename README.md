# Keitaro Campaign Wrapper

Небольшая обёртка над Keitaro Admin API для создания кампаний и безопасного редактирования
офферов внутри потоков.

Сейчас реализовано:

- создание кампании по названию, GEO-коду и ID оффера;
- выбор домена, группы и источника из справочников Keitaro;
- два потока:
  - GEO-поток принимает пользователей из выбранной страны и редиректит на Google;
  - default-поток отправляет остальных пользователей на выбранный оффер;
- сохранение результата создания в SQLite через SQLAlchemy;
- русский HTML/CSS/JS-интерфейс без frontend-фреймворка;
- автоматические проверки валидации и API-оркестрации.
- импорт потоков существующей кампании в локальную базу;
- локальный черновик офферов с `Add`, `Remove`, `Bring Back`, `Cancel` и `Pin Weight`;
- публикация только офферов через `Push to KT` без перезаписи фильтров и редиректов;
- архив удалённых офферов и защита от перезаписи неопубликованного черновика при Fetch;
- отдельный экран редактора потоков в том же HTML/CSS/JS-интерфейсе.

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

### Запуск через Docker

Если Python на компьютере не настроен, достаточно установленного Docker:

```bash
docker compose up --build
```

Приложение будет доступно на <http://127.0.0.1:7777>. Остановить контейнер можно сочетанием `Ctrl+C`, а удалить его — командой `docker compose down`.

## Редактор потоков

1. В блоке `Редактор потоков и офферов` выбери кампанию или введи её ID.
2. Нажми `Fetch Streams from KT`. Поток без офферов отображается, но намеренно не изменяется.
3. Для потока с офферами найди оффер, выбери его и нажми `Add`. Действие меняет только локальный черновик.
4. `Remove`, `Bring Back` и `Pin Weight` также меняют только локальную базу.
5. `Cancel` возвращает последнее опубликованное состояние.
6. `Push to KT` отправляет в Keitaro только список офферов и их доли. Фильтры, редирект, триггеры и лендинги берутся из актуального потока Keitaro и сохраняются.

Если в потоке есть неопубликованный черновик, повторный `Fetch` остановится с предупреждением. После явного нажатия `Сбросить черновик и повторить Fetch` локальные изменения будут отменены.

Состояние редактора хранится в таблицах `managed_campaigns`, `managed_streams`, `offers` и `stream_offers`. Последний опубликованный снимок хранится в `managed_streams.published_snapshot`, поэтому отмена и архивирование не удаляют историю оффера.

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
- `GET /admin_api/v1/campaigns` и `GET /admin_api/v1/campaigns/{id}`;
- `GET /admin_api/v1/campaigns/{id}/streams`;
- `GET /admin_api/v1/streams/{id}`;
- `PUT /admin_api/v1/streams/{id}` — только с заменой массива `offers` и сохранением остальных полей;
- `GET /admin_api/v1/offers/{id}` и `GET /admin_api/v1/offers`.

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
  models.py     # журнал создания и локальные модели редактора
  schemas.py    # входные модели API
  keitaro.py    # клиент Admin API Keitaro
  editor.py     # черновики, снимки, архив и расчёт весов
  static/       # HTML, CSS, JS
alembic/        # миграции
tests/          # unit tests
```
