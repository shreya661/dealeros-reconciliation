# Architectural & Domain Decisions (DECISIONS)

### 1. Split Payments vs. Duplicate Entries (`REC-1055`)
- **Decision**: Treat multi-part entries in System B whose sum equals System A's total value as an **Agreement** (non-error) rather than a duplicate or value mismatch.
- **Alternative rejected**: Blindly flagging any record with more than one System B entry as a `DUPLICATE_IN_B`.
- **Reasoning**: In dealership and accounting workflows, split payments (e.g., partial deposits, split financing) represent valid business operations; failing to sum them produces false alarms on healthy accounts.

---

### 2. Cross-Tenant Location Discrepancy & Boundary Protection (`REC-1077`)
- **Decision**: Surface `REC-1077` to Org A with System B's location masked as `[External Organization]`.
- **Alternative rejected**: Exposing Org B's internal location ID (`LOC-201`) to Org A, or hiding the record from Org A completely.
- **Reasoning**: Org A must know their transaction has an external reconciliation conflict, but strict tenant boundaries dictate that another organization's internal identifiers must never leak across the perimeter.

---

### 3. Dual-Column Data Model (Raw vs. Normalized)
- **Decision**: Store both the raw input string (`raw_value`, `record_ref_raw`) and the sanitized/parsed value (`value`, `record_ref_norm`) in the database.
- **Alternative rejected**: Destructively transforming data in-place during import, or dropping rows with invalid numbers like `REC-1050`.
- **Reasoning**: In reconciliation systems, 100% row survival and auditability are non-negotiable; preserving original inputs allows debugging corrupt exports without data loss.

---

### 4. Canonical Reference Normalization via Regex
- **Decision**: Normalize messy identifiers (`rec1034`, ` REC - 1070 `, `1112`) using regex numeric extraction to format `REC-{digits}`.
- **Alternative rejected**: Exact string joins or manual exception dictionaries.
- **Reasoning**: Real dealership software exports contain arbitrary whitespace and casing typos; extracting the underlying numeric key is deterministic and scalable.

---

### 5. Date-Only Differences as an Isolated Low-Severity Category (`REC-1009`)
- **Decision**: Flag date differences between `event_date` and `recorded_on` as a distinct category (`DATE_MISMATCH`) rather than a monetary failure.
- **Alternative rejected**: Ignoring date differences entirely, or grouping them into value mismatches.
- **Reasoning**: Event recording often spans a weekend or billing cycle close (e.g., March 31 vs April 2); categorizing timing differences separately allows operators to prioritize actual cash discrepancies.

---

### 6. Preserving Voided Transactions (`REC-1019`)
- **Decision**: Import and reconcile `VOIDED` records in System A against System B entries while persisting their lifecycle state.
- **Alternative rejected**: Silently filtering out voided records during data ingestion.
- **Reasoning**: System B still recorded a matching monetary entry for `REC-1019`, making it critical for auditors to see if funds were captured against a voided agreement.
