# URL Shortener Microservice

A Flask service that turns long URLs into short links, redirects visitors and
records every click. Users sign in with JWT and own their links (expiry dates,
tags; custom aliases on Premium); Premium users get click analytics per day,
country and referrer. Built in modules: **5** (core service, Docker), **6** (data
model, analytics) and **7** (JWT, roles, tier limits, rate limiting) are complete.

**Stack:** Python 3.11 · Flask · Flask-RESTX · SQLAlchemy 2 / Alembic ·
PostgreSQL 18 · Pydantic · Flask-Injector · Flask-JWT-Extended · Flask-Limiter ·
Redis · Docker · Gunicorn

## Quick start

Requires Docker with Compose v2.

```bash
cp .env.example .env                               # then set POSTGRES_PASSWORD, REDIS_PASSWORD, JWT_SECRET_KEY
poetry run python scripts/download_geoip.py        # optional: city/country for clicks (~130 MB)
docker compose up --build                          # applies migrations, then starts the app
```

Generate the JWT key with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
Open **<http://localhost:8000/api/docs>**: register, log in, then click **Authorize**
and enter `Bearer <access_token>`. To make a user Premium (or `admin`):

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
| `JWT_SECRET_KEY` | **required** | Signs the JWT tokens; at least 32 characters (the app refuses to start otherwise) |
| `REDIS_PASSWORD` | **required** | Redis holds the login rate-limit counters (caching arrives in Module 8) |
| `APP_ENV` | `production` | `development`, `production` or `testing` |
| `GEOIP_DATABASE_PATH` | `geoip/dbip-city-lite.mmdb` | GeoIP database; without it, clicks have no location |
| `TRUSTED_PROXY_COUNT` | `0` | Trusted reverse proxies; only then is `X-Forwarded-For` used for the client IP (set it behind a proxy, or rate limits apply to everyone together) |
| `WEB_CONCURRENCY` | `4` | Gunicorn workers in the production image |

## API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/<code>/` | — | Public short link: 302 to the original URL (code or alias); 404 unknown, 410 expired/deactivated |
| `POST` | `/api/v1/auth/register/` | — | Create an account (Free tier) |
| `POST` | `/api/v1/auth/login/` | — | Access token (15 min) + refresh token (7 days); 5 attempts/min per IP |
| `POST` | `/api/v1/auth/refresh/` | — | New access token from `{"refresh": "<token>"}` |
| `POST` | `/api/v1/urls/` | Bearer | Create a short URL (expiry, tags; alias on Premium) |
| `GET` | `/api/v1/urls/` | Bearer | List your URLs (`status`, `sort`, `tag`, `page`, `page_size`) |
| `GET` | `/api/v1/urls/<code>/` | Bearer | Any URL's details (read-only for non-owners) |
| `PUT` | `/api/v1/urls/<code>/` | Bearer, owner or Admin | Replace the URL's editable fields |
| `DELETE` | `/api/v1/urls/<code>/` | Bearer, owner or Admin | Deactivate the URL (kept, with its clicks) |
| `GET` | `/api/v1/analytics/<code>/` | Bearer, Premium owner or Admin | Clicks over time, per country and referrer (`days`, `interval`) |
| `POST` | `/api/urls` | — | Module 5: anonymous short URL |
| `GET` | `/api/<code>` | — | Module 5: same redirect as `/<code>/` |

- **Auth:** `Authorization: Bearer <access_token>` from login; refresh it with the refresh token. 401 if missing, expired or invalid; 429 after 5 login attempts per minute.
- **Roles and tiers:** Free — at most 10 active URLs, no custom alias, no analytics; Premium — unlimited, aliases, analytics; Admin — Premium plus changing and analysing any URL. Not allowed → 403.
- **Input:** URLs are trimmed and must be http/https, with no spaces or invisible characters, no `user:password@`, and not a link to this service (422 otherwise).
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
    API -.->|login rate limit| Redis[(Redis)]
```

Routes only handle HTTP and check permissions (`IsOwnerOrReadOnly`); services hold
the rules (including tier limits) and are injected with Flask-Injector;
`URLManager` provides the `active_urls()`, `expired_urls()` and `popular_urls()` queries.
Lists load owners and tags with `joinedload`/`selectinload` (no N+1 queries);
analytics are computed with `GROUP BY` in PostgreSQL.

### Data model

```mermaid
erDiagram
    users ||--o{ urls : owns
    urls ||--o{ clicks : records
    urls }o--o{ tags : "tagged via url_tags"

    users {
        int id PK
        string username UK
        string email UK "required"
        string password "scrypt hash"
        string tier "Free, Premium or Admin"
        bool is_premium "default false"
        bool is_active "default true"
        datetime date_joined
    }
    urls {
        int id PK
        string original_url
        string short_code UK "indexed, max 10"
        string custom_alias UK "nullable"
        int owner_id FK "nullable for Module 5 URLs"
        bool is_active "default true"
        datetime expires_at "nullable"
        int click_count "default 0, never negative"
        datetime created_at "indexed"
        string title "nullable, filled in Module 9"
        string description "nullable, filled in Module 9"
        string favicon "nullable, filled in Module 9"
    }
    clicks {
        bigint id PK
        int url_id FK "indexed with clicked_at"
        datetime clicked_at
        inet ip_address
        string city "nullable"
        string country "ISO code, nullable"
        text user_agent
        string referrer "nullable"
    }
    tags {
        int id PK
        string name UK
    }
```

- `users` also has Django `AbstractUser`'s `first_name`, `last_name`, `is_staff`, `is_superuser` and `last_login`.
- Deleting a user deletes their URLs; deleting a URL deletes its clicks and tag links (`ON DELETE CASCADE`). `DELETE` in the API only deactivates.
- Default tags (Marketing, Social, Newsletter, Product, Event) are seeded by a data migration.

## Project structure

```text
app/
├── __init__.py        # create_app(): config, extensions, blueprints, DI
├── api.py             # /api blueprint, Swagger, namespaces
├── models.py          # imports every model (for migrations)
├── core/              # config, database extensions, errors, logging, Swagger helpers
├── auth/              # registration, JWT login/refresh, permissions
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
- The Module 5 endpoint `POST /api/urls` stays anonymous and is not tier-limited.
- IP Geolocation by [DB-IP](https://db-ip.com) (CC BY 4.0).
