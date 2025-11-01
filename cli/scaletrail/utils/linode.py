from typing import Any, Dict, List, Optional
import inquirer
from scaletrail.utils import formatting
from datetime import datetime, timezone


CONTINENT_CHOICES = [
    "North America",
    "Europe",
    "Asia",
    "South America",
    "Oceania",
    "Show all regions"
]

NORTH_AMERICA_LINODE_REGIONS = [
    "ca-central",
    "us-central",
    "us-east",
    "us-iad",
    "us-lax",
    "us-mia",
    "us-ord",
    "us-sea",
    "us-southeast",
    "us-west"
]

EUROPE_LINODE_REGIONS = [
    "de-fra-2",
    "es-mad",
    "eu-central",
    "eu-west",
    "fr-par",
    "gb-lon",
    "it-mil",
    "nl-ams",
    "se-sto"
]

ASIA_LINODE_REGIONS = [
    "ap-northeast",
    "ap-south",
    "ap-west",
    "id-cgk",
    "in-bom-2",
    "in-maa",
    "jp-osa",
    "jp-tyo-3",
    "sg-sin-2"
]

SOUTH_AMERICA_LINODE_REGIONS = [
    "br-gru"
]

OCEANIA_LINODE_REGIONS = [
    "au-mel",
    "ap-southeast"
]

CONTINENT_TO_REGIONS = {
    "North America": NORTH_AMERICA_LINODE_REGIONS,
    "Europe": EUROPE_LINODE_REGIONS,
    "Asia": ASIA_LINODE_REGIONS,
    "South America": SOUTH_AMERICA_LINODE_REGIONS,
    "Oceania": OCEANIA_LINODE_REGIONS,
}


def _pick_price(item: Dict[str, Any], region_id: str) -> Dict[str, float]:
    """
    Return {"hourly": x, "monthly": y} using region override if present,
    otherwise the base price.
    """
    base = item.get("price", {}) or {}
    hourly = base.get("hourly")
    monthly = base.get("monthly")

    for rp in item.get("region_prices", []) or []:
        if rp.get("id") == region_id:
            hourly = rp.get("hourly", hourly)
            monthly = rp.get("monthly", monthly)
            break
    return {"hourly": float(hourly), "monthly": float(monthly)}

def _pick_backup_price(item: Dict[str, Any], region_id: str) -> Optional[Dict[str, float]]:
    """
    Same as _pick_price but for the backups addon. Returns None if no backups addon.
    """
    backups = (item.get("addons") or {}).get("backups")
    if not backups:
        return None

    base = (backups.get("price") or {})
    hourly = base.get("hourly")
    monthly = base.get("monthly")

    for rp in backups.get("region_prices", []) or []:
        if rp.get("id") == region_id:
            hourly = rp.get("hourly", hourly)
            monthly = rp.get("monthly", monthly)
            break

    return {"hourly": float(hourly), "monthly": float(monthly)}

def choose_instance(instances: list, message: str = "Select a Linode plan for (env) TODO: add env name here for readability"):
    instances_sorted = sorted(instances, key=lambda x: x.get("price_monthly", 0))

    header = (
        f"{'Label':<18} | "
        f"{'Class':<9} | "
        f"{'Mem GB':>6} | "
        f"{'Disk GB':>7} | "
        f"{'Transfer GB':>11} | "
        f"{'Monthly':>10} | "
        f"{'Backups Monthly':>14}"
    )

    # Show header above the prompt
    print(header)
    print("-" * len(header))

    # python-inquirer expects choices as strings OR (name, value) tuples
    choices = [(formatting._row(inst), inst["id"]) for inst in instances_sorted]

    questions = [
        inquirer.List(
            "selected",
            message=message,
            choices=choices,
            carousel=True,  # supported in python-inquirer
        )
    ]
    answers = inquirer.prompt(questions)
    if not answers:
        return None

    selected_id = answers["selected"]
    # return full instance (not just id)
    return next((i for i in instances if i["id"] == selected_id), None)

def get_instances_for_region(resp: Dict[str, Any], region_id: str, 
                             include_classes: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Flatten the Linode types payload into a list of dicts with the right
    price for `region_id`. Optionally filter by class (e.g., ["standard","dedicated"]).
    """
    out: List[Dict[str, Any]] = []
    for itm in resp.get("data", []) or []:
        if include_classes and itm.get("class") not in include_classes:
            continue

        price = _pick_price(itm, region_id)
        backup_price = _pick_backup_price(itm, region_id)

        out.append({
            "id": itm.get("id"),
            "label": itm.get("label"),
            "class": itm.get("class"),
            "vcpus": itm.get("vcpus"),
            "memory_mb": itm.get("memory"),
            "disk_mb": itm.get("disk"),
            "transfer_gb": itm.get("transfer"),
            "gpus": itm.get("gpus"),
            "network_out_mbps": itm.get("network_out"),
            "price_hourly": price["hourly"],
            "price_monthly": price["monthly"],
            "backups_hourly": backup_price["hourly"] if backup_price else None,
            "backups_monthly": backup_price["monthly"] if backup_price else None,
        })
    return out


def choose_os(oses: List[Dict[str, Any]], message: str = "Select an operating system"):
    """
    Prompt the user to choose an operating system from the available Linode images.

    Params
    -------
    oses : list[dict]
        Output from `get_operating_systems_for_region()`.

    message : str
        The message to display in the selection prompt.

    Returns
    -------
    dict | None
        The full OS image dictionary for the selected choice, or None if cancelled.
    """
    if not oses:
        print("No operating systems available for this region.")
        return None

    # Construct readable names for the prompt
    choices = []
    for img in oses:
        vendor = img.get("vendor") or "Unknown"
        label = img.get("label") or img.get("id")
        desc = img.get("description") or ""
        eol_flag = " (EOL)" if img.get("deprecated") or img.get("eol") else ""
        choice_label = f"{vendor:<10} | {label:<25} {eol_flag} - {desc[:60]}"
        choices.append((choice_label.strip(), img["id"]))

    print(f"{'Vendor':<10} | {'Label':<25} | Description")
    print("-" * 80)

    questions = [
        inquirer.List(
            "selected",
            message=message,
            choices=choices,
            carousel=True,
        )
    ]

    answers = inquirer.prompt(questions)
    if not answers:
        return None

    selected_id = answers["selected"]
    return next((os for os in oses if os["id"] == selected_id), None)

def _parse_iso(dt: Optional[str]) -> Optional[datetime]:
    if not dt:
        return None
    # Linode returns e.g. "2025-10-01T04:00:00"
    try:
        # assume UTC if no TZ provided
        return datetime.fromisoformat(dt.replace("Z", "")).replace(tzinfo=timezone.utc)
    except Exception:
        return None

def _eol_has_passed(eol: Optional[str]) -> bool:
    dt = _parse_iso(eol)
    if not dt:
        return False
    return datetime.now(timezone.utc) >= dt

def get_operating_systems_for_region(
    images_resp: Dict[str, Any],
    region_id: str,
    include_vendors: Optional[List[str]] = None,
    public_only: bool = True,
    exclude_eol: bool = True,
    require_status_available: bool = True,
    required_capabilities: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Normalize/filter Linode Images (OSes) for a specific region.

    Parameters
    ----------
    images_resp : dict
        The parsed JSON payload from `GET /linode/images`.
        Expected: {"data": [ {image...}, ... ], "page": ..., "pages": ..., "results": ...}

    region_id : str
        Region slug (e.g., "us-east", "us-ord", "br-gru", "jp-tyo-3").

    include_vendors : list[str] | None
        If given, keep only images whose `vendor` (case-insensitive) is in this list.

    public_only : bool
        If True (default), only include images with `is_public == True`.

    exclude_eol : bool
        If True (default), exclude images that are deprecated *or* whose `eol` has passed.

    require_status_available : bool
        If True (default), include only images where `status == "available"`.

    required_capabilities : list[str] | None
        If provided, keep only images that include *all* these capabilities
        (e.g., ["cloud-init"]).

    Region filtering behavior
    -------------------------
    If the image has a non-empty `regions` array, we require `region_id` to be present.
    If `regions` is None or empty, we treat the image as globally available.

    Returns
    -------
    list[dict]
        Each dict includes at least:
        - id, label, vendor, description, size, created, updated
        - is_public, deprecated, eol (raw), eol_passed (bool)
        - regions (list | None), status, capabilities (list)
    """
    out: List[Dict[str, Any]] = []

    vendor_allow: Optional[set] = None
    if include_vendors:
        vendor_allow = {v.strip().lower() for v in include_vendors if v and v.strip()}

    need_caps: Optional[set] = None
    if required_capabilities:
        need_caps = {c.strip() for c in required_capabilities if c and c.strip()}

    for img in images_resp.get("data", []) or []:
        # public filter
        if public_only and not img.get("is_public", False):
            continue

        # vendor filter (case-insensitive)
        vendor = (img.get("vendor") or "").strip()
        if vendor_allow is not None and vendor.lower() not in vendor_allow:
            continue

        # status filter
        if require_status_available and img.get("status") != "available":
            continue

        # capability filter
        caps = img.get("capabilities") or []
        if need_caps and not need_caps.issubset(set(caps)):
            continue

        # region gating
        regions = img.get("regions")
        if isinstance(regions, list) and len(regions) > 0:
            if region_id not in regions:
                continue
        # If regions is None or empty list, treat as globally available

        # EOL/Deprecated filtering
        deprecated = bool(img.get("deprecated"))
        eol_raw = img.get("eol")
        eol_passed = _eol_has_passed(eol_raw)
        if exclude_eol and (deprecated or eol_passed):
            continue

        out.append({
            "id": img.get("id"),
            "label": img.get("label"),
            "vendor": vendor or None,
            "description": img.get("description") or "",
            "size": img.get("size"),
            "created": img.get("created"),
            "updated": img.get("updated"),
            "is_public": bool(img.get("is_public")),
            "deprecated": deprecated,
            "eol": eol_raw,
            "eol_passed": eol_passed,
            "regions": regions if regions is not None else None,
            "status": img.get("status"),
            "capabilities": caps,
        })

    # Stable, readable ordering: vendor -> label
    out.sort(key=lambda x: ((x.get("vendor") or "").lower(), (x.get("label") or "").lower()))
    return out