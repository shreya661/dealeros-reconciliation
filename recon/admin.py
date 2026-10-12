from django.contrib import admin
from recon.models import Location, SystemARecord, SystemBEntry


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("location_id", "org_id", "location_name")
    list_filter = ("org_id",)
    search_fields = ("location_id", "location_name", "org_id")


@admin.register(SystemARecord)
class SystemARecordAdmin(admin.ModelAdmin):
    list_display = ("record_id", "location", "event_date", "total_value", "state")
    list_filter = ("state", "location__org_id")
    search_fields = ("record_id", "actor_id")


@admin.register(SystemBEntry)
class SystemBEntryAdmin(admin.ModelAdmin):
    list_display = ("entry_id", "record_ref_norm", "location", "recorded_on", "value")
    list_filter = ("location__org_id",)
    search_fields = ("entry_id", "record_ref_norm", "record_ref_raw")
