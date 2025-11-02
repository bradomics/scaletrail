import typer
import inquirer
import sys
import json
from tomlkit import document, table, dumps, parse

from pathlib import Path
import os
from dotenv import load_dotenv
import requests
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich_pyfiglet import RichFiglet
from rich.table import Table
from rich import box
from rich.panel import Panel

from .utils import cloudflare, formatting, linode, env_file

load_dotenv()
console = Console()
app = typer.Typer()

# Default env. choices for prompts
ENV_CHOICES = ["dev", "staging", "prod"]

def select_environments() -> List[str]:
    """
    Ask which environments to set up. Supports dev/staging/prod or custom list.
    """
    answers = inquirer.prompt([
        inquirer.Checkbox(
            "envs",
            message="Which environments do you want to set up? (Use the space bar to select, enter to confirm)",
            choices=ENV_CHOICES,
            carousel=True,
        )
    ]) or {}

    envs = answers.get("envs", [])

    if not envs:
        console.print("[red]No environments selected.[/red]")
        raise typer.Exit(1)
    return envs

@app.command()
def init(
    project_name: str = typer.Option(
        "",
        help="The name of the project to initialize.",
    ),
    linode_api_key: str = typer.Option(
        "",
        help="Your Linode API key for managing infrastructure.",
    ),
    continent: str = typer.Option(
        "",
        help="Continent for infrastructure (North America, Europe, Asia, South America, Oceania).",
    ),
    linode_region: str = typer.Option(
        "",
        help="The Linode region slug for your desired infrastructure's region.",
    ),
    instance_type: str = typer.Option(
        "",
        help="The Linode instance type for your desired infrastructure.",
    ),
    domain_to_configure: str = typer.Option(
        "",
        help="The domain to configure for your infrastructure (e.g., example.com).",
    ),
    image: str = typer.Option(
        "",
        help="The Linode image slug for your desired infrastructure's base image.",# TODO: move image, backups enabled, etc. to prior step. Also create a simple option that bypasses unneeded prompts and goes with a default configuration
    ),
    backups_enabled: bool = typer.Option(
        False,
        help="Whether to enable backups for the Linode instance.",
    ),
    tags: str = typer.Option(
        "",
        help="Comma-separated tags to apply to the Linode instance.",
    ),
    stripe_api_key: str = typer.Option(
        "",
        help="Your Stripe API key for payment processing.",
    ),
    sendgrid_api_key: str = typer.Option(
        "",
        help="Your SendGrid API key for payment processing.",
    )
):
    """Initializes the project configuration."""
    # The banner and links are now part of the init command's execution flow.
    formatting.show_banner()

    if not project_name:
        project_name = typer.prompt("Project name")        

    # We'll first need to ensure the .env file exists along with API keys necessary to trigger
    # infrastructure changes.
    env_file.find_or_create_env_file()
    if not env_file.api_key_present("LINODE_API_KEY"):
        linode_api_key = typer.prompt("Linode API key", hide_input=True)
        env_file.add_api_key("LINODE_API_KEY", linode_api_key)
    else:
        cloudflare_api_key = os.getenv("LINODE_API_KEY")

    if not env_file.api_key_present("CLOUDFLARE_ACCOUNT_ID"):
        cloudflare_account_id = typer.prompt("Cloudflare account ID", hide_input=True)
        env_file.add_api_key("CLOUDFLARE_ACCOUNT_ID", cloudflare_account_id)
    else:
        cloudflare_account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")

    if not env_file.api_key_present("CLOUDFLARE_API_KEY"):
        cloudflare_api_key = typer.prompt("Cloudflare API key", hide_input=True)
        env_file.add_api_key("CLOUDFLARE_API_KEY", cloudflare_api_key)
    else:
        cloudflare_api_key = os.getenv("CLOUDFLARE_API_KEY")
        
    if not env_file.api_key_present("STRIPE_API_KEY"):
        stripe_api_key = typer.prompt("Stripe API key", hide_input=True)
        env_file.add_api_key("STRIPE_API_KEY", stripe_api_key)
    else:
        stripe_api_key = os.getenv("STRIPE_API_KEY")

    # Allow CLI overrides: if both continent and region were provided, skip prompts
    if not linode_region:
        if not continent:
            print("\n")
            ans = inquirer.prompt([
                inquirer.List("continent",
                    message="Select a continent for your infrastructure (or show all regions)",
                    choices=linode.CONTINENT_CHOICES,
                    carousel=True)
            ]) or {}
            continent = ans.get("continent", "")
            if not continent:
                raise typer.Exit(1)

        if continent == "Show all regions":
            region_choices = sum(linode.CONTINENT_TO_REGIONS.values(), [])  # flatten
        else:
            # normalize if user passed --continent europe
            norm = continent.strip().lower()
            alias = {c.lower(): c for c in linode.CONTINENT_CHOICES if c != "Show all regions"}
            continent = alias.get(norm, continent)
            region_choices = linode.CONTINENT_TO_REGIONS.get(continent, [])

        ans = inquirer.prompt([
            inquirer.List("linode_region",
                message=f"Select a Linode region{f' in {continent}' if continent!='Show all regions' else ''}",
                choices=region_choices,
                carousel=True)
        ]) or {}
        linode_region = ans.get("linode_region", "")
        console.print(f"Selected region: {linode_region}")
                # Use continent to filter for available Linode types
        url = "https://api.linode.com/v4/linode/types"

        payload = {}
        headers = {
            'Accept': 'application/json',
            'Authorization': linode_api_key
        }

        response = requests.request("GET", url, headers=headers, data=payload)
        envs = select_environments()
        console.print("Available Linode instance types:")
        # region_id could be "us-east", "us-ord", "br-gru", "id-cgk", etc.
        instances = linode.get_instances_for_region(response.json(), region_id=linode_region,
            include_classes=["nanode","standard","dedicated","premium"])
        
        # After you pick `linode_region` and have a Linode API key:
        imgs_url = "https://api.linode.com/v4/images"
        headers = {
            "Accept": "application/json",
            # IMPORTANT: Linode expects a Bearer token here:
            "Authorization": linode_api_key,
        }
        imgs_resp = requests.get(imgs_url, headers=headers).json()

        # Filter to OSes available in the chosen region:
        oses = linode.get_operating_systems_for_region(
            imgs_resp,
            region_id=linode_region,
            include_vendors=["AlmaLinux", "Alpine", "Arch", "CentOS", "Debian", "Fedora", "Kali", "Gentoo", "OpenSuse", "Rocky Linux", "Slackware", "Ubuntu"],   # or e.g. ["Ubuntu", "Debian", "AlmaLinux", "Rocky Linux"]
            public_only=True,
            exclude_eol=True,
        )

        env_instance_types: Dict[str, str] = {}
        env_os_choices: Dict[str, str] = {}
        env_backups_enabled: Dict[str, bool] = {}
        env_instance_tags: Dict[str, List[str]] = {}
        env_stripe_api_keys: Dict[str, str] = {}
        env_sendgrid_api_keys: Dict[str, str] = {}
        for env in envs:
            console.print(f"\n[bold]Environment:[/bold] {env}")
            console.print(f"Pick a size for the '{env}' environment (region: {linode_region})\n")
            selected = linode.choose_instance(
                instances,
                message=f"Select a Linode plan for {env}"
            )
            selected_os = linode.choose_os(oses, message=f"Select a Linode OS for {env}")
            if not selected:
                console.print(f"[red]No instance selected for {env}. Aborting.[/red]")
                raise typer.Exit(1)
            env_instance_types[env] = selected["id"]
            env_os_choices[env] = selected_os["id"]
            console.print(f"→ {env}: [bold]{selected['label']}[/bold] ({selected['id']})")

            env_backups_enabled[env] = typer.prompt(f"Enable backups for {env}? (y/n)").lower() == "y"
            env_instance_tags[env] = typer.prompt(f"Tags for {env} instance (comma-separated)")
            env_stripe_api_keys[env] = typer.prompt(f"Stripe API key ({env})")
            env_sendgrid_api_keys[env] = typer.prompt(f"SendGrid API key ({env})")


    if not linode_region:
        raise typer.Exit(1)

    if not domain_to_configure:
        domain_to_configure = typer.prompt("\nDomain to configure (e.g., example.com)")

        # Get Zone ID via Cloudflare
        domain_zone_id = cloudflare.get_cloudflare_zone_id(domain_to_configure, cloudflare_api_key)
        dns_records = cloudflare.get_cloudflare_dns_records(domain_zone_id, cloudflare_api_key)

        for env in envs:
            if env == "prod":
                # TODO: Turn these statements into a function
                if cloudflare.root_domain_is_availabile(dns_records, domain_to_configure):
                    console.print(f"[bold]{domain_to_configure}[/bold] (the root domain) is available!\n It will be used to host the [bold]front end[/bold] server for the [bold][{formatting.ENV_COLORS[env]}]production[/{formatting.ENV_COLORS[env]}][/bold] environment.\n")
                else:
                    console.print(f"[red][bold]Warning![/bold] The root domain [bold]{domain_to_configure}[/bold] has an existing A or CNAME record! It will be overwritten![/red]\n")

                if cloudflare.subdomain_is_available(dns_records, "www", domain_to_configure):
                    console.print(f"[bold]www.{domain_to_configure}[/bold] subdomain is available!\n")
                else:
                    console.print(f"[red][bold]Warning![/bold] The [bold]www.{domain_to_configure}[/bold] has an existing A or CNAME record! It will be overwritten![/red]\n")

                if cloudflare.subdomain_is_available(dns_records, "api", domain_to_configure):
                    console.print(f"[bold]api.{domain_to_configure}[/bold] subdomain is available!\nIt will be used to host the [bold]back end[/bold] server for the [bold][{formatting.ENV_COLORS[env]}]production[/{formatting.ENV_COLORS[env]}][/bold] environment.\n")
                else:
                    console.print(f"[red][bold]Warning![/bold] The [bold]api.{domain_to_configure}[/bold] has an existing A or CNAME record! It will be overwritten![/red]\n")
            else:
                if cloudflare.subdomain_is_available(dns_records, f"{env}", domain_to_configure):
                    console.print(f"[bold]{env}.{domain_to_configure}[/bold] subdomain is available!\nIt will be used to host the [bold]front end[/bold] server for the [bold][{formatting.ENV_COLORS[env]}]{env}[/{formatting.ENV_COLORS[env]}][/bold] environment.\n")
                else:
                    console.print(f"[red][bold]{env}.{domain_to_configure}[/bold] subdomain is already taken![/red]\n")

                if cloudflare.subdomain_is_available(dns_records, f"{env}-api", domain_to_configure):
                    console.print(f"[bold]{env}-api.{domain_to_configure}[/bold] subdomain is available!\nIt will be used to host the [bold]back end[/bold] server for the [bold][{formatting.ENV_COLORS[env]}]{env}[/{formatting.ENV_COLORS[env]}][/bold] environment.\n")
                else:
                    console.print(f"[red][bold]{env}-api.{domain_to_configure}[/bold] subdomain is already taken![/red]\n")            

    # Persist full configuration as TOML — one file per environment
    out_dir = Path.cwd() / "config"
    out_dir.mkdir(parents=True, exist_ok=True)

    for env_name in envs:
        # pick the instance type for this env (guard in case of missing key)
        instance_id = env_instance_types.get(env_name, "")
        env_instance_tags.get(env_name, "")
        image_id = env_os_choices.get(env_name, "")
        stripe_api_key = env_stripe_api_keys.get(env_name, "")
        sendgrid_api_key = env_sendgrid_api_keys.get(env_name, "")


        config_data = {
            "project": {
                "name": project_name,
                "initialized": True,
            },
            # helpful to store which env this file represents
            "environment": {
                "name": env_name
            },
            "linode": {
                "region": linode_region,
                "backups_enabled": bool(env_backups_enabled[env_name]),
                "tags": [t.strip() for t in env_instance_tags[env_name].split(",")] if env_instance_tags else [],
                # keep a single env block in each file for clarity
                "instance_type": instance_id,
                "image": image_id,
            },
            "cloudflare": {
                "account_id_saved": bool(cloudflare_account_id),
                "api_key_saved": bool(cloudflare_api_key),
            },
            "stripe": {"api_key_saved": bool(stripe_api_key)},
            "sendgrid": {"api_key_saved": bool(sendgrid_api_key)},
            "domain": {"root": domain_to_configure},
        }

        # Write ./config/<env>-config.toml
        config_file = out_dir / f"{env_name}-config.toml"
        config_file.write_text(dumps(config_data), encoding="utf-8")

        project_env_file = out_dir / f"{env_name}.env"
        project_env_file.write_text(
            f"STRIPE_API_KEY={stripe_api_key}\n"
            f"SENDGRID_API_KEY={sendgrid_api_key}\n",
            encoding="utf-8"
        )

    env_list = ", ".join(envs)
    console.print(f"[green]Configs for [bold]{env_list}[/bold] have been saved to the [bold]config[/bold] folder.[/green]")
    console.print(f"Initialization complete! You can now run [bold]scaletrail preview[/bold] and [bold]scaletrail deploy[/bold] to preview and deploy your infrastructure.")

@app.command()
def run():
    """Runs the application."""
    typer.echo("Running the application...")


def _find_config_dir() -> Path:
    cfg = Path.cwd() / "config"
    if not cfg.exists() or not cfg.is_dir():
        console.print("[red]No ./config directory found.[/red]")
        raise typer.Exit(code=1)
    return cfg


def _list_env_configs(config_dir: Path) -> List[Path]:
    return sorted(config_dir.glob("*-config.toml"))


def _pick_env_file(candidates: List[Path]) -> Path:
    if not candidates:
        console.print("[red]No *-config.toml files found in ./config[/red]")
        raise typer.Exit(code=1)
    if len(candidates) == 1:
        return candidates[0]

    choices = [c.name for c in candidates]
    answer = inquirer.prompt([
        inquirer.List(
            "cfg",
            message="Select an environment to preview",
            choices=choices,
            carousel=True,
        )
    ])
    if not answer or "cfg" not in answer:
        raise typer.Exit(code=1)
    return next(p for p in candidates if p.name == answer["cfg"])


def _env_name_from_config_filename(config_path: Path) -> str:
    # e.g., dev-config.toml -> dev
    stem = config_path.name
    if stem.endswith("-config.toml"):
        return stem[:-len("-config.toml")]
    return stem.replace(".toml", "")


def _read_toml(path: Path) -> Dict[str, Any]:
    try:
        return parse(path.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"[red]Failed to parse TOML:[/red] {e}")
        raise typer.Exit(code=1)


def _read_env_file(env_path: Path) -> Dict[str, str]:
    if not env_path.exists():
        return {}

    data: Dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.strip().startswith("#"):
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        data[key.strip()] = val.strip()
    return data


def _planned_dns_records(root: str, env_name: str) -> List[Dict[str, str]]:
    records: List[Dict[str, str]] = []


    # <env>-api.<root> for non-prod environments
    if env_name and env_name.lower() not in ("prod", "production"):
        records.append({
            "Name": f"{env_name}-api.{root}",
            "Type": "A",
            "Content": "TBD (after create)",
            "Proxy": "Proxied",
            "TTL": "Auto",
        })
    else:
        # api.<root>
        records.append({
            "Name": f"api.{root}",
            "Type": "A",
            "Content": "TBD (after create)",
            "Proxy": "Proxied",
            "TTL": "Auto",
        })

        # www CNAME → apex
        records.append({
            "Name": f"www.{root}",
            "Type": "CNAME",
            "Content": root,
            "Proxy": "Proxied",
            "TTL": "Auto",
        })

    return records

def _linode_table(cfg: Dict[str, Any]) -> Table:
    lin = cfg.get("linode", {})
    env = cfg.get("environment", {})
    proj = cfg.get("project", {})

    table = Table(
        title=f"Linode • Resources to be added • {proj.get('name','')} [{env.get('name','')}]",
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold cyan",
        expand=False,
    )

    table.add_column("Region", justify="center", style="bold")
    table.add_column("Type", justify="center")
    table.add_column("Image", justify="center")
    table.add_column("Backups", justify="center")
    table.add_column("Tags", justify="center")

    table.add_row(
        lin.get("region", "—"),
        lin.get("instance_type", "—"),
        lin.get("image", "—"),
        "Yes" if lin.get("backups_enabled") else "No",
        ", ".join(lin.get("tags", [])) or "—",
    )

    return table


def _cloudflare_table(cfg: Dict[str, Any], env_name: str, env_vars: Dict[str, str]) -> Table:
    cf = cfg.get("cloudflare", {})
    domain = cfg.get("domain", {})
    root = domain.get("root", "—")

    table = Table(
        title=f"Cloudflare • DNS records to be added • {root}",
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold cyan",
        expand=False,
    )

    table.add_column("Record", justify="left")
    table.add_column("Type", justify="center")
    table.add_column("Content", justify="left")
    table.add_column("Proxy", justify="center")

    # planned DNS
    dns_records = _planned_dns_records(root, env_name)
    for r in dns_records:
        table.add_row(
            r["Name"],
            r["Type"],
            r["Content"],
            "🟠 proxied" if r["Proxy"] == "Proxied" else "⚪",
        )

    return table

@app.command()
def preview():
    """Previews resources to be provisioned."""
    try:
        config_dir = _find_config_dir()
        candidates = _list_env_configs(config_dir)
        cfg_path = _pick_env_file(candidates)
        env_name = _env_name_from_config_filename(cfg_path)
        env_path = config_dir / f"{env_name}.env"

        cfg = _read_toml(cfg_path)
        env_vars = _read_env_file(env_path)

        project_name = cfg.get("project", {}).get("name", "Unknown")
        # _render_header(project_name, env_name)

        # Linode section
        console.print(_linode_table(cfg))
        console.print("\n\n")

        # Cloudflare section
        console.print(_cloudflare_table(cfg, env_name, env_vars))
        console.print("\n\n")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Preview failed:[/red] {e}")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
