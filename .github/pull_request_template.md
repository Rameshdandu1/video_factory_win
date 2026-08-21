## Outcome

Describe the user-visible or operational result.

## Contract and architecture impact

- Architecture impact: none / describe and link ADR
- API impact: none / describe migration
- Data impact: none / describe migration and rollback
- Wan2.1 revision/default impact: none / describe evidence

## Verification

- [ ] Relevant tests added or updated
- [ ] `ruff format --check .`
- [ ] `ruff check .`
- [ ] `mypy`
- [ ] `pytest -m "not gpu"`
- [ ] `cd frontend && npm ci`
- [ ] `cd frontend && npm run format`
- [ ] `cd frontend && npm run lint`
- [ ] `cd frontend && npm run typecheck`
- [ ] `cd frontend && npm test`
- [ ] `cd frontend && npm run build`
- [ ] No unrelated files changed
- [ ] Documentation/contracts updated where required
