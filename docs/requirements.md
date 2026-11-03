# Blueprint traceability

Source: all 12 pages of Z-PRINT Software Requirements Specification + Codex Development Blueprint v1.0, 27 October 2026. Phase 1 is the requested delivery. Later-phase requirements are tracked below, not waived. “Implemented” means in the simulation context only.

| ID | Requirement | Current evidence and remaining scope | Phase |
|---|---|---|---|
| FR-01 | Station QR and scoped sessions | Server-validated station URL and private bearer sessions implemented. Printed QR generation, TLS and Next.js mobile portal pending. | 1 partial; 2 |
| FR-02 | PDF/DOCX secure upload | PDF limit/signature/parser checks, session ownership implemented. DOCX expressly rejected; sandbox conversion pending. | 1 PDF; 2 DOCX |
| FR-03 | Conversion/count/preview | Server PDF page count, normalization and authorized PDF preview. DOCX and thumbnails pending. | 1 partial; 2 |
| FR-04 | Copies/mode/duplex/A4/ranges | Validated settings, exact page selection and copies; colour rejected by B/W simulated device. Real device options pending. | 1; 5 hardware |
| FR-05 | Whole-order pricing | Both proposed tier sets seeded, versioned immutable quotes, thresholds tested. Admin tier validation/editing pending. | 1; 4 admin |
| FR-06 | Capability/readiness gating | Heartbeat freshness, device checks, empty/error blocking and bulk unknown gating. Real telemetry/reservations/operator confirmation pending. | 1 simulation; 4–5 |
| FR-07 | MTN/Airtel initiation | Gateway protocol and simulated choices, Uganda-format number validation, masked storage, no PIN. Carrier-specific validation/onboarding pending. | 1 mock; 3 real |
| FR-08 | Verified callback/reconciliation | HMAC mock signature plus separate ledger verification, duplicate/pending/mismatch/retry tests. Actual gateway signature, polling scheduler, reversals/settlement discrepancy queue pending. | 1 mock; 3 |
| FR-09 | Durable queue/dispatch/audit | Database CAS claim, unique attempt, local SQLite intent/outbox, audit and ambiguous lease/restart quarantine. Hardware spooler and long-job lease renewal pending. | 1 simulation; 4–5 |
| FR-10 | Restricted USB kiosk | Folder and contract only; not a locked kiosk. No arbitrary filesystem API exists. Safe USB enumeration/import/eject and OS lockdown pending. | 4 |
| FR-11 | Status/receipt/reports | Live demo polling, simulated receipt/history, protected sales/jobs report API. Full admin dashboard and financial reports pending. | 1 partial; 4 |
| FR-12 | Offline printing/payment rules | Durable agent outbox replay implemented. Full local API, local Wi-Fi portal, verified prepaid/offline mechanisms and cloud synchronization pending. No offline new charges. | 4 |
| FR-13 | Error recovery | Simulated readiness failures, paid hold, restart uncertainty and network outbox tests. Operator reprint/refund/jam workflows pending. | 1 partial; 4–5 |
| FR-14 | Admin tiers/devices/limits/pause | Seeded schema, configured limits and read-only protected pricing/report endpoints. Role-based accounts, changes/audits and pause UI pending. | 4 |
| FR-15 | Retention/private content | Scoped preview, private storage, automatic retention service and agent spool cleanup, tests. Production encryption/ACLs and privacy policy pending. | 1 partial; 5 |

## Phase milestones

1. **Foundation:** monorepo, Docker development definition, PostgreSQL-compatible frozen migration, PDF upload/count, local SQLite agent, simulated B/W output and runnable full demo. Native SQLite execution tested. PostgreSQL execution is assigned to CI until a Docker-capable host is available.
2. **QR portal:** Next.js application, stable printed QR, previews/thumbnails, sandboxed DOCX conversion, improved mobile flow and quote expiry/retry UX.
3. **Payment:** selected Uganda-compatible gateway sandbox, provider-controlled PIN prompt, authenticated callbacks, independent API verification, reconciliation scheduler, settlement checks and supported refund adapter.
4. **Kiosk/offline:** React kiosk, restricted USB importer/OS lockdown, local FastAPI authority, SQLite offline state and full cloud sync, local Wi-Fi, admin roles/config/recovery.
5. **Pilot:** actual hardware and telemetry, monitored jams/outages, financial/physical reconciliation, privacy/restoration review and gated go-live.

## Blueprint acceptance cases (section 13)

| Case | Phase 1 evidence / pending |
|---|---|
| 15 pages × 2 = 30 sides / 6,000 UGX / 16 duplex sheets | End-to-end test and live demo script |
| 29 vs 30 threshold | Parameterized test; business approval explicitly outstanding |
| DOCX actual pages and range/copies | PDF ranges/copies tested; DOCX deferred |
| Unsupported colour/duplex blocked | API capability validation; seeded printer rejects colour; UI disables colour |
| Empty/offline/jam/unknown bulk blocks payment | Parameterized readiness, stale heartbeat and bulk tests |
| Duplicate webhook only one paid/dispatch | Signed callback replay, event counts and concurrent claim tests |
| Pending/failed/spoof/wrong amount cannot print | Separate provider-ledger and mismatch tests |
| Restart during printing becomes uncertain | Restart and lease-expiry tests; no redispatch |
| QR and kiosk share lifecycle/status | Demo browser uses canonical APIs; QR and USB UI pending |
| Local Wi-Fi/USB offline; no false offline payment | Outbox replay tested; full offline portal/import pending |
| Admin tier changes preserve paid quote | Snapshot invariance tested by fixture mutation; authorized editing UI/API pending |
| Session privacy and deletion | Cross-session preview and expired on-disk deletion tests |
| Outage/retry/backlog/100+ pages/recovery E2E | Payment retry, outbox, readiness recovery, 100-side and multiple-job tests; full hardware pilot pending |

## Additional production requirements retained

- Gateway minimum transaction limits, fees, settlement rules, reversals, refunds and final approved prices.
- Stronger device telemetry confidence, paper reservation/queue accounting and explicit operator acknowledgement where unknown.
- Sandboxed LibreOffice conversion, zip-bomb/macro/path/resource protection and conversion warnings.
- Role-based salted password authentication (Argon2/bcrypt), expiry, rotation, optional MFA, audit of staff actions.
- External TLS, CORS allowlist if clients separate origins, signed short-lived downloads and shared rate limiting. Cookie-based sessions must add CSRF protection if introduced.
- Authenticated outbound station connectivity; private printers/local agent; secure Wi-Fi routing and local TLS plan.
- Idempotent cloud sync with stable event IDs, conflicts, duplicate handling and clock-skew strategy.
- Managed service deployment, queue/conversion/payment/print/settlement metrics, backups and tested restoration.
- Physical cabinet, UPS/surge protection, protected cable/USB extension, safe output tray and support policy.
- Real-device completion evidence distinct from spool acceptance; double-refund and approved reprint prevention.

Cash, physical card acceptors, scanning/photocopying, arbitrary remote printers and mandatory student accounts remain outside the first-release scope, matching the source.
