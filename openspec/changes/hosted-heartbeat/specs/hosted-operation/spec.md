## ADDED Requirements

### Requirement: The hosted Sellbird SHALL run heartbeat cycles without operator action after a restart

The hosted Sellbird SHALL run heartbeat cycles without operator action after a restart.

#### Scenario: The hosted Sellbird case 1

- **GIVEN** a trained hosted Sellbird
- **WHEN** the pod restarts
- **THEN** a new heartbeat cycle is recorded in the database

### Requirement: The hosted dashboard SHALL report a stopped heartbeat as stopped

The hosted dashboard SHALL report a stopped heartbeat as stopped.

#### Scenario: The hosted dashboard case 2

- **GIVEN** the newest heartbeat record is older than three intervals
- **WHEN** the status endpoint is read
- **THEN** it reports not running

### Requirement: No email SHALL be sent in hosted mode without approval

No email SHALL be sent in hosted mode without approval.

#### Scenario: No email case 3

- **GIVEN** approval mode on
- **WHEN** a heartbeat cycle stages email
- **THEN** each waits in the Outbox and the sent count does not change
