import pytest
from sqlalchemy.exc import IntegrityError

from app.auth.passwords import PasswordRejected
from app.users import find_user


def test_usernames_are_matched_without_regard_to_case_or_spacing(make_user, session) -> None:
    make_user("Astrid")
    assert find_user(session, "  ASTRID ").username == "astrid"


def test_a_username_can_only_be_taken_once(make_user, session) -> None:
    make_user("astrid")
    with pytest.raises(IntegrityError):
        make_user("Astrid")


def test_a_user_with_a_weak_password_is_not_created(make_user, session) -> None:
    with pytest.raises(PasswordRejected):
        make_user("astrid", password="kort")
    assert find_user(session, "astrid") is None


def test_the_password_is_never_stored_as_typed(make_user) -> None:
    user = make_user()
    assert user.password_hash.startswith("$argon2id$")
