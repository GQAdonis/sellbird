## ADDED Requirements

### Requirement: The gateway JWKS address SHALL be https outside loopback and in-cluster hosts

The gateway JWKS address SHALL be https outside loopback and in-cluster hosts.

#### Scenario: The gateway JWKS address case 1

- **GIVEN** a JWKS address with scheme http and a public host
- **WHEN** gateway configuration loads
- **THEN** loading fails with a message naming the variable and no value

### Requirement: exists() SHALL treat an unclassified connect failure as an outage

exists() SHALL treat an unclassified connect failure as an outage.

#### Scenario: exists() case 2

- **GIVEN** a connect failure carrying no sqlstate
- **WHEN** exists() is called
- **THEN** it raises a storage error
