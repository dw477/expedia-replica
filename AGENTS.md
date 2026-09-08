# Project Rules

These rules apply throughout the repository.

## Structure

- Keep client-side code in `frontend/` and server-side code in `backend/`.
- Keep shared contracts explicit. If API schemas or generated types are added, document where their source of truth lives.
- Prefer small, focused modules with names that describe their responsibility.

## Changes

- Preserve the existing architecture and conventions unless a requirement calls for changing them.
- Avoid unrelated refactors in feature and bug-fix changes.
- Never commit secrets, credentials, generated build output, dependency directories, or local environment files.
- Update `README.md` when setup steps, prerequisites, or top-level commands change.

## Quality

- Add or update tests for behavior changes.
- Run the relevant formatter, linter, type checker, and tests before considering work complete.
- Handle errors explicitly at system boundaries such as HTTP requests, input parsing, and persistence.
- Keep user-facing behavior accessible and responsive when working in the frontend.

## Documentation

- Explain non-obvious decisions near the code or in the relevant application documentation.
- Keep commands copy-pasteable and avoid documenting tools that are not actually configured.
