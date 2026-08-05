"""Typer + Rich CLI for ToolKinetik.

Commands:
    health                     Check FastAPI backend health
    skills list                List loaded skills
    skills reload              Trigger skill hot-reload
    skills create NAME DESC    Request a new skill
    sandbox status             Show sandbox status
"""

from __future__ import annotations

import httpx
import typer
from rich.console import Console
from rich.table import Table

from toolkinetik.config import get_settings

console = Console()
settings = get_settings()

API_BASE = settings.TOOLKINETIK_API_URL
HEADERS = {"X-API-Key": settings.AGNO_API_KEY}

# --- Typer apps ------------------------------------------------------------
app = typer.Typer(help="ToolKinetik CLI", no_args_is_help=True)
skills_app = typer.Typer(help="Manage skills", no_args_is_help=True)
sandbox_app = typer.Typer(help="Sandbox management", no_args_is_help=True)

app.add_typer(skills_app, name="skills")
app.add_typer(sandbox_app, name="sandbox")


# --- Commands --------------------------------------------------------------

@app.command()
def health() -> None:
    """Check if the FastAPI backend is running."""
    try:
        response = httpx.get(f"{API_BASE}/api/health", timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            console.print(f"[bold green]✓ Backend is healthy — status: {data.get('status', 'unknown')}[/]")
        else:
            console.print(f"[bold red]✗ Backend returned {response.status_code}[/]")
            raise typer.Exit(code=1)
    except httpx.RequestError as exc:
        console.print(f"[bold red]✗ Cannot reach backend at {API_BASE}: {exc}[/]")
        raise typer.Exit(code=1) from exc


@skills_app.command("list")
def skills_list() -> None:
    """List all loaded skills."""
    try:
        response = httpx.get(f"{API_BASE}/api/skills", headers=HEADERS, timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            tools = data.get("tools", [])
            table = Table(title="Loaded Skills")
            table.add_column("#", style="cyan", no_wrap=True)
            table.add_column("Skill Name", style="white")
            for idx, name in enumerate(tools, 1):
                table.add_row(str(idx), name)
            console.print(table)
        else:
            console.print(f"[bold red]✗ Failed to list skills: {response.status_code}[/]")
            raise typer.Exit(code=1)
    except httpx.RequestError as exc:
        console.print(f"[bold red]✗ Cannot reach backend: {exc}[/]")
        raise typer.Exit(code=1) from exc


@skills_app.command("reload")
def skills_reload() -> None:
    """Trigger skill hot-reload."""
    try:
        response = httpx.post(f"{API_BASE}/api/reload-skills", headers=HEADERS, timeout=10.0)
        if response.status_code == 200:
            data = response.json()
            loaded = data.get("loaded_tools", [])
            console.print(f"[bold green]✓ Skills reloaded — {len(loaded)} tool(s) loaded[/]")
            for name in loaded:
                console.print(f"  • {name}")
        else:
            console.print(f"[bold red]✗ Reload failed: {response.status_code}[/]")
            raise typer.Exit(code=1)
    except httpx.RequestError as exc:
        console.print(f"[bold red]✗ Cannot reach backend: {exc}[/]")
        raise typer.Exit(code=1) from exc


@skills_app.command("create")
def skills_create(
    name: str = typer.Argument(..., help="Name of the new skill"),
    description: str = typer.Argument(..., help="Description of what the skill does"),
) -> None:
    """Request a new skill via the SkillWriter pipeline.

    Triggers the full create-test-promote loop: research → codegen →
    safety → TDD → promote.
    """
    from toolkinetik.skill_writer import SkillWriter

    console.print("[bold cyan]Creating skill:[/]")
    console.print(f"  Name:        {name}")
    console.print(f"  Description: {description}")
    console.print("[dim]Running SkillWriter pipeline (research → codegen → TDD → promote)...[/]")

    writer = SkillWriter()
    result = writer.write_skill(f"{description} (skill name: {name})")

    if result.success:
        console.print(f"[bold green]✓ Skill '{name}' created and promoted[/]")
        if result.promotion:
            console.print(f"  Path: {result.promotion.skill_path}")
    else:
        console.print(f"[bold red]✗ Skill creation failed: {result.error}[/]")
        if result.safety_issues:
            console.print(f"  Safety issues: {result.safety_issues}")
        raise typer.Exit(code=1)


@sandbox_app.command("status")
def sandbox_status() -> None:
    """Show sandbox status — checks Docker daemon availability."""
    import shutil as _shutil

    console.print("[bold blue]Sandbox Status[/]")
    console.print(f"  Image: {settings.SANDBOX_IMAGE}")

    docker_cli = _shutil.which("docker")
    if not docker_cli:
        console.print("  [bold red]✗ Docker CLI not found[/]")
        raise typer.Exit(code=1)

    try:
        import docker
        client = docker.from_env()
        client.ping()
        console.print("  [bold green]✓ Docker daemon reachable[/]")
        info = client.info()
        console.print(f"  Containers: {info.get('Containers', 'unknown')}")
        console.print(f"  Docker version: {info.get('ServerVersion', 'unknown')}")
    except Exception as exc:
        console.print(f"  [bold red]✗ Docker daemon unreachable: {exc}[/]")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":  # pragma: no cover
    app()