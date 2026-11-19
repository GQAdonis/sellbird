# image-delivery Specification

## Purpose
Delivers a published image to the platform's overlay by pinned digest with guards.

## Requirements

### Requirement: Guarded digest pin

The deploy job SHALL pin the overlay to the published image by tag and digest and SHALL refuse malformed digests, tag-only images and pins that move backwards.

#### Scenario: Valid forward pin is written

- GIVEN a valid digest for a commit ahead of the current pin
- WHEN the deploy job runs
- THEN only the tag and digest lines change

#### Scenario: Bad pins are refused

- GIVEN a malformed digest, a tag-only image, or an older commit
- WHEN the deploy job runs
- THEN it refuses and writes nothing

### Requirement: Hardened manifests

Sellbird's manifests SHALL run the app non-root with a read-only root filesystem, allow ingress only from flint-gate, run migrations as a separate job, and reference secrets only by name.

#### Scenario: Rendered manifests pass the checks

- GIVEN the rendered example overlay
- WHEN the manifest check runs
- THEN pinning, network policy, read-only root, the migration job and secret references all pass, and no real hostname literal is present
