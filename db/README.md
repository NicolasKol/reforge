# db

Database schemas for pipeline provenance and experiment metadata.

## postgres/

PostgreSQL schema definitions:

- `init.sql` — Database initialization
- `provenance.sql` — Provenance tracking tables
- `nuke_reforge.sql` — Clean slate reset script

These schemas are automatically loaded by Docker Compose on first startup.
