## ADDED Requirements

### Requirement: The platform interface document SHALL describe every resource the base creates

The platform interface document SHALL describe every resource the base creates.

#### Scenario: The platform interface document case 1

- **GIVEN** the rendered base manifests
- **WHEN** compared with docs/platform-interface.md
- **THEN** each kind and name in the base appears in the document
