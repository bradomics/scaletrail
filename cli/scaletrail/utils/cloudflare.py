from typing import Any, Dict, List, Optional
import typer
import requests

from rich.console import Console
from rich_pyfiglet import RichFiglet

console = Console()
def get_cloudflare_zone_id(domain: str, cloudflare_api_key: str) -> Optional[str]:
    """Fetches the Cloudflare Zone ID for a given domain."""
    url = "https://api.cloudflare.com/client/v4/zones"
    headers = {
        "Authorization": f"Bearer {cloudflare_api_key}",
        "Content-Type": "application/json"
    }
    params = {"name": domain}

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        if data.get("success") and data.get("result"):
            print(f"Cloudflare zone ID for domain {domain} is {data['result'][0]['id']}\n")
            return data["result"][0]["id"]
    console.print(f"[red]Error fetching Zone ID for domain {domain}[/red]")
    return None

def get_cloudflare_dns_records(zone_id: str, cloudflare_api_key: str) -> Optional[List[Dict[str, Any]]]:
    """Fetches DNS records for a given Cloudflare Zone ID."""
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    headers = {
        "Authorization": f"Bearer {cloudflare_api_key}",
        "Content-Type": "application/json"
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            return data.get("result", [])
    console.print(f"[red]Error fetching DNS records for zone ID {zone_id}[/red]")
    return None

def subdomain_is_available(records, subdomain, root_domain):
    """
    Checks whether a given subdomain (like 'dev') or the root domain
    already exists as an A or CNAME record.
    Returns True if available, False if it already exists.
    """
    # Handle root domain (no subdomain)
    if not subdomain or subdomain in ("@", "", root_domain):
        target_name = root_domain.lower()
    else:
        target_name = f"{subdomain}.{root_domain}".lower()

    for record in records:
        record_name = record.get("name", "").lower()
        record_type = record.get("type", "").upper()

        if record_type in ("A", "CNAME") and record_name == target_name:
            return False  # already exists (not available)

    return True  # available

def root_domain_is_availabile(records, root_domain):
    return subdomain_is_available(records, "", root_domain)