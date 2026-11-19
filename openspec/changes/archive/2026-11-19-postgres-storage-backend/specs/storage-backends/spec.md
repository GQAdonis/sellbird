# Spec Delta: storage-backends

## Purpose

Lets Sellbird keep its state in SQLite for local installs or in Postgres 18 for hosted deployments with identical behaviour.

## ADDED Requirements

### Requirement: Selectable storage backend

Sellbird SHALL store state in SQLite by default and in Postgres 18 when configured with a Postgres backend, with identical observable behaviour for every state operation.

#### Scenario: SQLite remains the default

- GIVEN a local install with no backend configured
- WHEN Sellbird runs its state operations
- THEN results equal the hand-authored expectations and the database is a local SQLite file

#### Scenario: Postgres matches the same expectations

- GIVEN Sellbird configured with a Postgres 18 backend
- WHEN the same state operations run
- THEN results equal the same hand-authored expectations

### Requirement: Governed signal vocabulary

Each backend SHALL reject an observation whose signal code is not in the governed vocabulary.

#### Scenario: Unknown signal code is refused

- GIVEN a signal code absent from the vocabulary
- WHEN an observation with that code is written
- THEN the write is refused and nothing is stored

### Requirement: Exactly-once outbox claim

Each backend SHALL let exactly one claimer take an approved outbox item, even under concurrent claim attempts.

#### Scenario: Concurrent claims yield one winner

- GIVEN one approved outbox item and several concurrent claimers
- WHEN they all try to claim it
- THEN exactly one claim succeeds

#### Scenario: Claimed item cannot be claimed again

- GIVEN an item already claimed
- WHEN a second claimer tries
- THEN no claim is returned

### Requirement: Sending safety parity

Quiet hours, the daily send limit, opt-out and suppression, and the approval ladder SHALL behave identically on both backends.

#### Scenario: Unsafe sends are refused on both backends

- GIVEN a send inside quiet hours, over the daily limit, to a suppressed address, or of an unapproved item
- WHEN the sender evaluates it on either backend
- THEN the send is refused

### Requirement: Reversible migrations

Postgres schema changes SHALL be versioned migrations that can be applied, reversed and re-applied to an identical schema.

#### Scenario: Up, down, up is identical

- GIVEN a fresh Postgres database
- WHEN all migrations are applied, reversed and re-applied
- THEN the schema equals a fresh application and the recorded version is the latest migration

### Requirement: Least-privilege runtime role

Sellbird SHALL run against Postgres with a role that cannot change the schema; migrations SHALL use a separate migration role.

#### Scenario: Runtime role cannot alter schema

- GIVEN a connection as the runtime role
- WHEN it attempts CREATE TABLE or ALTER TABLE
- THEN the statement is refused
