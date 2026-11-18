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
