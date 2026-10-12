from decimal import Decimal
from typing import Dict, List, Optional
from collections import defaultdict

from recon.models import Location, SystemARecord, SystemBEntry


class DiscrepancyReason:
    MISSING_IN_B = "MISSING_IN_B"
    ORPHAN_IN_B = "ORPHAN_IN_B"
    DUPLICATE_IN_B = "DUPLICATE_IN_B"
    VALUE_MISMATCH = "VALUE_MISMATCH"
    LOCATION_MISMATCH = "LOCATION_MISMATCH"
    DATE_MISMATCH = "DATE_MISMATCH"


def get_tenant_locations(org_id: Optional[str]) -> Dict[str, Location]:
    """
    Returns a dict mapping location_id -> Location object.
    If org_id is provided, only returns locations for that tenant.
    """
    qs = Location.objects.all()
    if org_id:
        qs = qs.filter(org_id=org_id)
    return {loc.location_id: loc for loc in qs}


def reconcile(org_id: Optional[str] = None) -> List[Dict]:
    """
    Core reconciliation engine.
    Matches System A records against System B entries and detects discrepancies.
    Respects strict tenant isolation when org_id is provided.
    """
    all_locations = {loc.location_id: loc for loc in Location.objects.all()}
    tenant_locations = get_tenant_locations(org_id)
    tenant_loc_ids = set(tenant_locations.keys())

    # Query records
    a_qs = SystemARecord.objects.select_related("location").all()
    b_qs = SystemBEntry.objects.select_related("location").all()

    # Filter by tenant if org_id is specified
    if org_id:
        a_records = [r for r in a_qs if r.raw_location_id in tenant_loc_ids]
        b_entries = [e for e in b_qs if e.raw_location_id in tenant_loc_ids]
    else:
        a_records = list(a_qs)
        b_entries = list(b_qs)

    # Group B entries by normalized reference
    # Also fetch all B entries across database to check if an A record was logged in another org's B
    b_by_ref = defaultdict(list)
    for entry in b_qs:
        b_by_ref[entry.record_ref_norm].append(entry)

    discrepancies = []

    # 1. Evaluate System A records belonging to this tenant
    for a_rec in a_records:
        rec_id = a_rec.record_id
        matching_b = b_by_ref.get(rec_id, [])

        # Case: A record with no entry in B at all
        if not matching_b:
            discrepancies.append({
                "record_id": rec_id,
                "reason": DiscrepancyReason.MISSING_IN_B,
                "summary": "Record exists in System A but has no entries in System B",
                "org_id": a_rec.location.org_id if a_rec.location else "UNKNOWN",
                "location_a": a_rec.raw_location_id,
                "location_b": "-",
                "value_a": a_rec.total_value,
                "value_b": None,
                "diff": a_rec.total_value,
                "date_a": str(a_rec.event_date) if a_rec.event_date else "-",
                "date_b": "-",
                "details": "No matching record_ref found in System B entries."
            })
            continue

        # Check for split entries vs true duplicates
        is_split = False
        if len(matching_b) > 1:
            # Check if labels indicate a multi-part/split payment
            has_split_label = any("part" in (b.label or "").lower() for b in matching_b)
            # Sum up valid values
            has_unparseable_value = any(b.value is None for b in matching_b)
            if not has_unparseable_value:
                b_sum = sum(b.value for b in matching_b)
                if a_rec.total_value is not None and abs(b_sum - a_rec.total_value) <= Decimal("0.01"):
                    is_split = True

        # Case: True Duplicate in B (more than 1 entry and not a valid matching split)
        if len(matching_b) > 1 and not is_split:
            b_total = sum((b.value or Decimal("0.00")) for b in matching_b)
            discrepancies.append({
                "record_id": rec_id,
                "reason": DiscrepancyReason.DUPLICATE_IN_B,
                "summary": f"System B contains {len(matching_b)} conflicting entries for this record",
                "org_id": a_rec.location.org_id if a_rec.location else "UNKNOWN",
                "location_a": a_rec.raw_location_id,
                "location_b": ", ".join(b.raw_location_id for b in matching_b),
                "value_a": a_rec.total_value,
                "value_b": b_total,
                "diff": abs((a_rec.total_value or Decimal("0.00")) - b_total),
                "date_a": str(a_rec.event_date) if a_rec.event_date else "-",
                "date_b": ", ".join(str(b.recorded_on or "-") for b in matching_b),
                "details": f"Entries: {', '.join(b.entry_id for b in matching_b)}"
            })
            continue

        # If it's a split entry that sums to A's total, this is an AGREEMENT (non-error)
        if is_split:
            # Check location agreement across split entries
            pass

        # Calculate B value for comparison
        b_sum = sum((b.value or Decimal("0.00")) for b in matching_b)
        has_blank_or_invalid_b = any(b.value is None for b in matching_b)

        # Case: Value mismatch or blank/unparseable value
        if has_blank_or_invalid_b or (a_rec.total_value is not None and abs(b_sum - a_rec.total_value) > Decimal("0.01")):
            detail_msg = "Unparseable or blank value in System B" if has_blank_or_invalid_b else f"System A: {a_rec.total_value} vs System B sum: {b_sum}"
            discrepancies.append({
                "record_id": rec_id,
                "reason": DiscrepancyReason.VALUE_MISMATCH,
                "summary": "Reported values differ between systems",
                "org_id": a_rec.location.org_id if a_rec.location else "UNKNOWN",
                "location_a": a_rec.raw_location_id,
                "location_b": matching_b[0].raw_location_id if matching_b else "-",
                "value_a": a_rec.total_value,
                "value_b": b_sum if not has_blank_or_invalid_b else None,
                "diff": abs((a_rec.total_value or Decimal("0.00")) - b_sum) if not has_blank_or_invalid_b else a_rec.total_value,
                "date_a": str(a_rec.event_date) if a_rec.event_date else "-",
                "date_b": str(matching_b[0].recorded_on or "-") if matching_b else "-",
                "details": detail_msg
            })

        # Case: Location mismatch (Tenant Boundary Trap handling)
        first_b = matching_b[0]
        if a_rec.raw_location_id != first_b.raw_location_id:
            # Multi-tenant protection:
            # If B belongs to another tenant, mask the external tenant's location details
            b_loc_obj = all_locations.get(first_b.raw_location_id)
            is_cross_tenant = b_loc_obj and a_rec.location and (b_loc_obj.org_id != a_rec.location.org_id)

            masked_b_loc = "[External Organization]" if (org_id and is_cross_tenant) else first_b.raw_location_id
            discrepancies.append({
                "record_id": rec_id,
                "reason": DiscrepancyReason.LOCATION_MISMATCH,
                "summary": "Location mismatch between System A and System B",
                "org_id": a_rec.location.org_id if a_rec.location else "UNKNOWN",
                "location_a": a_rec.raw_location_id,
                "location_b": masked_b_loc,
                "value_a": a_rec.total_value,
                "value_b": b_sum if not has_blank_or_invalid_b else None,
                "diff": abs((a_rec.total_value or Decimal("0.00")) - b_sum) if not has_blank_or_invalid_b else Decimal("0.00"),
                "date_a": str(a_rec.event_date) if a_rec.event_date else "-",
                "date_b": str(first_b.recorded_on or "-"),
                "details": "Cross-tenant boundary discrepancy detected" if is_cross_tenant else f"System A: {a_rec.raw_location_id} vs System B: {first_b.raw_location_id}"
            })

        # Case: Date discrepancy
        if a_rec.event_date and first_b.recorded_on and a_rec.event_date != first_b.recorded_on:
            discrepancies.append({
                "record_id": rec_id,
                "reason": DiscrepancyReason.DATE_MISMATCH,
                "summary": "Event date in System A differs from recorded date in System B",
                "org_id": a_rec.location.org_id if a_rec.location else "UNKNOWN",
                "location_a": a_rec.raw_location_id,
                "location_b": first_b.raw_location_id,
                "value_a": a_rec.total_value,
                "value_b": b_sum if not has_blank_or_invalid_b else None,
                "diff": Decimal("0.00"),
                "date_a": str(a_rec.event_date),
                "date_b": str(first_b.recorded_on),
                "details": f"System A date: {a_rec.event_date} vs System B date: {first_b.recorded_on}"
            })

    # 2. Check for Orphan Entries in System B (B entry pointing at non-existent record in A)
    # Check entries belonging to this tenant
    a_all_ids = set(SystemARecord.objects.values_list("record_id", flat=True))
    for b_entry in b_entries:
        if b_entry.record_ref_norm not in a_all_ids:
            discrepancies.append({
                "record_id": b_entry.record_ref_norm or b_entry.record_ref_raw,
                "reason": DiscrepancyReason.ORPHAN_IN_B,
                "summary": "System B entry references a record that does not exist in System A",
                "org_id": b_entry.location.org_id if b_entry.location else "UNKNOWN",
                "location_a": "-",
                "location_b": b_entry.raw_location_id,
                "value_a": None,
                "value_b": b_entry.value,
                "diff": b_entry.value,
                "date_a": "-",
                "date_b": str(b_entry.recorded_on or "-"),
                "details": f"Entry ID: {b_entry.entry_id}, Raw Ref: '{b_entry.record_ref_raw}'"
            })

    return discrepancies
