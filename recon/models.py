from django.db import models


class Location(models.Model):
    """
    Mapping of physical location to organization (tenant).
    Every location belongs to exactly one org.
    """
    location_id = models.CharField(max_length=50, primary_key=True)
    org_id = models.CharField(max_length=50, db_index=True)
    location_name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.location_name} ({self.location_id}) - {self.org_id}"


class SystemARecord(models.Model):
    """
    Events as recorded by System A.
    record_id is the primary identifier.
    """
    record_id = models.CharField(max_length=50, primary_key=True)
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="system_a_records"
    )
    raw_location_id = models.CharField(max_length=50, blank=True)
    event_date = models.DateField(null=True, blank=True)
    category_code = models.CharField(max_length=50, blank=True)
    actor_id = models.CharField(max_length=50, blank=True, null=True)
    base_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    adjustment = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    raw_total_value = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, default="CONFIRMED")

    def __str__(self):
        return f"SystemA {self.record_id} ({self.total_value})"


class SystemBEntry(models.Model):
    """
    Entries as recorded by System B.
    record_ref points back at System A (with dirty variations).
    Multiple B entries may exist for a single System A record.
    """
    entry_id = models.CharField(max_length=50, primary_key=True)
    record_ref_raw = models.CharField(max_length=100)
    record_ref_norm = models.CharField(max_length=100, db_index=True)
    system_a_record = models.ForeignKey(
        SystemARecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="system_b_entries"
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="system_b_entries"
    )
    raw_location_id = models.CharField(max_length=50, blank=True)
    recorded_on = models.DateField(null=True, blank=True)
    raw_value = models.CharField(max_length=100, blank=True)
    value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    label = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"SystemB {self.entry_id} -> {self.record_ref_norm} ({self.value})"
