# Spec Delta: platform-interface

## Purpose

Defines what Sellbird requires from the shared platform so the two repositories can be built and verified independently.

## ADDED Requirements

### Requirement: Platform contract document

The repository SHALL publish a platform interface document that specifies database provisioning, identity issuer and JWKS, minted claims, hostname and certificate ownership, overlay location and pin format, namespaces, and secret names.

#### Scenario: Contract is complete

- GIVEN the published contract document
- WHEN the contract check runs
- THEN every required section, secret name, claim, overlay path and pin format is present and well-formed

#### Scenario: Incomplete contract is rejected

- GIVEN a copy of the contract with the JWKS section removed
- WHEN the contract check runs
- THEN the check fails and names the missing section

### Requirement: AI credential contract

The platform contract SHALL define the AI brain credential as Secret `sellbird-claude` with key `CLAUDE_CODE_OAUTH_TOKEN`, consumed only as an environment variable and never persisted or logged.

#### Scenario: Credential source is the environment

- GIVEN the contract
- WHEN the AI credential section is read
- THEN it names the Secret and key and forbids file persistence and logging

### Requirement: Operator agreement

The contract SHALL be considered agreed only when the operator records an agreement decision.

#### Scenario: Agreement is a decision, not a file

- GIVEN a well-formed contract without an operator agreement decision
- WHEN phase closure is evaluated
- THEN the contract scenario is reported BLOCKED, not PASS

### Requirement: Required contract sections

The platform interface document SHALL contain every level-two section in the required-section list below, each with its exact heading.

#### Scenario: Every required section is checked by name

- GIVEN the published contract document
- WHEN the contract check runs
- THEN it confirms each heading in the required-section list and reports any missing one by name
- AND the required-section list is: Status and agreement; Ownership summary; Namespaces; Database provisioning; Identity (Kratos); Operator identity provisioning; Gateway (flint-gate); Issuer and JWKS; Minted claims; Route ownership; Hostname and certificate; Session cookie domain; Secrets; AI credential; Gateway configuration values; Overlay location and pin format; Argo CD ownership; Migration flow; NetworkPolicy; Rotation and revocation; Out of scope; Placeholders

### Requirement: Required contract names

The platform interface document SHALL name the Secrets `sellbird-db-migrate` and `sellbird-db-app` with key `SELLBIRD_DATABASE_URL`, the Secret `sellbird-claude` with key `CLAUDE_CODE_OAUTH_TOKEN`, the claims `iss`, `aud`, `sub`, `kid` and `exp`, the overlay file `apps/sellbird/overlays/production/kustomization.yaml`, the repository variable `SELLBIRD_PLATFORM_REPO`, and the hostname placeholder `sellbird.example.test`.

#### Scenario: Every required name is checked

- GIVEN the published contract document
- WHEN the contract check runs
- THEN it confirms each required Secret, key, claim, path, variable and placeholder, and reports any missing one by name

### Requirement: Least-privilege database provisioning

The contract SHALL require a `sellbird` database owned by a migration role `sellbird_migrate` and a runtime role `sellbird_app` that holds only data-manipulation privileges, with no superuser, role-creation or database-creation rights and no DDL, and SHALL keep the database single tenant with row-level security deferred.

#### Scenario: Runtime role grants exclude DDL

- GIVEN the database provisioning section
- WHEN its grants are read
- THEN the runtime role receives SELECT, INSERT, UPDATE and DELETE through default privileges and no CREATE or ALL grant

### Requirement: Gate token contract

The contract SHALL define the flint-gate token Sellbird accepts: RS256 with a `kid` resolvable in a JWKS served at an in-cluster URL ending in `/.well-known/jwks.json`, an exact issuer string, `aud` equal to `sellbird`, `sub` equal to the Kratos identity id, and `exp` no more than 300 seconds after issue; and it SHALL state that Sellbird ignores cookies and unverified `x-flint-*` and forwarded headers.

#### Scenario: Claims are fully specified

- GIVEN the minted claims section
- WHEN each of iss, aud, sub, kid and exp is looked up
- THEN each has a defined value and the check Sellbird applies to it

### Requirement: Overlay pin format

The contract SHALL define the pin the deploy bot writes into the platform repository overlay as a `sellbird` images entry whose `newTag` is a 40-character lowercase hex commit SHA and whose `digest` is `sha256:` followed by 64 lowercase hex characters, changed together and never moved backwards.

#### Scenario: Example pin is well-formed

- GIVEN the overlay section's example kustomization
- WHEN its newTag and digest lines are matched against the stated formats
- THEN both match

### Requirement: Placeholders only in the public repository

The contract document SHALL use placeholders for every hostname, repository owner, platform repository name and identity id, and SHALL NOT contain a real hostname, email address or identity id.

#### Scenario: Real names are rejected

- GIVEN a copy of the contract containing a hostname that is not a placeholder
- WHEN the contract check runs
- THEN the check fails and names the hostname
