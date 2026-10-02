# Ecosystem contract schemas (vendored, do not edit here)

These JSON Schemas are **generated** in the ecosystem's single contract source,
`coolman1984/GMES` → `packages/eco-contracts` (`npm run schemas`), and copied here unchanged so
this Python application can validate what it publishes without any third-party library.

A GMES end-to-end test compares these files byte for byte with the generated ones: if a contract
changes there and not here, that test fails (contract drift is caught, never discovered at a customer).

| Schema | Meaning | Owner |
|---|---|---|
| `eco.envelope.v1` | The CloudEvents-compatible envelope every ecosystem event travels in | ecosystem |
| `eco.employee.v1` | Workforce master data (no personal data) | **HR-System** |
| `eco.attendance_day.v1` | One employee's attendance for one work day | **HR-System** |
| `eco.schedule_day.v1` | One employee's planned day (shift, times, rest day or leave), published today and 13 days ahead | **HR-System** |
| `eco.qualification.v1` | One person's qualification for a skill (level, certified, expiry; a withdrawn one is inactive) | **HR-System** |
| `hr.payroll_period.v1` | One month's pay as totals per cost centre and account key (no names), approved and sent to Mizan, or reversed | **HR-System** |
| `canonical-v1.json` | Shared test vectors: canonical JSON and journal-line hash (ADR-026); must pass in Python and TypeScript | ecosystem |
