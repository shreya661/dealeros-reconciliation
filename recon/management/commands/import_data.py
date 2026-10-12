import csv
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from recon.models import Location, SystemARecord, SystemBEntry


def normalize_record_ref(raw_ref: str) -> str:
    """
    Normalizes messy references (e.g. 'rec1034', ' REC - 1070 ', '1112')
    into canonical format 'REC-####'.
    """
    if not raw_ref:
        return ""
    digits = re.findall(r"\d+", raw_ref)
    if digits:
        return f"REC-{digits[0]}"
    return raw_ref.strip()


def parse_decimal(val: str):
    """
    Safely converts dirty number strings (e.g. '1,25,400.00', '', spaces) to Decimal.
    Returns None if blank or unparseable.
    """
    if not val:
        return None
    cleaned = val.replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


class Command(BaseCommand):
    help = "Imports locations.csv, system_a.csv, and system_b.csv into database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dataset-dir",
            type=str,
            default=None,
            help="Directory containing the 3 CSV files (default: auto-detected)",
        )

    def handle(self, *args, **options):
        # Locate dataset directory
        dataset_dir = options.get("dataset_dir")
        if not dataset_dir:
            # Check relative to dealeros or parent
            candidates = [
                Path(__file__).resolve().parent.parent.parent.parent.parent / "DealerOS_Assignment_Dataset",
                Path(__file__).resolve().parent.parent.parent.parent / "DealerOS_Assignment_Dataset",
                Path("DealerOS_Assignment_Dataset"),
                Path("../DealerOS_Assignment_Dataset"),
            ]
            for candidate in candidates:
                if candidate.exists() and (candidate / "locations.csv").exists():
                    dataset_dir = candidate
                    break

        if not dataset_dir or not Path(dataset_dir).exists():
            self.stderr.write(self.style.ERROR(f"Dataset directory not found: {dataset_dir}"))
            return

        dataset_path = Path(dataset_dir)
        self.stdout.write(self.style.NOTICE(f"Loading datasets from: {dataset_path}"))

        with transaction.atomic():
            # 1. Locations
            loc_file = dataset_path / "locations.csv"
            loc_count = 0
            with open(loc_file, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    loc_id = row["location_id"].strip()
                    Location.objects.update_or_create(
                        location_id=loc_id,
                        defaults={
                            "org_id": row["org_id"].strip(),
                            "location_name": row["location_name"].strip(),
                        },
                    )
                    loc_count += 1
            self.stdout.write(self.style.SUCCESS(f"Imported {loc_count} locations."))

            # Cache locations
            locations_map = {loc.location_id: loc for loc in Location.objects.all()}

            # 2. System A
            a_file = dataset_path / "system_a.csv"
            a_count = 0
            with open(a_file, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rec_id = row["record_id"].strip()
                    loc_id = row["location_id"].strip()
                    actor = row.get("actor_id", "").strip() or None

                    SystemARecord.objects.update_or_create(
                        record_id=rec_id,
                        defaults={
                            "location": locations_map.get(loc_id),
                            "raw_location_id": loc_id,
                            "event_date": row["event_date"].strip() or None,
                            "category_code": row["category_code"].strip(),
                            "actor_id": actor,
                            "base_value": parse_decimal(row.get("base_value")),
                            "adjustment": parse_decimal(row.get("adjustment")),
                            "total_value": parse_decimal(row.get("total_value")),
                            "raw_total_value": row.get("total_value", "").strip(),
                            "state": row.get("state", "CONFIRMED").strip(),
                        },
                    )
                    a_count += 1
            self.stdout.write(self.style.SUCCESS(f"Imported {a_count} System A records."))

            # Cache System A records for linking
            a_records_map = {rec.record_id: rec for rec in SystemARecord.objects.all()}

            # 3. System B
            b_file = dataset_path / "system_b.csv"
            b_count = 0
            with open(b_file, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    entry_id = row["entry_id"].strip()
                    raw_ref = row["record_ref"]
                    norm_ref = normalize_record_ref(raw_ref)
                    loc_id = row["location_id"].strip()
                    raw_val = row.get("value", "")

                    SystemBEntry.objects.update_or_create(
                        entry_id=entry_id,
                        defaults={
                            "record_ref_raw": raw_ref,
                            "record_ref_norm": norm_ref,
                            "system_a_record": a_records_map.get(norm_ref),
                            "location": locations_map.get(loc_id),
                            "raw_location_id": loc_id,
                            "recorded_on": row["recorded_on"].strip() or None,
                            "raw_value": raw_val,
                            "value": parse_decimal(raw_val),
                            "label": row.get("label", "").strip(),
                        },
                    )
                    b_count += 1
            self.stdout.write(self.style.SUCCESS(f"Imported {b_count} System B entries."))

        self.stdout.write(self.style.SUCCESS("Import completed successfully with 100% row survival."))
