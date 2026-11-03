# External integrations needed

## Printer

Supply model/firmware, station OS, USB/network connection, IPP URI or CUPS queue, supported A4/colour/duplex combinations, and access to a test device. Validate IPP attributes, paper/toner/jam telemetry and whether completion proves physical output. Missing readings must stay UNKNOWN. `PrinterAdapter` defines readiness, submit and status; `SimulatedPrinter` is executable and `CupsPrinter` fails explicitly. Add real adapter contract tests with captured device responses before enabling it. Validate grayscale rendering and A4 scaling; simulated PDFs preserve content and annotate requested B/W rather than performing a colour transform.

## MTN / Airtel Uganda

Select a gateway with documented support for both networks in Uganda. Supply current official API and webhook security documentation, sandbox merchant account/credentials, server callback URL, independent transaction lookup, amount/currency/reference guarantees, minimum amount/fees, settlement and supported refunds/reversals. Do not invent endpoints. The `PaymentProvider` protocol names initiate_charge, verify_transaction, parse_verified_webhook, query_status and refund. The tested mock implements all except refund, which explicitly raises until the authorized workflow is built. Production must never use the mock ledger/HMAC convention as if it were a provider's protocol.

Z-PRINT never collects a PIN. Phone syntax accepts +2567XXXXXXXX; real provider/carrier compatibility and ported-number rules must come from provider docs. General logs do not contain full phone numbers; database attempts keep masked numbers. Live initiation will need a narrowly scoped, encrypted/transient phone handling policy.

## USB and offline

Supply kiosk OS, removable-media device policy, display/input type, enclosure layout, local Wi-Fi topology and DNS/TLS design. Implement import only from approved mounted USB roots with path containment, no executable mount/autorun, PDF/DOCX filters and isolated copies. A normal browser file chooser is not a locked USB kiosk. Add session inactivity reset, safe eject and content wipe. New offline Mobile Money charges remain prohibited; prepaid credit requires an authenticated accounting design.

## Before enabling public users

Approve actual prices, copy/page limits, minimum charge, refund/support policy, dispute retention, privacy notice, domain and certificate provisioning. Replace admin key with role-based staff auth; provision per-device rotated credentials. Complete document sandbox hardening and dependency review. Confirm backup restoration, monitoring and operator handling of uncertain prints. Phase 1 rejects non-demo startup on purpose.
