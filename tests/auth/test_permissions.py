import pytest

from app.auth.permissions import (
    IsOwnerOrReadOnly,
    require_analytics_access,
    require_premium,
)
from app.core.errors import ForbiddenError
from app.urls.models import URL
from app.users.models import Tier, User

OWNER = User(id=1, username="owner", tier=Tier.FREE)
OTHER = User(id=2, username="other", tier=Tier.PREMIUM)
ADMIN = User(id=3, username="admin", tier=Tier.ADMIN)
URL_OF_OWNER = URL(short_code="abc1234", original_url="https://e.com/", owner_id=1)
ANONYMOUS_URL = URL(short_code="anon123", original_url="https://e.com/", owner_id=None)

permission = IsOwnerOrReadOnly()


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
@pytest.mark.parametrize("user", [OWNER, OTHER, ADMIN], ids=["owner", "other", "admin"])
def test_everyone_may_read(method: str, user: User) -> None:
    assert permission.has_object_permission(method, user, URL_OF_OWNER)


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE", "POST"])
def test_only_the_owner_or_an_admin_may_change(method: str) -> None:
    assert permission.has_object_permission(method, OWNER, URL_OF_OWNER)
    assert permission.has_object_permission(method, ADMIN, URL_OF_OWNER)
    assert not permission.has_object_permission(method, OTHER, URL_OF_OWNER)


def test_nobody_but_admins_may_change_anonymous_urls() -> None:
    assert not permission.has_object_permission("PUT", OWNER, ANONYMOUS_URL)
    assert permission.has_object_permission("PUT", ADMIN, ANONYMOUS_URL)


def test_check_raises_forbidden() -> None:
    with pytest.raises(ForbiddenError, match="your own URLs"):
        permission.check("DELETE", OTHER, URL_OF_OWNER)


def test_analytics_rules() -> None:
    with pytest.raises(ForbiddenError, match="Premium"):
        require_premium(OWNER)  # Free
    require_premium(OTHER)  # Premium
    require_premium(ADMIN)

    with pytest.raises(ForbiddenError, match="own URLs"):
        require_analytics_access(OTHER, URL_OF_OWNER)
    require_analytics_access(OWNER, URL_OF_OWNER)
    require_analytics_access(ADMIN, URL_OF_OWNER)
