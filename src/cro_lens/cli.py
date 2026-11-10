"""cro-lens CLI — contract cli@1."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from cro_lens import __version__
from cro_lens.config import CroLensError, InvalidInput, new_run_id, provider_name, runs_dir, validate_url
from cro_lens.models import Given

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Evidence-backed landing page teardowns: one URL in, a checked A/B experiment backlog out.",
)
ModelOpt = Annotated[str, typer.Option("--model", help="sonnet or opus")]
ProviderOpt = Annotated[str | None, typer.Option("--provider", help="claude-code (default) or fake")]


def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def _fail(e: CroLensError) -> None:
    typer.echo(f"error: {e}", err=True)
    raise typer.Exit(e.exit_code)


def _notices(prov: object) -> None:
    """Say before the run what the sign-in check found: who pays, a token worked around."""
    from cro_lens.llm.provider import notices

    for n in notices(prov):  # type: ignore[arg-type]
        lines = n.lines() if hasattr(n, "lines") else [str(n)]
        typer.echo(f"! {lines[0]}", err=True)
        for line in lines[1:]:
            typer.echo(f"  {line}", err=True)
        typer.echo("  More: README → Signing in", err=True)


def print_event(ev: dict) -> None:
    if ev["status"] == "started":
        return
    mark = "✓" if ev["status"] == "done" else "✗"
    secs = f" ({ev['seconds']:.1f}s)" if ev.get("seconds") else ""
    detail = f"  {ev['detail']}" if ev.get("detail") else ""
    typer.echo(f"{mark} {ev['step']:<11}{detail}{secs}")


@app.command()
def analyze(
    url: str,
    model: ModelOpt = "sonnet",
    provider: ProviderOpt = None,
    audience: Annotated[str | None, typer.Option(help="who the page is for, if you know")] = None,
    traffic: Annotated[str | None, typer.Option(help="traffic source, e.g. 'paid social'")] = None,
    goal: Annotated[str | None, typer.Option(help="the conversion goal, e.g. 'trial sign-up'")] = None,
    out: Annotated[Path | None, typer.Option("--out", help="write the run folder here")] = None,
    no_feedback: Annotated[
        bool, typer.Option("--no-feedback", help="do not learn from your graded findings this time")
    ] = False,
) -> None:
    """Analyse one landing page and write report.md + report.json."""
    from cro_lens.llm.provider import get_provider, preflight
    from cro_lens.pipeline.run import Options, Pipeline
    from cro_lens.report.render_md import cost_text

    _utf8()
    try:
        validate_url(url)
        if model not in ("sonnet", "opus"):
            raise typer.BadParameter("--model must be sonnet or opus")
        run_id = new_run_id(url)
        folder = (out or runs_dir() / run_id).resolve()
        prov = get_provider(provider_name(provider))
        preflight(prov)
        _notices(prov)
        pipe = Pipeline(
            prov,
            Options(
                model=model,
                given=Given(audience=audience, traffic=traffic, goal=goal),
                feedback=not no_feedback,
            ),
            folder,
            on_event=print_event,
        )
        rep = pipe.run(url, run_id)
    except CroLensError as e:
        _fail(e)
        return
    except ValueError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(2) from e
    typer.echo(f"report: {folder / 'report.md'}")
    typer.echo(f"cost: {cost_text(rep)} ({len(rep.cost.calls)} model calls)")


@app.command()
def resume(
    run: Annotated[str, typer.Argument(help="run id (in $CRO_LENS_HOME/runs) or a run folder path")],
    model: Annotated[str | None, typer.Option("--model", help="sonnet or opus; default: the run's")] = None,
    provider: ProviderOpt = None,
) -> None:
    """Continue a stopped run from the step that did not finish. Never visits the page again."""
    from cro_lens.llm.provider import get_provider, preflight
    from cro_lens.pipeline.run import Pipeline
    from cro_lens.report.render_md import cost_text

    _utf8()
    try:
        if model is not None and model not in ("sonnet", "opus"):
            raise typer.BadParameter("--model must be sonnet or opus")
        given = Path(run)
        folder = (given if given.is_dir() else runs_dir() / run).resolve()
        if not folder.is_dir():
            raise InvalidInput(f"no run called {run}")
        prov = get_provider(provider_name(provider))
        preflight(prov)
        _notices(prov)
        pipe, spec, start = Pipeline.for_resume(prov, folder, on_event=print_event, model=model)
        rep = pipe.resume(spec, start)
    except CroLensError as e:
        _fail(e)
        return
    except ValueError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(2) from e
    typer.echo(f"report: {folder / 'report.md'}")
    typer.echo(f"cost: {cost_text(rep)} ({len(rep.cost.calls)} model calls)")


@app.command()
def ui(port: Annotated[int, typer.Option(help="port on 127.0.0.1")] = 8765) -> None:
    """Start the local web app on 127.0.0.1."""
    import uvicorn

    from cro_lens.web.app import create_app

    _utf8()
    typer.echo(f"cro-lens ui → http://127.0.0.1:{port}")
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")


@app.command("eval")
def eval_cmd() -> None:
    """Your own eval: how often cro-lens was right, from the findings you graded in the web app."""
    from cro_lens.feedback import pct, stats

    _utf8()
    st = stats()
    typer.echo(f"graded: {st['graded']} findings ({st['valid']} valid · {st['invalid']} invalid)")
    typer.echo(f"precision: {pct(st['precision'], 'pending grades')}")
    validity = pct(st["evidence_validity"], "pending runs")
    over = f" over {st['evidence_runs']} runs" if st["evidence_validity"] is not None else ""
    typer.echo(f"evidence validity: {validity}{over}")
    typer.echo(f"next run learns from: {st['next_run_examples']} graded findings")


def _version(v: bool) -> None:
    if v:
        typer.echo(f"cro-lens {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[bool, typer.Option("--version", callback=_version, is_eager=True)] = False,
) -> None:
    pass


COMMANDS = {"analyze", "resume", "ui", "eval", "--help", "-h", "--version"}


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] not in COMMANDS and not argv[0].startswith("-"):
        sys.argv.insert(1, "analyze")
    app()


if __name__ == "__main__":
    main()
