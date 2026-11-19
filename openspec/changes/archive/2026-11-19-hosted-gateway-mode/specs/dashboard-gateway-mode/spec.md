# Spec Delta: dashboard-gateway-mode

## Purpose

Lets the dashboard run behind flint-gate on a public hostname while keeping the local single-user token mode unchanged.

## ADDED Requirements

### Requirement: Configured gateway mode

The dashboard SHALL enter gateway mode only from configuration, never from request headers, and only then accept a non-loopback bind.

#### Scenario: Local mode refuses public binds

- GIVEN local token mode
- WHEN the dashboard starts with a non-loopback host
- THEN it exits with the loopback refusal

#### Scenario: Headers cannot switch modes

- GIVEN local token mode
- WHEN a request carries gateway identity headers
- THEN the request is handled as local mode and the headers are ignored

### Requirement: Gate token verification

In gateway mode the dashboard SHALL admit a request only with a flint-gate JWT that verifies against the pinned JWKS with the expected issuer, audience, key id and algorithm, is unexpired, and names an allowlisted identity.

#### Scenario: Allowlisted identity is admitted

- GIVEN a valid gate JWT for the allowlisted identity
- WHEN it requests the dashboard API
- THEN the request succeeds as principal user

#### Scenario: Invalid credentials are refused

- GIVEN no JWT, a forged identity header, a JWT with the wrong audience, an expired JWT, or a non-allowlisted identity
- WHEN it requests the dashboard API
- THEN the request is refused with 401 and no data

### Requirement: Untrusted inputs in gateway mode

In gateway mode the dashboard SHALL ignore cookies and unverified forwarded or identity headers and SHALL disable the agent token.

#### Scenario: Cookie alone grants nothing

- GIVEN a request with a session cookie but no gate JWT
- WHEN it requests the dashboard API
- THEN it is refused

### Requirement: Token never printed

The dashboard SHALL NOT print or log its unlock token in gateway mode or inside a container.

#### Scenario: Logs stay clean

- GIVEN the dashboard started in a container
- WHEN its logs are searched for the token
- THEN the token is not found
