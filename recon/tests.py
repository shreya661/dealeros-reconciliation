from decimal import Decimal
from django.test import TestCase

from recon.models import Location, SystemARecord, SystemBEntry
from recon.services import DiscrepancyReason, reconcile


class ReconciliationLogicTests(TestCase):
    def setUp(self):
        # Create Locations for two tenants
        self.loc_a1 = Location.objects.create(location_id="LOC-101", org_id="ORG-A", location_name="HQ North")
        self.loc_a2 = Location.objects.create(location_id="LOC-102", org_id="ORG-A", location_name="HQ South")
        self.loc_b1 = Location.objects.create(location_id="LOC-201", org_id="ORG-B", location_name="East Branch")

    def test_missing_in_b(self):
        """
        Catches a record in System A that has zero entries in System B.
        """
        SystemARecord.objects.create(
            record_id="REC-9001",
            location=self.loc_a1,
            raw_location_id="LOC-101",
            total_value=Decimal("500.00"),
            event_date="2026-03-01",
        )
        discrepancies = reconcile(org_id="ORG-A")
        match = [d for d in discrepancies if d["record_id"] == "REC-9001"]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["reason"], DiscrepancyReason.MISSING_IN_B)

    def test_orphan_in_b(self):
        """
        Catches a System B entry pointing at a record_ref that does not exist in System A.
        """
        SystemBEntry.objects.create(
            entry_id="ENT-9001",
            record_ref_raw="REC-9999",
            record_ref_norm="REC-9999",
            location=self.loc_a1,
            raw_location_id="LOC-101",
            value=Decimal("750.00"),
        )
        discrepancies = reconcile(org_id="ORG-A")
        match = [d for d in discrepancies if d["record_id"] == "REC-9999"]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["reason"], DiscrepancyReason.ORPHAN_IN_B)

    def test_duplicate_in_b(self):
        """
        Catches duplicate entries in System B for the same record (not a split).
        """
        SystemARecord.objects.create(
            record_id="REC-9002",
            location=self.loc_a1,
            raw_location_id="LOC-101",
            total_value=Decimal("1000.00"),
        )
        SystemBEntry.objects.create(
            entry_id="ENT-9002-1",
            record_ref_raw="REC-9002",
            record_ref_norm="REC-9002",
            location=self.loc_a1,
            raw_location_id="LOC-101",
            value=Decimal("1000.00"),
            label="Original Entry",
        )
        SystemBEntry.objects.create(
            entry_id="ENT-9002-2",
            record_ref_raw="REC-9002",
            record_ref_norm="REC-9002",
            location=self.loc_a1,
            raw_location_id="LOC-101",
            value=Decimal("1000.00"),
            label="Original Entry Duplicate",
        )
        discrepancies = reconcile(org_id="ORG-A")
        match = [d for d in discrepancies if d["record_id"] == "REC-9002"]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["reason"], DiscrepancyReason.DUPLICATE_IN_B)

    def test_split_entry_agreement_non_error(self):
        """
        Verifies the 'non-error': when multiple entries in B represent split parts
        whose sum matches System A's total, it is treated as an AGREEMENT, not an error.
        """
        SystemARecord.objects.create(
            record_id="REC-9003",
            location=self.loc_a1,
            raw_location_id="LOC-101",
            total_value=Decimal("1500.00"),
        )
        SystemBEntry.objects.create(
            entry_id="ENT-9003-1",
            record_ref_raw="REC-9003",
            record_ref_norm="REC-9003",
            location=self.loc_a1,
            raw_location_id="LOC-101",
            value=Decimal("900.00"),
            label="Payment Part 1 of 2",
        )
        SystemBEntry.objects.create(
            entry_id="ENT-9003-2",
            record_ref_raw="REC-9003",
            record_ref_norm="REC-9003",
            location=self.loc_a1,
            raw_location_id="LOC-101",
            value=Decimal("600.00"),
            label="Payment Part 2 of 2",
        )
        discrepancies = reconcile(org_id="ORG-A")
        match = [d for d in discrepancies if d["record_id"] == "REC-9003"]
        self.assertEqual(len(match), 0, "Split parts summing to A total must count as agreement.")

    def test_value_mismatch(self):
        """
        Catches when System A and System B report different values.
        """
        SystemARecord.objects.create(
            record_id="REC-9004",
            location=self.loc_a1,
            raw_location_id="LOC-101",
            total_value=Decimal("1200.00"),
        )
        SystemBEntry.objects.create(
            entry_id="ENT-9004",
            record_ref_raw="REC-9004",
            record_ref_norm="REC-9004",
            location=self.loc_a1,
            raw_location_id="LOC-101",
            value=Decimal("950.00"),
        )
        discrepancies = reconcile(org_id="ORG-A")
        match = [d for d in discrepancies if d["record_id"] == "REC-9004"]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["reason"], DiscrepancyReason.VALUE_MISMATCH)
        self.assertEqual(match[0]["diff"], Decimal("250.00"))

    def test_blank_value_in_b(self):
        """
        Catches unparseable or blank values in System B without crashing.
        """
        SystemARecord.objects.create(
            record_id="REC-9005",
            location=self.loc_a1,
            raw_location_id="LOC-101",
            total_value=Decimal("800.00"),
        )
        SystemBEntry.objects.create(
            entry_id="ENT-9005",
            record_ref_raw="REC-9005",
            record_ref_norm="REC-9005",
            location=self.loc_a1,
            raw_location_id="LOC-101",
            value=None,  # Blank / unparseable
            raw_value="",
        )
        discrepancies = reconcile(org_id="ORG-A")
        match = [d for d in discrepancies if d["record_id"] == "REC-9005"]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["reason"], DiscrepancyReason.VALUE_MISMATCH)

    def test_location_mismatch_and_tenant_masking(self):
        """
        Catches location discrepancy across systems and ensures foreign tenant ID is masked.
        """
        SystemARecord.objects.create(
            record_id="REC-9006",
            location=self.loc_a1,
            raw_location_id="LOC-101",
            total_value=Decimal("500.00"),
        )
        SystemBEntry.objects.create(
            entry_id="ENT-9006",
            record_ref_raw="REC-9006",
            record_ref_norm="REC-9006",
            location=self.loc_b1,  # Belongs to ORG-B!
            raw_location_id="LOC-201",
            value=Decimal("500.00"),
        )
        discrepancies = reconcile(org_id="ORG-A")
        match = [d for d in discrepancies if d["record_id"] == "REC-9006" and d["reason"] == DiscrepancyReason.LOCATION_MISMATCH]
        self.assertEqual(len(match), 1)
        # Verify tenant protection: ORG-B location is masked
        self.assertEqual(match[0]["location_b"], "[External Organization]")

    def test_date_mismatch(self):
        """
        Catches differences between System A event_date and System B recorded_on.
        """
        SystemARecord.objects.create(
            record_id="REC-9007",
            location=self.loc_a1,
            raw_location_id="LOC-101",
            total_value=Decimal("500.00"),
            event_date="2026-03-10",
        )
        SystemBEntry.objects.create(
            entry_id="ENT-9007",
            record_ref_raw="REC-9007",
            record_ref_norm="REC-9007",
            location=self.loc_a1,
            raw_location_id="LOC-101",
            value=Decimal("500.00"),
            recorded_on="2026-03-12",
        )
        discrepancies = reconcile(org_id="ORG-A")
        match = [d for d in discrepancies if d["record_id"] == "REC-9007" and d["reason"] == DiscrepancyReason.DATE_MISMATCH]
        self.assertEqual(len(match), 1)

    def test_strict_tenant_isolation(self):
        """
        Ensures a tenant cannot see another tenant's discrepancies.
        """
        SystemARecord.objects.create(
            record_id="REC-A-EXCLUSIVE",
            location=self.loc_a1,
            raw_location_id="LOC-101",
            total_value=Decimal("100.00"),
        )
        SystemARecord.objects.create(
            record_id="REC-B-EXCLUSIVE",
            location=self.loc_b1,
            raw_location_id="LOC-201",
            total_value=Decimal("200.00"),
        )
        disc_a = reconcile(org_id="ORG-A")
        disc_b = reconcile(org_id="ORG-B")

        records_seen_by_a = {d["record_id"] for d in disc_a}
        records_seen_by_b = {d["record_id"] for d in disc_b}

        self.assertIn("REC-A-EXCLUSIVE", records_seen_by_a)
        self.assertNotIn("REC-B-EXCLUSIVE", records_seen_by_a)
        self.assertIn("REC-B-EXCLUSIVE", records_seen_by_b)
        self.assertNotIn("REC-A-EXCLUSIVE", records_seen_by_b)
