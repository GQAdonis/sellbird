# container-runtime Specification

## Purpose
Defines how the Sellbird container behaves when run in Kubernetes.

## Requirements

### Requirement: Non-root read-only runtime

The container SHALL run as a non-root user with a read-only root filesystem, writing only to a declared data volume.

#### Scenario: Runtime is locked down

- GIVEN the container running
- WHEN its user and filesystem are inspected
- THEN the user is not root and the root filesystem is read-only

### Requirement: Reproducible CLI install

The image SHALL install the Claude CLI at a pinned version verified by checksum.

#### Scenario: Tampered installer fails the build

- GIVEN a CLI download whose checksum does not match
- WHEN the image is built
- THEN the build fails

### Requirement: Environment-only AI credential

The container SHALL read the AI credential only from CLAUDE_CODE_OAUTH_TOKEN and SHALL NOT write any credential to disk or logs.

#### Scenario: Credential comes from the environment

- GIVEN the variable set
- WHEN the brain starts the CLI
- THEN the CLI receives it and no credential file is created

#### Scenario: No silent fallback

- GIVEN the variable unset
- WHEN the brain starts
- THEN it reports the documented missing-login error
