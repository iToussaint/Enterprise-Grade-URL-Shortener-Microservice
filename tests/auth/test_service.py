import pytest

from app.auth import service as service_module
from app.auth.service import AuthService
from tests.factories import create_user

PASSWORD = "correct horse battery staple"

pytestmark = pytest.mark.usefixtures("app_context")


def test_authenticate_returns_the_user_for_valid_credentials() -> None:
    user = create_user("alice")

    assert AuthService().authenticate("alice", PASSWORD) == user


@pytest.mark.parametrize(
    ("username", "password"),
    [("alice", "wrong password"), ("nobody", PASSWORD)],
    ids=["wrong password", "unknown user"],
)
def test_authenticate_rejects_wrong_credentials(username: str, password: str) -> None:
    create_user("alice")

    assert AuthService().authenticate(username, password) is None


def test_authenticate_rejects_an_inactive_user() -> None:
    create_user("alice", is_active=False)

    assert AuthService().authenticate("alice", PASSWORD) is None


def test_unknown_user_still_costs_a_password_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Keeps response times the same, so they don't reveal which usernames exist.
    checked: list[str] = []

    def record_check(pwhash: str, password: str) -> bool:
        checked.append(password)
        return False

    monkeypatch.setattr(service_module, "check_password_hash", record_check)

    AuthService().authenticate("nobody", "guess")

    assert checked == ["guess"]
