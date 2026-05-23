from __future__ import annotations

import json as json_module
import sys
from datetime import datetime

import flickrapi
import typer
from rich.console import Console
from rich.table import Table

from flickrfinder.config import load_config
from flickrfinder.core import downloads as downloads_engine
from flickrfinder.core import facets as facets_engine
from flickrfinder.core import flickr_client
from flickrfinder.core import search as search_engine
from flickrfinder.core import sync as sync_engine
from flickrfinder.core.db import session_scope

app = typer.Typer(
    help="Search your Flickr photos by EXIF metadata.",
    no_args_is_help=True,
    add_completion=False,
)
db_app = typer.Typer(help="Database utilities.", no_args_is_help=True)
app.add_typer(db_app, name="db")
console = Console()


@app.command()
def auth() -> None:
    """One-time Flickr OAuth login. Token is cached on disk by flickrapi."""
    cfg = load_config()
    flickr = flickr_client.build_client(cfg, require_auth=False)
    if flickr.token_cache.token is not None and not typer.confirm(
        "A token is already stored. Replace it?", default=False
    ):
        raise typer.Exit(0)
    info = flickr_client.do_oauth_flow(cfg)
    console.print(
        f"[green]Authenticated as[/green] [bold]{info['username']}[/bold] "
        f"([dim]{info['user_nsid']}[/dim])"
    )


@app.command()
def whoami() -> None:
    """Print the currently authenticated Flickr user."""
    cfg = load_config()
    try:
        flickr = flickr_client.build_client(cfg)
    except flickr_client.NotAuthenticated as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    user = flickr.test.login()["user"]
    username = user["username"]["_content"]
    nsid = user["id"]
    person = flickr.people.getInfo(user_id=nsid)["person"]
    count = person.get("photos", {}).get("count", {}).get("_content", "?")
    console.print(f"[bold]{username}[/bold] ([dim]{nsid}[/dim]) — {count} photos")


@app.command()
def logout() -> None:
    """Clear the cached OAuth token."""
    cfg = load_config()
    flickr_client.clear_saved_token(cfg)
    console.print("[green]Token cleared.[/green]")


@app.command("smoke-test")
def smoke_test(
    limit: int = typer.Option(5, "--limit", "-n", help="How many photos to fetch."),
) -> None:
    """Fetch metadata + EXIF for a few photos and print them. Phase 1 sanity check."""
    cfg = load_config()
    try:
        flickr = flickr_client.build_client(cfg)
    except flickr_client.NotAuthenticated as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    nsid = flickr.test.login()["user"]["id"]
    page = flickr.people.getPhotos(
        user_id=nsid,
        per_page=limit,
        page=1,
        extras="date_taken,date_upload,last_update,tags,url_t,url_m,o_dims",
    )
    photos = page["photos"]["photo"]
    if not photos:
        console.print("[yellow]No photos found for this account.[/yellow]")
        return

    for p in photos:
        console.rule(f"{p.get('title') or '(untitled)'} — id {p['id']}")
        meta = Table(show_header=False, box=None)
        for k in ("datetaken", "dateupload", "lastupdate", "tags", "url_t", "url_m"):
            if k in p:
                meta.add_row(k, str(p[k]))
        console.print(meta)

        try:
            exif_resp = flickr.photos.getExif(photo_id=p["id"])
        except flickrapi.exceptions.FlickrError as e:
            console.print(f"[yellow]No EXIF available: {e}[/yellow]")
            continue
        exif = exif_resp.get("photo", {}).get("exif", [])
        if not exif:
            console.print("[yellow]No EXIF available.[/yellow]")
            continue
        t = Table(title="EXIF")
        t.add_column("tag")
        t.add_column("label")
        t.add_column("raw")
        for e in exif:
            t.add_row(e.get("tag", ""), e.get("label", ""), e.get("raw", {}).get("_content", ""))
        console.print(t)


@app.command()
def sync(
    ids: str | None = typer.Option(
        None,
        "--ids",
        help="Comma-separated photo IDs to sync. Skips the full pagination phase.",
    ),
    max_photos: int | None = typer.Option(
        None,
        "--max",
        help="Limit total photos enumerated in phase A (for testing).",
    ),
    page_size: int = typer.Option(500, "--page-size", help="Photos per getPhotos page."),
) -> None:
    """Sync metadata + EXIF from Flickr into the local DB. Resumes if interrupted."""
    cfg = load_config()
    try:
        if ids:
            id_list = [s.strip() for s in ids.split(",") if s.strip()]
            sync_engine.sync_ids(cfg, id_list, console=console)
        else:
            sync_engine.sync_full(cfg, max_photos=max_photos, page_size=page_size, console=console)
    except flickr_client.NotAuthenticated as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None


@db_app.command("stats")
def db_stats_cmd() -> None:
    """Print row counts and sync state."""
    cfg = load_config()
    stats = sync_engine.db_stats(cfg)
    t = Table(show_header=False, box=None)
    for k, v in stats.items():
        t.add_row(k, f"{v:,}")
    console.print(t)


@db_app.command("init")
def db_init_cmd() -> None:
    """Create database tables if missing."""
    cfg = load_config()
    from flickrfinder.core.db import init_db

    init_db(cfg)
    console.print(f"[green]Initialized[/green] {cfg.db_path}")


def _parse_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise typer.BadParameter(f"expected YYYY-MM-DD, got {value!r}") from None


@app.command()
def search(
    camera: str | None = typer.Option(None, help="Substring match on Make or Model"),
    make: str | None = typer.Option(None),
    model: str | None = typer.Option(None),
    lens: str | None = typer.Option(None, help="Substring match on LensModel or Lens"),
    focal_length: float | None = typer.Option(None, "--focal-length"),
    focal_min: float | None = typer.Option(None, "--focal-min"),
    focal_max: float | None = typer.Option(None, "--focal-max"),
    aperture: float | None = typer.Option(None),
    aperture_min: float | None = typer.Option(None, "--aperture-min"),
    aperture_max: float | None = typer.Option(None, "--aperture-max"),
    shutter: float | None = typer.Option(None, help="Exposure time in seconds, e.g. 0.004"),
    shutter_min: float | None = typer.Option(None, "--shutter-min"),
    shutter_max: float | None = typer.Option(None, "--shutter-max"),
    shutter_faster_than: float | None = typer.Option(None, "--shutter-faster-than"),
    shutter_slower_than: float | None = typer.Option(None, "--shutter-slower-than"),
    iso: int | None = typer.Option(None),
    iso_min: int | None = typer.Option(None, "--iso-min"),
    iso_max: int | None = typer.Option(None, "--iso-max"),
    taken_after: str | None = typer.Option(None, "--taken-after", help="YYYY-MM-DD"),
    taken_before: str | None = typer.Option(None, "--taken-before", help="YYYY-MM-DD"),
    uploaded_after: str | None = typer.Option(None, "--uploaded-after", help="YYYY-MM-DD"),
    uploaded_before: str | None = typer.Option(None, "--uploaded-before", help="YYYY-MM-DD"),
    tag: list[str] = typer.Option([], "--tag", help="Repeatable; ANDed together"),
    public: bool | None = typer.Option(None, "--public/--private"),
    exif: list[str] = typer.Option(
        [],
        "--exif",
        help="Generic EXIF filter, e.g. 'WhiteBalance=Auto', 'FocalLengthIn35mmFormat>=35'",
    ),
    limit: int = typer.Option(50, "--limit", "-n"),
    offset: int = typer.Option(0),
    order: str = typer.Option("taken", help="taken|uploaded|focal|iso|aperture|shutter"),
    asc: bool = typer.Option(False, "--asc/--desc", help="Sort direction (default desc)"),
    output: str = typer.Option("table", "--format", "-f", help="table|json|ids"),
) -> None:
    """Search your synced photos by EXIF and metadata. See PLAN.md for the full filter list."""
    cfg = load_config()
    try:
        exif_exprs = [search_engine.ExifExpr.parse(e) for e in exif]
        f = search_engine.Filter(
            camera=camera,
            make=make,
            model=model,
            lens=lens,
            focal_length=focal_length,
            focal_min=focal_min,
            focal_max=focal_max,
            aperture=aperture,
            aperture_min=aperture_min,
            aperture_max=aperture_max,
            shutter=shutter,
            shutter_min=shutter_min,
            shutter_max=shutter_max,
            shutter_faster_than=shutter_faster_than,
            shutter_slower_than=shutter_slower_than,
            iso=iso,
            iso_min=iso_min,
            iso_max=iso_max,
            taken_after=_parse_date(taken_after),
            taken_before=_parse_date(taken_before),
            uploaded_after=_parse_date(uploaded_after),
            uploaded_before=_parse_date(uploaded_before),
            tags=tag,
            public=public,
            exif=exif_exprs,
            limit=limit,
            offset=offset,
            sort=order,  # type: ignore[arg-type]
            direction="asc" if asc else "desc",
        )
    except search_engine.FilterError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2) from None

    with session_scope(cfg) as s:
        results, total = search_engine.search(s, f)

    if output == "ids":
        for r in results:
            print(r.id)
        return
    if output == "json":
        print(
            json_module.dumps(
                {
                    "total": total,
                    "results": [
                        {
                            "id": r.id,
                            "title": r.title,
                            "taken_at": r.taken_at.isoformat() if r.taken_at else None,
                            "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
                            "url_t": r.url_t,
                            "url_m": r.url_m,
                            "is_public": r.is_public,
                            "exif": r.exif,
                        }
                        for r in results
                    ],
                },
                indent=2,
            )
        )
        return

    t = Table(show_header=True, header_style="bold")
    t.add_column("id")
    t.add_column("taken")
    t.add_column("title")
    t.add_column("camera")
    t.add_column("lens")
    t.add_column("focal")
    t.add_column("iso")
    t.add_column("f/")
    t.add_column("shutter")
    for r in results:
        t.add_row(
            r.id,
            r.taken_at.strftime("%Y-%m-%d") if r.taken_at else "",
            (r.title or "")[:40],
            r.exif.get("Model", ""),
            r.exif.get("LensModel", r.exif.get("Lens", "")),
            r.exif.get("FocalLength", ""),
            r.exif.get("ISO", r.exif.get("ISOSpeedRatings", "")),
            r.exif.get("FNumber", ""),
            r.exif.get("ExposureTime", ""),
        )
    console.print(t)
    console.print(f"[dim]Showing {len(results)} of {total} matches.[/dim]")


@app.command()
def facets(
    top: int = typer.Option(25, "--top", "-n", help="Top N values per facet"),
) -> None:
    """Show what's actually in your DB: top cameras, lenses, tags, and EXIF fields."""
    cfg = load_config()
    with session_scope(cfg) as s:
        result = facets_engine.compute_facets(s, top=top)

    def render(title: str, values: list[facets_engine.FacetValue]) -> None:
        if not values:
            return
        t = Table(title=title, show_header=False, box=None)
        for v in values:
            t.add_row(v.value, f"{v.count:,}")
        console.print(t)

    render("Cameras (top)", result.cameras)
    render("Lenses (top)", result.lenses)
    render("Tags (top)", result.tags)
    render("EXIF fields present", result.exif_tags)
    console.print(
        "[dim]Use any EXIF field with --exif TAG=VALUE / TAG~=VALUE / TAG>=N (numeric).[/dim]"
    )


@app.command()
def download(
    photo_id: str = typer.Argument(..., help="Flickr photo id"),
    force: bool = typer.Option(False, "--force", help="Re-download even if a cached file exists"),
) -> None:
    """Fetch the original-size image for one photo and store it under data/originals/."""
    cfg = load_config()
    try:
        dl = downloads_engine.download_original(cfg, photo_id, force=force)
    except flickr_client.NotAuthenticated as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    except downloads_engine.DownloadError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2) from None
    mb = dl.bytes / (1024 * 1024)
    console.print(f"[green]Saved[/green] {dl.path} ([dim]{dl.size}, {mb:.1f} MB[/dim])")


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Defaults to FLICKRFINDER_HOST or 127.0.0.1"),
    port: int | None = typer.Option(None, help="Defaults to FLICKRFINDER_PORT or 8765"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Start the REST API. (Web UI is Phase 4; this serves only the API for now.)"""
    cfg = load_config()
    import uvicorn

    uvicorn.run(
        "flickrfinder.api.app:app",
        host=host or cfg.host,
        port=port or cfg.port,
        reload=reload,
    )


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
