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
- builds `dist/index.html`
- copies bundled shared assets into `dist/`
- creates a downloadable app zip in `dist/downloads/`

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
