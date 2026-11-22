## ADDED Requirements

### Requirement: Hosted configuration SHALL survive a pod restart

Hosted configuration SHALL survive a pod restart.

#### Scenario: Hosted configuration case 1

- **GIVEN** a file written under the hosted home folder
- **WHEN** the pod is deleted and replaced
- **THEN** the file is present with the same content in the new pod

### Requirement: The migration Job SHALL NOT depend on a resource created later in the same sync

The migration Job SHALL NOT depend on a resource created later in the same sync.

#### Scenario: The migration Job case 2

- **GIVEN** the rendered base manifests
- **WHEN** hook phases and waves are ordered
- **THEN** every resource the migration Job references is a PreSync hook at an earlier wave or exists outside the sync

### Requirement: DNS egress SHALL work with and without NodeLocal DNSCache

DNS egress SHALL work with and without NodeLocal DNSCache.

#### Scenario: DNS egress case 3

- **GIVEN** the rendered NetworkPolicy
- **WHEN** its DNS egress rules are read
- **THEN** port 53 is allowed to kube-dns pods and to 169.254.20.10/32 and to no other link-local address
