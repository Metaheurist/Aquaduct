# Model-Downloads (offsite bundles)

This folder is **mostly git-ignored** so generated files (including **embedded Hugging Face tokens**) are never committed.

## What’s tracked here

- **`generate_offsite_bundle.py`** — run this on a machine that has your token in the environment (or in `.env`). It writes a **standalone** bundle under **`offsite/`** you can copy to another PC.

## One-time: generate the offsite bundle

From the **repository root** (with `HF_TOKEN` or `HUGGINGFACEHUB_API_TOKEN` set, or in `.env`):

```bash
python Model-Downloads/generate_offsite_bundle.py
```

This creates **`Model-Downloads/offsite/`** (ignored by git) containing:

- `download_all_models.py` — downloads every **curated** Aquaduct model repo into a local `models/` folder next to the script (same folder naming as the app).
- `requirements-offsite.txt` — minimal pip deps for that machine.

## On the “download” PC (no full repo required)

```bash
cd offsite
pip install -r requirements-offsite.txt
python download_all_models.py
```

Copy the resulting **`models/`** directory to your main machine (e.g. into `.Aquaduct_data/models`, or your **External** models path in the app).

## Security

- Treat **`offsite/`** like a secret: anyone with those files can use your Hub token until you revoke it at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).
- Do not zip/upload `offsite/` to public places.
