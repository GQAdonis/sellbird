## ADDED Requirements

### Requirement: A deploy SHALL require a passing test run of the same commit

A deploy SHALL require a passing test run of the same commit.

#### Scenario: A deploy case 1

- **GIVEN** a commit whose test job fails
- **WHEN** the image workflow runs
- **THEN** the deploy job does not run

### Requirement: The published image SHALL be the image that was scanned

The published image SHALL be the image that was scanned.

#### Scenario: The published image case 2

- **GIVEN** the image ID recorded right after build
- **WHEN** scans finish
- **THEN** publish proceeds only if the image ID is unchanged

### Requirement: A failing scan SHALL stop publication

A failing scan SHALL stop publication.

#### Scenario: A failing scan case 3

- **GIVEN** the vulnerable-image control
- **WHEN** the workflow runs
- **THEN** the scan step fails and nothing is published or deployed

### Requirement: The image SHALL install only hash-locked dependencies

The image SHALL install only hash-locked dependencies.

#### Scenario: The image case 4

- **GIVEN** a lock entry whose hash does not match
- **WHEN** the image builds
- **THEN** the build fails
