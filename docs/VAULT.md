# Workspace secret vault

Workspace integration credentials are stored in `integration_connections.encrypted_credentials`.

## Encryption

- Algorithm: AES-256-GCM (authenticated encryption)
- Nonce: 12 random bytes per payload
- Master key: `OPSPILOT_VAULT_MASTER_KEY` (32+ characters), hashed with SHA-256 to 32 bytes
- Production refuses to boot without a dedicated vault key (`docs` + Settings validator)

## Key management

- Generate the master key outside the app (KMS, sealed secret, or cloud secret manager)
- Rotate by decrypting with the old key and encrypting with the new key (`SecretVaultService.rotate`)
- Never log ciphertext+key together, never return decrypted payloads to the API

## Development

If the vault key is missing outside production, OpsPilot derives a process-local key from `OPSPILOT_JWT_SECRET`. That is not acceptable in production.
