from pathlib import Path
from string import Template
from datetime import datetime, timezone
from importlib.resources import as_file, files
import subprocess
import zipfile
import json
import html
import os
import shutil

APP_DIR = Path.cwd().resolve()

BUILD_DIR = APP_DIR / "dist"
DOWNLOAD_DIR = BUILD_DIR / "downloads"

INFO_FILE = APP_DIR / "info.json"
TEMPLATE_FILE = files("sagemotion_publish.templates").joinpath("index.html")
LOGO_FILE = files("sagemotion_publish.assets").joinpath(
    "sagemotion_logo.png"
)

EXCLUDE_DIRS = {
    ".git",
    ".github",
    "dist",
    "publish",
    "sagemotion_publish",
    "__pycache__",
}

EXCLUDE_FILES = {
    ".gitignore",
}


def git_output(args, fallback="unknown"):
    try:
        return subprocess.check_output(
            args,
            cwd=APP_DIR,
            text=True,
        ).strip()
    except Exception:
        return fallback


def load_info():
    with open(INFO_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_context(info):
    app_name = info.get("app_name", "Unnamed App")
    app_id = info.get("app_id", "unknown")
    app_version = info.get("app_version", "unknown")

    zip_filename = (
        f"{app_id}_{app_name.replace(' ', '_')}_{app_version}.zip"
    )

    return {
        "app_name": html.escape(app_name),
        "app_id": html.escape(app_id),
        "app_version": html.escape(app_version),
        "zip_filename": html.escape(zip_filename),
        "commit_hash": html.escape(
            git_output(["git", "rev-parse", "--short", "HEAD"])
        ),
        "commit_hash_full": html.escape(
            git_output(["git", "rev-parse", "HEAD"])
        ),
        "commit_message": html.escape(
            git_output(["git", "log", "-1", "--pretty=%s"])
        ),
        "commit_date": html.escape(
            git_output(
                ["git", "log", "-1", "--date=iso-strict", "--pretty=%cd"]
            )
        ),
        "publish_date": html.escape(
            datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        ),
    }


def clean_build_dir():
    if BUILD_DIR.exists():
        for root, dirs, files in os.walk(BUILD_DIR, topdown=False):
            for file in files:
                Path(root, file).unlink()

            for directory in dirs:
                Path(root, directory).rmdir()

        BUILD_DIR.rmdir()

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def render_template(context):
    with as_file(TEMPLATE_FILE) as template_path:
        with open(template_path, "r", encoding="utf-8") as f:
            template = Template(f.read())

    rendered = template.safe_substitute(context)

    output_file = BUILD_DIR / "index.html"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(rendered)


def copy_publish_assets():
    with as_file(LOGO_FILE) as logo_path:
        shutil.copy2(logo_path, BUILD_DIR / logo_path.name)


def should_exclude(path: Path):
    parts = set(path.parts)

    if parts & EXCLUDE_DIRS:
        return True

    if path.name in EXCLUDE_FILES:
        return True

    return False


def create_zip(zip_filename):
    zip_path = DOWNLOAD_DIR / zip_filename

    with zipfile.ZipFile(
        zip_path,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as zf:
        for path in APP_DIR.rglob("*"):
            if not path.is_file():
                continue

            relative = path.relative_to(APP_DIR)

            if should_exclude(relative):
                continue

            zf.write(path, relative)


def main():
    info = load_info()

    context = build_context(info)

    clean_build_dir()

    render_template(context)
    copy_publish_assets()

    create_zip(context["zip_filename"])

    print(f"Built site for {context['app_name']}")
    print(f"Zip: {context['zip_filename']}")


if __name__ == "__main__":
    main()
