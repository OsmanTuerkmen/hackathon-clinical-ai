# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React 19, TypeScript, Vite 8, and IBM Carbon v11, specified in the F1 brief.

## Users

- Access-body staff assess requests, review cases and exports, and inspect the audit trail.
- Researchers and other applicants submit secondary-use requests and access approved results.
- Members of the public consult the transparency register.
- Hackathon jurors evaluate the local demonstration.

## Product Purpose

AccessDesk demonstrates an automated health data access body under Regulation (EU) 2025/327. It processes secondary-use requests using the Five Safes and makes the resulting decisions, safeguards, and permitted outputs inspectable.

## Positioning

This is a local Track 3 hackathon demonstration of an EHDS health data access workflow. It is not presented as a production authority or a live legal service.

## Operating Context

The demonstration runs locally on Windows and uses the supplied synthetic Track 3 data. Staff use an inbox and case workflow; applicants use a simulated identity and receive only results permitted by the case status; the public can inspect the register.

## Capabilities and Constraints

- The backend evaluates purpose, identity, query plans, statistical outputs, and SPE permits.
- Opt-outs are excluded, small cells are protected, and SPE files remain separate and read-only.
- AI is disabled unless separately configured.
- Runtime data and submissions remain local. The frontend makes no external network request.
- Regulation (EU) 2025/327 and the reviewed text in `docs/legal/compliance-check.md` govern the legal copy.
- Product behavior is evaluated against the supplied official requests, prototype results, and independent pandas oracle.

## Brand Commitments

The product name is AccessDesk. The interface uses the bilingual terms and the GOV.UK, NHS.UK, IBM Carbon, and Linear references recorded in `docs/design.md`. Copy stays factual and avoids promotional claims.

## Evidence on Hand

- `TRACK-3-ehds/` contains the official task, synthetic CSVs, requests, and expected answers; it is read-only.
- `ehds-accessdesk/` is the read-only prototype reference.
- `demo/registry.json`, the golden results, and the independent oracle provide local demonstration and regression data.
- No real patient records, customer testimonials, or production outcome metrics are supplied.

## Product Principles

- Apply the decision rules in the specified order and keep them explainable.
- Exclude opt-outs and minimize the data copied to an SPE.
- Release only small-cell-protected statistical results.
- Keep staff review, applicant access, and public transparency distinct.
- Preserve a local, offline demonstration with bilingual content.

## Accessibility & Inclusion

The interface targets WCAG 2.1 AA, supports keyboard operation, and provides German and English content. Status meaning is conveyed with text and icons as well as color.
