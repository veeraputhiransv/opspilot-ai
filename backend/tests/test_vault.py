from app.core.config import Settings
from app.services.vault import SecretVaultService, VaultError


def _vault() -> SecretVaultService:
    return SecretVaultService(
        Settings(env="test", vault_master_key="unit-test-vault-master-key-32b!!", jwt_secret="x" * 40)
    )


def test_encrypt_decrypt_round_trip() -> None:
    vault = _vault()
    sealed = vault.encrypt({"token": "ghp_secret"})
    assert "ghp_secret" not in sealed
    assert vault.decrypt(sealed)["token"] == "ghp_secret"


def test_invalid_ciphertext() -> None:
    vault = _vault()
    try:
        vault.decrypt("00" * 20)
    except VaultError:
        return
    raise AssertionError("invalid ciphertext must fail")


def test_redact_never_returns_secrets() -> None:
    vault = _vault()
    redacted = vault.redact({"token": "secret", "webhook_url": "https://hooks.slack.com/x"})
    assert redacted["token"] == "[redacted]"
    assert "hooks.slack.com" not in str(redacted)


def test_rotate_rewrites_ciphertext() -> None:
    vault = _vault()
    first = vault.encrypt({"token": "ghp_secret"})
    second = vault.rotate(first)
    assert first != second
    assert vault.decrypt(second)["token"] == "ghp_secret"


def test_encrypt_without_key() -> None:
    vault = _vault()
    vault._key = None
    try:
        vault.encrypt({"token": "x"})
    except VaultError:
        return
    raise AssertionError("missing master key must fail encrypt")


def test_missing_master_key_in_production() -> None:
    try:
        Settings(env="production", jwt_secret="production-secret-must-be-long-enough", vault_master_key="short")
    except Exception as exc:
        assert "VAULT_MASTER_KEY" in str(exc)
        return
    raise AssertionError("production must require a vault master key")
