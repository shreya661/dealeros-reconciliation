from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response

from recon.models import Location
from recon.services import DiscrepancyReason, reconcile


def reconciliation_view(request):
    """
    Renders the plain, functional reconciliation dashboard.
    Supports filtering by tenant (org_id), disagreement reason, and sorting by value.
    """
    org_id = request.GET.get("org_id", "ORG-A")
    reason = request.GET.get("reason", "")
    sort_by = request.GET.get("sort", "desc")  # 'asc' or 'desc'

    # Fetch discrepancies respecting tenant boundary
    discrepancies = reconcile(org_id=org_id if org_id != "ALL" else None)

    # Filter by reason
    if reason:
        discrepancies = [d for d in discrepancies if d["reason"] == reason]

    # Sort by value / diff
    def get_sort_key(item):
        val = item["diff"] or item["value_a"] or item["value_b"]
        return float(val) if val is not None else 0.0

    reverse_order = (sort_by == "desc")
    discrepancies.sort(key=get_sort_key, reverse=reverse_order)

    # Available tenants and reasons for filter dropdowns
    available_orgs = sorted(list(Location.objects.values_list("org_id", flat=True).distinct()))
    reasons = [
        DiscrepancyReason.VALUE_MISMATCH,
        DiscrepancyReason.MISSING_IN_B,
        DiscrepancyReason.ORPHAN_IN_B,
        DiscrepancyReason.DUPLICATE_IN_B,
        DiscrepancyReason.LOCATION_MISMATCH,
        DiscrepancyReason.DATE_MISMATCH,
    ]

    context = {
        "discrepancies": discrepancies,
        "selected_org": org_id,
        "selected_reason": reason,
        "selected_sort": sort_by,
        "available_orgs": available_orgs,
        "reasons": reasons,
        "total_count": len(discrepancies),
    }
    return render(request, "recon/reconciliation.html", context)


@api_view(["GET"])
def reconciliation_api(request):
    """
    JSON API endpoint for programmatic access.
    """
    org_id = request.GET.get("org_id")
    reason = request.GET.get("reason")
    sort_by = request.GET.get("sort", "desc")

    discrepancies = reconcile(org_id=org_id)

    if reason:
        discrepancies = [d for d in discrepancies if d["reason"] == reason]

    def get_sort_key(item):
        val = item["diff"] or item["value_a"] or item["value_b"]
        return float(val) if val is not None else 0.0

    discrepancies.sort(key=get_sort_key, reverse=(sort_by == "desc"))

    # Convert Decimals to string/float for JSON serialization
    for d in discrepancies:
        if d.get("value_a") is not None:
            d["value_a"] = str(d["value_a"])
        if d.get("value_b") is not None:
            d["value_b"] = str(d["value_b"])
        if d.get("diff") is not None:
            d["diff"] = str(d["diff"])

    return Response({
        "count": len(discrepancies),
        "org_id": org_id,
        "discrepancies": discrepancies
    })
