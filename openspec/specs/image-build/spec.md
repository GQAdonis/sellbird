# image-build Specification

## Purpose
Builds, scans and publishes the Sellbird image by digest.

## Requirements

### Requirement: Scanned publish by digest

On a merge to main the pipeline SHALL build the image, refuse to publish it if the vulnerability or secret scan fails, publish it under the commit SHA, and expose its digest.

#### Scenario: Clean build is published with a digest

- GIVEN a merge to main with a clean scan
- WHEN the pipeline runs
- THEN the image is published under the commit SHA and its digest is output

#### Scenario: Planted secret blocks publishing

- GIVEN an image containing a planted secret
- WHEN the secret scan runs
- THEN publishing is refused
