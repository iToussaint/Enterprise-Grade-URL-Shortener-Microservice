"""Every model in one place.

Importing this module registers all tables with SQLAlchemy, which migrations
(autogenerate) and the tests' table clean-up rely on.
"""

from app.analytics.models import Click
from app.urls.models import URL, Tag, url_tags
from app.users.models import Tier, User

__all__ = ["URL", "Click", "Tag", "Tier", "User", "url_tags"]
