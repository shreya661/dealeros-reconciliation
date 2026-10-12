# DealerOS — Multi-Tenant Event Reconciliation System

A resilient, multi-tenant reconciliation service built with **Django** that compares disparate event exports (`System A` vs. `System B`), isolates tenant boundaries (`locations.csv`), and surfaces discrepancies with zero silent data loss.

---

## 1. How to Run It (From a Clean Clone)

### Prerequisites
- Python 3.10+ (tested with Python 3.12)
- Virtual environment or standard Python installation

### Setup & Launch
```bash
# 1. Clone repository & navigate to directory
cd dealeros

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run database migrations (creates SQLite tables)
python manage.py migrate

# 4. Ingest and normalize raw dataset (zero row loss)
python manage.py import_data

# 5. Run the test suite
python manage.py test recon

# 6. Start the local server
python manage.py runserver
```

Open your browser at **`http://127.0.0.1:8000/`** to view the interactive reconciliation dashboard.  
JSON API endpoint: **`http://127.0.0.1:8000/api/reconciliation/?org_id=ORG-A`**

---

## 2. What Was Built

### Core Engineering & Data Ingestion
- **Resilient Data Models (`recon/models.py`)**: Stores both raw inputs (`raw_value`, `record_ref_raw`, `raw_location_id`) and sanitized values (`value`, `record_ref_norm`, foreign keys).
- **Zero-Loss Data Importer (`recon/management/commands/import_data.py`)**: 
  - Sanitizes dirty reference strings (`rec1034`, ` REC - 1070 `, `1112` $\rightarrow$ `REC-####`).
  - Converts international number notation (`1,25,400.00` $\rightarrow$ `Decimal('125400.00')`).
  - Safely handles blank values (`""` $\rightarrow$ `None`) without dropping records (`REC-1050`).
  - 100% of rows from all 3 CSVs survive ingestion.

### Comparison Engine (`recon/services.py`)
- **Missing in B**: System A records with zero matching entries (`REC-1015`, `REC-1061`).
- **Orphan in B**: System B entries referencing non-existent records (`REC-1999`).
- **True Duplicate in B**: Catches duplicate entries (`REC-1042`).
- **Split Payment Agreement (The "Non-Error")**: Recognizes when multiple System B entries sum to System A's total (`REC-1055`), treating it as an agreement rather than an error.
- **Value Mismatches**: Catches numerical divergences and blank values.
- **Tenant Boundary Protection**: Isolates records by tenant (`ORG-A` vs `ORG-B`). When a cross-tenant location discrepancy occurs (`REC-1077`), the foreign location identifier is masked to prevent cross-tenant data leakage.

### Reconciliation Screen (`recon/views.py` & templates)
- Plain, responsive table listing every disagreement, discrepancy reason, values from both systems, locations, and calculated difference.
- **Tenant Switcher**: Switch between `ORG-A`, `ORG-B`, and multi-tenant admin view.
- **Filters & Sorting**: Filter by reason and sort ascending/descending by value difference.

### Test Suite (`recon/tests.py`)
- 9 isolated unit tests covering every single discrepancy category and tenant isolation guarantee.

---

## 3. What Was Deliberately Not Built

As outlined in the brief's guidance on scope:
1. **User Authentication & Permission Systems**: Tenant switching is demonstrated via a parameter/dropdown rather than full JWT/session auth.
2. **Heavy Frontend Framework / Complex CSS**: Used a clean, semantic HTML5 table with vanilla CSS rather than a bloated single-page app framework.
3. **Write-Back / Dispute Resolution Engine**: Focus was kept strictly on reconciliation detection rather than building a bidirectional ledger resolution workflow.
4. **Performance Micro-optimizations**: The dataset is 120 rows; in-memory comparison in Python services was chosen over complex SQL window functions to optimize readability and maintainability.

---

## 4. How I Worked with the Agent

I used the AI agent as a pair-programming collaborator for scaffolding boilerplate, exploratory inspection of edge cases in the dataset, and generating test fixtures. I directed the architecture, audited the comparison logic, verified edge cases against domain realities, and iteratively refined the codebase.

---

## 5. Evaluation Questions

### a. Name one thing the AI agent got wrong. How did you notice?
When initially writing the comparison logic, the agent proposed flagging every record with more than one System B entry as a `DUPLICATE_IN_B`. I noticed that `REC-1055` had two entries (`71,950.93` and `107,926.39`) that summed exactly to System A's `179,877.32` and were explicitly labeled as split parts. I caught that this was the deliberate "non-error" mentioned in the rubric and redirected the agent to treat matching split payments as valid agreements. Additionally, the agent's initial extraction command used Linux `unzip`, which crashed on Windows, requiring a switch to Python's cross-platform `zipfile` module.

### b. Which part of your submission are you least confident about, and why?
The exact product semantics around cross-tenant conflicts like `REC-1077`. In our implementation, Org A sees the discrepancy with Org B's location masked (`[External Organization]`) to prevent data leakage. However, when Org B logs in, they have a System B entry with no corresponding System A record in their scope. Whether Org B should see this as an orphan or whether a shared cross-tenant dispute queue is required is a product requirement that needs business clarification.

### c. If you had a second day, what would you fix first?
I would build an asynchronous ingestion pipeline (using Celery or Django background tasks) with file upload endpoints in the UI so operators can upload fresh daily CSV exports directly through the browser. Second, I would add a "Resolve Discrepancy" action that logs manual accountant sign-offs to a persistent audit trail.
