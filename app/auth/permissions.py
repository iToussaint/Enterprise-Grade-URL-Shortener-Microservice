"""Who may do what with a URL, like Django REST framework's permission classes.

Roles come from the user's tier: Free, Premium, Admin.
"""

from app.core.errors import ForbiddenError
from app.urls.models import URL
from app.users.models import PREMIUM_TIERS, Tier, User

# Methods that only read, as in DRF.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def is_admin(user: User) -> bool:
    return user.tier == Tier.ADMIN


class IsOwnerOrReadOnly:
    """Any authenticated user may read a URL; only its owner or an Admin may change it."""

    message = "You can only change your own URLs."

    def has_object_permission(self, method: str, user: User, url: URL) -> bool:
        if method in SAFE_METHODS:
            return True
        return is_admin(user) or url.owner_id == user.id

    def check(self, method: str, user: User, url: URL) -> None:
        if not self.has_object_permission(method, user, url):
            raise ForbiddenError(self.message)


def require_premium(user: User) -> None:
    """Detailed analytics are a Premium feature (Admins included)."""
    if user.tier not in PREMIUM_TIERS:
        raise ForbiddenError("Analytics require a Premium account.")


def require_analytics_access(user: User, url: URL) -> None:
    """Owners see their own URLs' analytics; Admins see every URL's."""
    if not is_admin(user) and url.owner_id != user.id:
        raise ForbiddenError("You can only view analytics for your own URLs.")
