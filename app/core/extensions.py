from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Predictable constraint and index names, so later migrations can alter or drop them.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Created here, initialised in create_app(): models import `db` without
# importing the application factory, which avoids circular imports.
db = SQLAlchemy(model_class=Base)
# Batch mode is a workaround for SQLite's limited ALTER TABLE; PostgreSQL
# does not need it, so migrations use plain operations.
migrate = Migrate(render_as_batch=False)
