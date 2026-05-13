from pathlib import Path
from string import Template
from datetime import datetime, timezone
from importlib.resources import as_file, files
import boto3
import json
import html
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

APP_DIR = Path.cwd().resolve()

BUILD_DIR = APP_DIR / "dist"
DOWNLOAD_DIR = BUILD_DIR / "downloads"

LARGE_FILE_THRESHOLD_BYTES = 25 * 1024 * 1024

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


def env_or_error(name):
    value = os.getenv(name, "").strip()
    if value:
        return value

    raise RuntimeError(
        f"Missing required environment variable: {name}"
    )


def normalize_bucket_prefix(value):
    cleaned = []

    for char in value.lower():
        if char.isalnum():
            cleaned.append(char)
        else:
            cleaned.append("-")

    normalized = "".join(cleaned).strip("-")

    if not normalized:
        normalized = "sagemotion-app"

    return normalized[:26].strip("-") or "sagemotion-app"


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
        "zip_filename_raw": zip_filename,
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
        "download_href": html.escape(f"./downloads/{zip_filename}"),
        "download_attr": " download",
        "download_note_block": "",
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


def iter_repo_files():
    for path in APP_DIR.rglob("*"):
        if not path.is_file():
            continue

        relative = path.relative_to(APP_DIR)

        if should_exclude(relative):
            continue

        yield path, relative


def create_zip(zip_filename):
    zip_path = DOWNLOAD_DIR / zip_filename

    with zipfile.ZipFile(
        zip_path,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as zf:
        for path, relative in iter_repo_files():
            zf.write(path, relative)

    return zip_path


def cf_api_request(method, path, token, payload=None):
    url = f"https://api.cloudflare.com/client/v4{path}"
    body = None
    headers = {
        "Authorization": f"Bearer {token}",
    }

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers=headers,
    )

    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Cloudflare API request failed ({method} {path}): "
            f"{exc.code} {error_body}"
        ) from exc


def create_r2_bucket(account_id, api_token):
    prefix = normalize_bucket_prefix(
        os.getenv("SAGEMOTION_R2_BUCKET_PREFIX", "sagemotion-app")
    )
    suffix = str(uuid.uuid4())
    bucket_name = f"{prefix}-{suffix}".lower()

    payload = {"name": bucket_name}

    location_hint = os.getenv("SAGEMOTION_R2_LOCATION_HINT", "").strip()
    if location_hint:
        payload["locationHint"] = location_hint

    storage_class = os.getenv("SAGEMOTION_R2_STORAGE_CLASS", "").strip()
    if storage_class:
        payload["storageClass"] = storage_class

    cf_api_request(
        "POST",
        f"/accounts/{account_id}/r2/buckets",
        api_token,
        payload,
    )

    return bucket_name


def get_public_bucket_url(account_id, api_token, bucket_name):
    response = cf_api_request(
        "PUT",
        (
            f"/accounts/{account_id}/r2/buckets/"
            f"{bucket_name}/domains/managed"
        ),
        api_token,
        {"enabled": True},
    )

    result = response.get("result") or {}
    domain = result.get("domain", "").strip()

    if not domain:
        raise RuntimeError(
            f"Cloudflare did not return an r2.dev domain for {bucket_name}"
        )

    return f"https://{domain}"


def upload_file_to_r2(bucket_name, object_key, file_path):
    account_id = env_or_error("SAGEMOTION_R2_ACCOUNT_ID")
    access_key_id = env_or_error("SAGEMOTION_R2_ACCESS_KEY_ID")
    secret_access_key = env_or_error("SAGEMOTION_R2_SECRET_ACCESS_KEY")

    client = boto3.client(
        service_name="s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
    )

    try:
        client.upload_file(str(file_path), bucket_name, object_key)
    except Exception as exc:
        raise RuntimeError(
            f"R2 object upload failed for {object_key}: {exc}"
        ) from exc


def zip_requires_external_storage(zip_path):
    return zip_path.stat().st_size > LARGE_FILE_THRESHOLD_BYTES


def configure_download(context, zip_path):
    if not zip_requires_external_storage(zip_path):
        return False

    account_id = env_or_error("SAGEMOTION_R2_ACCOUNT_ID")
    api_token = env_or_error("SAGEMOTION_R2_API_TOKEN")

    bucket_name = create_r2_bucket(account_id, api_token)
    public_bucket_url = get_public_bucket_url(
        account_id,
        api_token,
        bucket_name,
    )

    object_prefix = os.getenv(
        "SAGEMOTION_R2_OBJECT_PREFIX",
        "downloads",
    ).strip().strip("/")
    object_key = (
        f"{object_prefix}/{zip_path.name}"
        if object_prefix
        else zip_path.name
    )

    upload_file_to_r2(bucket_name, object_key, zip_path)

    context["download_href"] = html.escape(
        f"{public_bucket_url}/{urllib.parse.quote(object_key, safe='/-_.~')}"
    )
    context["download_attr"] = ""
    context["download_note_block"] = (
        "<p>Your download is ready.</p>"
    )
    return True


def main():
    info = load_info()

    context = build_context(info)

    clean_build_dir()
    zip_path = create_zip(context["zip_filename_raw"])
    zip_size_bytes = zip_path.stat().st_size
    using_external_storage = configure_download(context, zip_path)
    if using_external_storage:
        zip_path.unlink()

    render_template(context)
    copy_publish_assets()

    print(f"Built site for {context['app_name']}")
    print(f"Zip: {context['zip_filename_raw']}")
    print(f"Zip size: {zip_size_bytes} bytes")
    if using_external_storage:
        print("Download storage: external")
    else:
        print("Download storage: local dist/downloads")


if __name__ == "__main__":
    main()
