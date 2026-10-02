# Contributing

Thanks for looking at OpsPilot. Small, reviewable changes that preserve the investigation and policy contracts are welcome.

## Local development

1. Copy `.env.example` to `.env` if you are not using Compose defaults.
2. Start PostgreSQL (pgvector) and Redis: `docker compose up -d postgres redis`.
3. Backend: `cd backend && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/alembic upgrade head`.
4. Frontend: `cd frontend && npm install`.

See [README.md](README.md) for full run instructions and [docs/DEMO.md](docs/DEMO.md) for the optional AcmeFlow workspace.

## Quality gates

Please run the same checks CI runs before opening a pull request:

```bash
cd backend
ruff check app tests
mypy app
pytest -q
python -m app.evaluation.runner

cd ../frontend
npm run typecheck
npm run lint
```

Browser tests (approve, reject, isolation, demo):

```bash
bash scripts/run-e2e.sh
```

Do not weaken tests to make a change pass.

## Design constraints

- Do not bypass `RiskPolicyService` or add a generic tool-execute endpoint.
- Keep every incident and knowledge query workspace-scoped.
- Alert `message` text is evidence, not control.
- Demo adapters must stay labeled as simulation.
- Do not commit `.env`, videos, or machine-local paths.

## Security reports

Use [SECURITY.md](SECURITY.md). Do not file public issues for exploitable bugs.
