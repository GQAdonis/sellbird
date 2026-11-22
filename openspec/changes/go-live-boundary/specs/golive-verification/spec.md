## ADDED Requirements

### Requirement: Boundary evidence SHALL contain counts, exit codes, digests and timestamps only

Boundary evidence SHALL contain counts, exit codes, digests and timestamps only.

#### Scenario: Boundary evidence case 1

- **GIVEN** a finished boundary run
- **WHEN** the evidence folder is searched for secret, email and token patterns
- **THEN** nothing matches
