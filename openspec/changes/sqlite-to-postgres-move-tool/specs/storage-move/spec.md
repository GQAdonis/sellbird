# Spec Delta: storage-move

## Purpose

Moves an existing SQLite Sellbird database into an empty Postgres backend without losing data.

## ADDED Requirements

### Requirement: Complete move

The move command SHALL copy every table from a SQLite database into an empty Postgres database in one transaction, preserving identifiers, timestamps, JSON and signal confirmation state.

#### Scenario: Counts and checksums match

- GIVEN a fixture SQLite database
- WHEN it is moved into an empty Postgres database
- THEN per-table row counts and checksums equal the fixture's recorded values

### Requirement: Non-empty target refused

The move command SHALL refuse a target database that already holds Sellbird data and SHALL write nothing.

#### Scenario: Existing data is protected

- GIVEN a Postgres database that already holds Sellbird rows
- WHEN a move into it is attempted
- THEN the command refuses and the target is unchanged
