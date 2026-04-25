# Contributing

Mini.ai is a personal research project. The bar for contributions is:

1. **All dependencies permissively licensed** (MIT / Apache 2.0). No GPL, AGPL, or BSL.
2. **Pure logic is tested.** If you add a scoring function, decay curve, or policy rule, add a test in `tests/`.
3. **Policies respect the contract.** Every cognitive policy extends `CognitivePolicy`, emits a structured log, and is idempotent.
4. **No secrets in commits.** `.env` is gitignored. Use Secret Manager for GCP.

## Local dev

```bash
pip install -r requirements.txt
pytest tests/ -v
docker compose -f infra/docker-compose.yml up -d
```

## PRs

Small, focused, with a description. Reference the backlog story ID (e.g. `S019`) where relevant.
