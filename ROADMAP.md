# Roadmap

This document tracks possible future work. Items are not committed release
scope until they are selected for a milestone and given acceptance criteria.

## Feed Selection and Presentation

- Include and exclude keyword filters.
- Per-feed message templates with safe rendering rules.
- Digest mode for combining multiple entries into fewer Matrix messages.
- Additional feed metadata such as publication time and author.

## Matrix Integration

- Room aliases as an alternative to internal room IDs.
- Optional support for encrypted Matrix rooms.
- Configurable message types and richer Matrix event formatting.

## Operations

- Prometheus metrics for runs, failures, retries, and delivery latency.
- Configurable log verbosity and optional structured JSON logs.
- State inspection and controlled retention commands.
- Health/status command suitable for monitoring checks.

## Distribution

- Native Debian package and repository.
- Signed release artifacts and checksum publication.
- Automated installation and upgrade verification on supported Debian releases.

## Engineering

- Property-based tests for feed identity and configuration boundaries.
- Integration tests against disposable Synapse and HTTP feed fixtures.
- Database migration fixtures for every released schema version.
