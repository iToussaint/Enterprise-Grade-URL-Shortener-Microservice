# URL Shortener Microservice

A Flask service that turns long URLs into short links, redirects visitors and
records every click. Users own their links (custom aliases, expiry dates, tags),
and Premium users get click analytics per day, country and referrer.
Built in modules: **5** (core service, Docker) and **6** (data model, users,
analytics) are complete.

**Stack:** Python 3.11 · Flask · Flask-RESTX · SQLAlchemy 2 / Alembic ·
PostgreSQL 18 · Pydantic · Flask-Injector · Docker · Gunicorn

## Quick start

Requires Docker with Compose v2.

```bash
cp .env.example .env                               # then set POSTGRES_PASSWORD and REDIS_PASSWORD
poetry run python scripts/download_geoip.py        # optional: city/country for clicks (~130 MB)
docker compose up --build                          # applies migrations, then starts the app
```

Open **<http://localhost:8000/api/docs>**, register a user, then use **Authorize**.
To unlock analytics for a user:

```bash
docker compose exec app flask --app app users set-tier <username> premium
```

## Configuration

Set in `.env` (see `.env.example`). Compose sets `APP_ENV`, `DATABASE_URL` and `REDIS_HOST` for the app container.

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_PASSWORD` | **required** | Database password (Compose creates the database) |
| `POSTGRES_USER`, `POSTGRES_DB` | `urlshortener` | Database user and name |
| `POSTGRES_HOST_PORT` | `5432` | Port on your machine; change it if a local PostgreSQL uses 5432 |
| `DATABASE_URL` | — | Required outside Docker: `postgresql+psycopg2://user:pass@localhost:5432/urlshortener` |
| `REDIS_PASSWORD` | **required** | Redis runs in Compose, reserved for caching (Module 8) |
| `APP_ENV` | `production` | `development`, `production` or `testing` |
| `GEOIP_DATABASE_PATH` | `geoip/dbip-city-lite.mmdb` | GeoIP database; without it, clicks have no location |
| `TRUSTED_PROXY_COUNT` | `0` | Trusted reverse proxies; only then is `X-Forwarded-For` used for the client IP |
| `WEB_CONCURRENCY` | `4` | Gunicorn workers in the production image |

## API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/<code>/` | — | Public short link: 302 to the original URL (code or alias); 404 unknown, 410 expired/deactivated |
| `POST` | `/api/v1/auth/register/` | — | Create an account (Free tier) |
| `POST` | `/api/v1/urls/` | Basic | Create a short URL (optional alias, expiry, tags) |
| `GET` | `/api/v1/urls/` | Basic | List your URLs (`status`, `sort`, `page`, `page_size`) |
| `GET` | `/api/v1/urls/<code>/` | Basic | Your URL's details |
| `PUT` | `/api/v1/urls/<code>/` | Basic | Replace your URL's editable fields |
| `DELETE` | `/api/v1/urls/<code>/` | Basic | Deactivate your URL (kept, with its clicks) |
| `GET` | `/api/v1/analytics/<code>/` | Basic, Premium | Clicks over time, per country and referrer (`days`, `interval`) |
| `POST` | `/api/urls` | — | Module 5: anonymous short URL |
| `GET` | `/api/<code>` | — | Module 5: same redirect as `/<code>/` |

- **Auth:** HTTP Basic (username and password on each request; use HTTPS in production). Other users' URLs return 404.
- **Errors:** always `{"error": {"code": "...", "message": "...", "details": [...]}}`.
- **Full schemas, validation rules and examples:** Swagger UI at `/api/docs` (spec at `/api/swagger.json`).

## Architecture

```mermaid
flowchart LR
    Visitor -->|GET /code/| Redirect[Public redirect]
    Client -->|/api/...| API[Flask-RESTX API<br/>auth · urls · analytics]
    Redirect --> Services
    API --> Services[Services<br/>UrlShortener · Click · Analytics]
    Services --> DB[(PostgreSQL)]
    Services --> GeoIP[(DB-IP file)]
    Redis[(Redis<br/>reserved: Module 8)]
```

```mermaid
erDiagram
    users ||--o{ urls : owns
    urls ||--o{ clicks : records
    urls }o--o{ tags : "url_tags"
```

Routes only handle HTTP; services hold the rules and are injected with Flask-Injector;
`URLManager` provides the `active_urls()`, `expired_urls()` and `popular_urls()` queries.
Lists load owners and tags with `joinedload`/`selectinload` (no N+1 queries);
analytics are computed with `GROUP BY` in PostgreSQL.

## Project structure

```text
app/
├── __init__.py        # create_app(): config, extensions, blueprints, DI
├── api.py             # /api blueprint, Swagger, namespaces
├── models.py          # imports every model (for migrations)
├── core/              # config, database extensions, errors, logging, Swagger helpers
├── auth/              # registration, HTTP Basic authentication
├── users/             # User model, `flask users set-tier`
├── urls/              # URL/Tag models, URLManager, service, routes, public redirect
└── analytics/         # Click model, click recording, GeoIP, analytics
migrations/            # Alembic: schema migrations + default-tags data migration
scripts/               # download_geoip.py
tests/                 # mirrors app/; runs against a real PostgreSQL
```

## Development

```bash
poetry install && poetry run pre-commit install
poetry run pytest                                   # needs Docker: Testcontainers starts PostgreSQL
poetry run pre-commit run --all-files               # Black, Ruff, mypy, requirements.txt export

docker compose exec app flask --app app db migrate -m "describe the change"   # new migration
docker compose exec app flask --app app db upgrade                            # apply migrations
```

Run without Docker: start only the database (`docker compose up -d db`), set
`DATABASE_URL` and `APP_ENV=development` in `.env`, then
`poetry run flask --app app db upgrade` and `poetry run flask --app app run --debug`.

**Production:** the image runs Gunicorn (`WEB_CONCURRENCY` workers) as a non-root user.
Run migrations as a separate step before starting new containers
(`.env` must hold the production `DATABASE_URL`):

```bash
docker build -t url-shortener .
docker run --rm --env-file .env url-shortener flask --app app db upgrade
docker run -d -p 8000:8000 --env-file .env -v ./geoip:/app/geoip:ro url-shortener
```

## Notes

- Flask-RESTX publishes **Swagger 2.0** (OpenAPI 2), not OpenAPI 3.0.
- HTTP Basic authentication is temporary; JWT login and refresh arrive in Module 7.
- IP Geolocation by [DB-IP](https://db-ip.com) (CC BY 4.0).
