"""Command Line Interface for the Short-Form Content Engine."""

from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table

from config.settings import ASSETS_DIR, DB_PATH, OUTPUT_DIR, settings
from engine.experiments.models import RenderAsset
from engine.experiments.repository import ExperimentRepository
from engine.media.compositor import FFmpegCompositor
from engine.media.transcription import DummyTranscriptionProvider
from engine.media.voice import DummyVoiceProvider
from engine.pipeline import ContentEnginePipeline
from engine.qa.validator import MediaValidator
from engine.scripting.schema import HookType, VariantPlan
from engine.scripting.scriptwriter import DummyScriptProvider

app = typer.Typer(help="Short-Form Content Engine - Experimental Audiovisual Pipeline")
experiment_app = typer.Typer(help="Manage experiments and hypotheses")
asset_app = typer.Typer(help="Manage and register compliant assets")

app.add_typer(experiment_app, name="experiment")
app.add_typer(asset_app, name="asset")

console = Console()


def get_repo() -> ExperimentRepository:
    """Instantiate standard repository."""
    return ExperimentRepository(settings.database_url)


@app.command(name="init")
def init_cmd():
    """Initialize database schemas and local storage directories."""
    repo = get_repo()
    repo.init_db()
    console.print(f"[bold green][OK][/bold green] Database schema initialized at [cyan]{DB_PATH}[/cyan]")
    console.print(f"[bold green][OK][/bold green] Asset storage ready at [cyan]{ASSETS_DIR}[/cyan]")
    console.print(f"[bold green][OK][/bold green] Output storage ready at [cyan]{OUTPUT_DIR}[/cyan]")


@asset_app.command(name="register")
def asset_register(
    asset_type: str = typer.Option(..., "--type", "-t", help="Type: video, audio, font, image"),
    source: str = typer.Option(..., "--source", "-s", help="Origin URI or file path"),
    license_name: str = typer.Option(..., "--license", "-l", help="License (e.g. CC0, CC-BY-4.0)"),
    creator: str = typer.Option(..., "--creator", "-c", help="Author or rights owner"),
    allowed_platforms: str = typer.Option("all", "--platforms", "-p", help="Allowed platforms"),
    attribution_required: bool = typer.Option(False, "--attribution", "-a", help="Attribution required"),
):
    """Register a new asset with strict provenance verification."""
    repo = get_repo()
    repo.init_db()
    try:
        asset = repo.register_asset(
            asset_type=asset_type,
            source=source,
            license_name=license_name,
            creator=creator,
            allowed_platforms=allowed_platforms,
            attribution_required=attribution_required,
        )
        console.print(f"[bold green][OK][/bold green] Asset registered successfully!")
        console.print(f"  ID: [cyan]{asset.id}[/cyan]")
        console.print(f"  Type: {asset.type} | License: {asset.license} | Creator: {asset.creator}")
    except ValueError as e:
        console.print(f"[bold red]Provenance Error:[/bold red] {e}")
        raise typer.Exit(code=1)


@experiment_app.command(name="create")
def experiment_create(
    name: str = typer.Option(..., "--name", "-n", help="Experiment name"),
    description: str = typer.Option(..., "--desc", "-d", help="Experiment description"),
    statement: str = typer.Option(
        "A question hook produces higher 3s retention than a statement",
        "--statement",
        help="Quantifiable hypothesis",
    ),
    independent_variable: str = typer.Option("hook_type", "--variable", help="Variable being modified"),
    primary_metric: str = typer.Option("retention_at_3s", "--metric", help="Primary observed metric"),
):
    """Create a new experiment container with its foundational hypothesis."""
    repo = get_repo()
    repo.init_db()

    exp = repo.create_experiment(name=name, description=description)
    hyp = repo.create_hypothesis(
        experiment_id=exp.id,
        statement=statement,
        independent_variable=independent_variable,
        primary_metric=primary_metric,
        success_criterion=f"{primary_metric} > baseline * 1.25",
        baseline_description="Standard baseline performance",
    )

    console.print(f"[bold green][OK][/bold green] Experiment created: [bold cyan]{exp.name}[/bold cyan] ({exp.id})")
    console.print(f"  Hypothesis ID: [cyan]{hyp.id}[/cyan]")
    console.print(f"  Testing Variable: [yellow]{hyp.independent_variable}[/yellow] on [yellow]{hyp.primary_metric}[/yellow]")


@experiment_app.command(name="list")
def experiment_list():
    """List all registered experiments and their execution status."""
    repo = get_repo()
    repo.init_db()
    experiments = repo.list_experiments()

    if not experiments:
        console.print("[yellow]No experiments recorded yet. Run `python cli.py experiment create` to begin.[/yellow]")
        return

    table = Table(title="Content Engine Experiments")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="bold white")
    table.add_column("Status", style="green")
    table.add_column("Hypotheses", justify="right")
    table.add_column("Runs", justify="right")
    table.add_column("Created", style="dim")

    for exp in experiments:
        table.add_row(
            exp.id[:8] + "...",
            exp.name,
            exp.status,
            str(len(exp.hypotheses)),
            str(len(exp.runs)),
            exp.created_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)


@app.command(name="run-demo")
def run_demo(
    topic: str = typer.Option("el Telescopio Espacial James Webb", "--topic", "-t", help="Topic for the demo variants"),
    duration: float = typer.Option(5.0, "--duration", "-d", help="Target duration in seconds for quick demo"),
):
    """Execute a fully deterministic offline demo generating 3 video variants (A/B/C) with QA and provenance."""
    repo = get_repo()
    repo.init_db()

    console.print(f"[bold blue]Starting Offline Demo Experiment on:[/bold blue] [bold]{topic}[/bold]")

    # 1. Create Demo Experiment & Hypothesis
    exp = repo.create_experiment(
        name=f"Demo: Hook Optimization ({topic[:30]})",
        description="Evaluating Question vs Statement vs Surprise hooks in vertical short-form",
    )
    hyp = repo.create_hypothesis(
        experiment_id=exp.id,
        statement="A question hook retains >25% higher audience at 3s compared to a statement or surprise.",
        independent_variable="hook_type",
        primary_metric="retention_at_3s",
        success_criterion="retention_at_3s >= 0.65",
        baseline_description="Standard baseline retention is 0.45",
    )

    plans = [
        VariantPlan(variant_code="A", hook_type=HookType.QUESTION, target_duration_sec=duration, topic=topic),
        VariantPlan(variant_code="B", hook_type=HookType.STATEMENT, target_duration_sec=duration, topic=topic),
        VariantPlan(variant_code="C", hook_type=HookType.SURPRISE, target_duration_sec=duration, topic=topic),
    ]

    pipeline = ContentEnginePipeline(
        repository=repo,
        script_provider=DummyScriptProvider(),
        voice_provider=DummyVoiceProvider(words_per_minute=160),
        transcription_provider=DummyTranscriptionProvider(),
        compositor=FFmpegCompositor(prefer_nvenc=settings.prefer_nvenc),
        validator=MediaValidator(
            expected_width=settings.default_width,
            expected_height=settings.default_height,
            duration_tolerance_sec=4.0,
        ),
    )

    console.print("[dim]Rendering variants through FFmpeg and compiling provenance...[/dim]")
    result = pipeline.run_experiment_variants(
        experiment_id=exp.id,
        hypothesis_id=hyp.id,
        variant_plans=plans,
    )

    console.print(f"\n[bold green][OK] Run Completed successfully![/bold green] (Run ID: [cyan]{result.run.id}[/cyan])\n")

    table = Table(title="Render Results & QA Verification")
    table.add_column("Variant", style="bold cyan")
    table.add_column("Hook Type", style="white")
    table.add_column("Duration", justify="right")
    table.add_column("Resolution", justify="center")
    table.add_column("Render Time", justify="right")
    table.add_column("QA Passed", justify="center")
    table.add_column("Output File Path", style="dim")

    for render in result.renders:
        qa_status = "[bold green]PASS[/bold green]" if render.qa_passed else "[bold red]FAIL[/bold red]"
        table.add_row(
            render.variant.variant_code,
            render.variant.hook_type,
            f"{render.duration_seconds}s",
            f"{render.width}x{render.height}",
            f"{render.render_time_seconds}s",
            qa_status,
            render.file_path,
        )

    console.print(table)
    console.print("\n[bold]Provenance verification:[/bold] All renders linked to internal procedural assets in SQLite.")


@app.command(name="run")
def run_experiment_cmd(
    experiment_id: str = typer.Option(..., "--experiment-id", "-e", help="UUID of experiment to execute"),
    duration: float = typer.Option(30.0, "--duration", "-d", help="Target duration in seconds"),
):
    """Run an existing experiment by ID using stored hypotheses."""
    repo = get_repo()
    repo.init_db()

    exp = repo.get_experiment(experiment_id)
    if not exp:
        console.print(f"[bold red]Experiment not found:[/bold red] {experiment_id}")
        raise typer.Exit(code=1)

    if not exp.hypotheses:
        console.print(f"[bold red]Experiment has no hypotheses defined.[/bold red]")
        raise typer.Exit(code=1)

    hyp = exp.hypotheses[0]
    topic = exp.name

    plans = [
        VariantPlan(variant_code="A", hook_type=HookType.QUESTION, target_duration_sec=duration, topic=topic),
        VariantPlan(variant_code="B", hook_type=HookType.STATEMENT, target_duration_sec=duration, topic=topic),
        VariantPlan(variant_code="C", hook_type=HookType.SURPRISE, target_duration_sec=duration, topic=topic),
    ]

    pipeline = ContentEnginePipeline(
        repository=repo,
        script_provider=DummyScriptProvider(),
        voice_provider=DummyVoiceProvider(),
        transcription_provider=DummyTranscriptionProvider(),
        compositor=FFmpegCompositor(prefer_nvenc=settings.prefer_nvenc),
        validator=MediaValidator(),
    )

    console.print(f"[bold blue]Executing Experiment:[/bold blue] {exp.name}")
    result = pipeline.run_experiment_variants(
        experiment_id=exp.id,
        hypothesis_id=hyp.id,
        variant_plans=plans,
    )
    console.print(f"[bold green][OK] Completed run {result.run.id} with {len(result.renders)} renders.[/bold green]")


@app.command(name="list")
def list_summary():
    """Display comprehensive summary of experiments, runs, and renders."""
    repo = get_repo()
    repo.init_db()
    experiments = repo.list_experiments()

    console.print(f"\n[bold]Total Experiments Recorded:[/bold] {len(experiments)}")
    for exp in experiments:
        console.print(f"\n[bold cyan]Experiment:[/bold cyan] {exp.name} ([dim]{exp.id}[/dim])")
        for hyp in exp.hypotheses:
            console.print(f"  [yellow]Hypothesis:[/yellow] {hyp.statement}")
            console.print(f"  [dim]Variable: {hyp.independent_variable} | Metric: {hyp.primary_metric}[/dim]")
        for run in exp.runs:
            console.print(f"    [green]Run {run.id[:8]}:[/green] Status={run.status} | Renders={len(run.renders)}")
            for r in run.renders:
                status_icon = "[OK]" if r.qa_passed else "[X]"
                console.print(f"      - [{ 'green' if r.qa_passed else 'red' }]{status_icon}[/] Variant {r.variant.variant_code} ({r.width}x{r.height}, {r.duration_seconds}s) -> {r.file_path}")


if __name__ == "__main__":
    app()
