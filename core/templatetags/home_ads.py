import re

from django import template
from django.conf import settings


register = template.Library()

HOME_SLOTS = {
    "logistics": "ADSENSE_LOGISTICS_HOME_SLOT",
    "realtor": "ADSENSE_REALTOR_HOME_SLOT",
}


@register.inclusion_tag("core/includes/home_ad.html")
def home_ad(subject_code):
    """Render one manual unit on an explicitly selected learning home only."""
    slot_setting = HOME_SLOTS.get(subject_code)
    client_id = getattr(settings, "ADSENSE_CLIENT_ID", "")
    slot_id = getattr(settings, slot_setting, "") if slot_setting else ""
    enabled = (
        getattr(settings, "ADSENSE_ENABLED", False)
        and re.fullmatch(r"ca-pub-\d{16}", client_id)
        and re.fullmatch(r"\d+", slot_id)
    )
    return {"ad_client": client_id if enabled else "", "ad_slot": slot_id if enabled else ""}
