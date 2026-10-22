# Python PAA Template Instructions

This directory is the Python implementation template for Personal AI
Architecture.

- Keep PAA-facing routes, schemas, message shapes, and stream events aligned
  with `contracts/` and `paa.lock.json`.
- Keep provider-specific details in `src/paa_template/adapters/`.
- Keep runtime configuration separate from request metadata.
- Run `python scripts/check_paa.py`, `python scripts/check_contracts.py`,
  `python scripts/check_imports.py`, and `python scripts/check_lockin.py`
  before changing the contract boundary.
- Run the shared validator from `../paa-conformance-validator` using
  `paa.target.json` before declaring the template acceptable.
