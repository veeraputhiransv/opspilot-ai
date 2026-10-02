from uuid import uuid4

import pytest

from app.core.errors import OpsPilotError, UnauthorizedError
from app.identity.passwords import hash_password, verify_password
from app.identity.tokens import decode_access_token, encode_access_token

SECRET = "unit-test-secret-must-be-32b-long!"


def test_password_round_trip() -> None:
    hashed = hash_password("correct-horse-battery")
    assert verify_password("correct-horse-battery", hashed) is True
    assert verify_password("wrong-password-value", hashed) is False


def test_access_token_round_trip() -> None:
    user_id = uuid4()
    org_id = uuid4()
    workspace_id = uuid4()
    token = encode_access_token(
        secret=SECRET,
        user_id=user_id,
        organization_id=org_id,
        workspace_id=workspace_id,
        roles=["operator"],
        ttl_minutes=15,
    )
    payload = decode_access_token(token, SECRET)
    assert payload["sub"] == str(user_id)
    assert payload["org"] == str(org_id)
    assert payload["ws"] == str(workspace_id)
    assert payload["roles"] == ["operator"]


def test_access_token_rejects_wrong_secret() -> None:
    token = encode_access_token(
        secret=SECRET,
        user_id=uuid4(),
        organization_id=uuid4(),
        workspace_id=uuid4(),
        roles=["admin"],
        ttl_minutes=15,
    )
    with pytest.raises(UnauthorizedError):
        decode_access_token(token, "other-secret-must-be-32-bytes!!!")


def test_register_schema_rejects_short_password() -> None:
    from app.identity.service import _validate_password

    with pytest.raises(OpsPilotError):
        _validate_password("short")
