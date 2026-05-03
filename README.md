# merge_pdf

Checklist PDF merge and pump-template generation workflows.

## Core folders

- `input/`: source checklist PDFs
- `ocr/`: per-PDF block mapping JSON files (`*_blocks.json`)
- `images/`: renamed defect pictures used for attachment
- `output/`: merged outputs and audit/report files
- `staged/`: generated/staged checklist variants (including pump template outputs)

## Main merge workflow

Script: `main.py`

Command:

`/Users/alfredlim/Redpower/venv/bin/python /Users/alfredlim/Redpower/merge_pdf/main.py`

What it does:

1. Reads PDFs in `input/`.
2. Looks up block mappings from `ocr/<PDF_STEM>_blocks.json`.
3. Matches images in `images/` by equipment + block.
4. Produces combined PDFs in `output/`.
5. Rebuilds audit files on every run.

Main outputs:

- `<REPORT_NAME> (with images)_combined.pdf`
- `attached_images_by_file.json`
- `attachment_audit_summary.json`
- `unused_images.json`

## JSON generation workflow

Script: `generate_blocks_json.py`

Command:

`/Users/alfredlim/Redpower/venv/bin/python /Users/alfredlim/Redpower/merge_pdf/generate_blocks_json.py`

Optional:

`/Users/alfredlim/Redpower/venv/bin/python /Users/alfredlim/Redpower/merge_pdf/generate_blocks_json.py --input-pdf-dir /path/to/input --output-json-dir /path/to/ocr`

## Pump date planning workflow

Script: `update_pump_dates.py`

Purpose:

- Builds `pump_date_update_plan.csv/json` for pump PDFs.
- Uses image dates for the selected month.
- Can estimate missing dates when no direct image match exists.

Typical command:

`/Users/alfredlim/Redpower/venv/bin/python /Users/alfredlim/Redpower/merge_pdf/update_pump_dates.py --input-dir input --ocr-dir ocr --image-dir images --report-dir output --target-month 2026-04 --estimate-missing`

## Pump template generation workflow

Script: `generate_pump_template_pdfs.py`

Purpose:

- Reads pump date plan CSV.
- Writes dated pump checklist XLSX files.
- Optionally exports PDFs.
- Keeps remarks area clean (row-level border and zero-height row handling).

Typical command:

`/Users/alfredlim/Redpower/venv/bin/python /Users/alfredlim/Redpower/merge_pdf/generate_pump_template_pdfs.py --plan-csv output/pump_date_update_plan.csv --ocr-dir ocr --output-dir staged/pump_template_dates --technician MANI --remarks-text "Please refer to the attached defect photos for the comments indicated" --export-pdf`

## Special ANNUALLY/HALF YEARLY setup

Special image pool rule used in operations:

- include all pictures in `images/_not_april/`
- plus `dr_` pictures from `images/` for the target month (for example `2026-04`)

This special setup is now exposed via `control_server` as a one-click tool (`special_merge_run`).

## Recommended run order

1. `generate_blocks_json.py` when input PDFs change.
2. `update_pump_dates.py` when monthly date references change.
3. `generate_pump_template_pdfs.py` for new pump template outputs.
4. `main.py` for checklist-image merge outputs.

## JSON schema (summary)

Each `*_blocks.json` file contains:

- `pdf`: source PDF filename
- `pages`: list of page objects

Each page object contains:

- `page_index`: zero-based page index
- `equipment`: normalized equipment code
- `blocks`: ordered block list found on that page
