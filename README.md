# `sagemotion-publish`

Shared publishing tooling for SageMotion app repositories.

This package bundles the shared publish template, branding assets, and build
logic so individual app repos only need their app-specific files.

## What it does

When run as a module:

```bash
python -m sagemotion_publish
```

the package:

- reads app metadata from `info.json` in the current working directory
- scans the repo for any included file larger than 25 MiB
- builds `dist/index.html`
- copies bundled shared assets into `dist/`
- creates a downloadable app zip in `dist/downloads/`
- uploads the zip to Cloudflare R2 instead of serving it locally when a file
  larger than 25 MiB is present

## Expected app repo layout

At minimum, run the command from an app directory that includes:

```text
info.json
core.py
config.json
snapshot.json
```

Additional app files are included in the generated zip unless excluded by the
build script.

## Large file fallback

If any included repo file is larger than `25 MiB`, the build switches the app
download to external object storage. In that mode, the generated page still
shows a normal download link and does not expose the storage provider in the
UI.

Required environment variables for R2 mode:

```text
SAGEMOTION_R2_ACCOUNT_ID
SAGEMOTION_R2_API_TOKEN
SAGEMOTION_R2_ACCESS_KEY_ID
SAGEMOTION_R2_SECRET_ACCESS_KEY
```

Optional environment variables:

```text
SAGEMOTION_R2_BUCKET_PREFIX
SAGEMOTION_R2_LOCATION_HINT
SAGEMOTION_R2_STORAGE_CLASS
SAGEMOTION_R2_OBJECT_PREFIX
```

Notes:

- bucket names are generated as `<prefix>-<uuid>`
- upload credentials are only read server-side from env vars and are never
  embedded into the generated site
- the public link is download-only; the page does not expose any upload path or
  write credentials

## Install

```bash
pip install git+https://github.com/SageMotionApps/SageMotion-Publish.git
```

## Usage

From inside an app repository:

```bash
python -m sagemotion_publish
```

## Development

For local development in this repository:

```bash
pip install -e .
python -m sagemotion_publish
```

The package loads shared resources from:

- `sagemotion_publish/templates/`
- `sagemotion_publish/assets/`
