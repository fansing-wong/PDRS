# Contributing

PDRS is a course research prototype. Contributions should keep its safety and research boundaries clear.

## Scope

- Keep source images read-only and accept regular image files only.
- Write candidates and reports to a separate output directory; never overwrite existing run data.
- Do not add physical-device access, filesystem directory/deleted-record recovery, cluster-chain traversal, or fragmented-file reassembly to the main application without an explicit project-scope decision.
- Describe validation limits and avoid presenting synthetic results as evidence about real-world recovery rates.

## Local setup

Use Python 3.12 or later:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[validation]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

On POSIX systems, use `.venv/bin/python` in place of the Windows executable path.

## Changes and experiments

- Add or update tests for behavior changes.
- Keep experiment generators deterministic and refuse to overwrite existing datasets.
- Do not commit virtual environments, raw images, generated candidate files, or result directories. The root `.gitignore` excludes the generated experiment folders.
- Include exact commands, Python version, dataset parameters, and known limitations when reporting results.

## Pull requests

Explain the change, its safety impact, how it was checked, and any remaining limitations. Do not include user data, credentials, or private image contents.