# merge_pdf

Generate block-mapping JSON files from checklist PDFs, then use them for PDF image merge workflows.

## What this folder does

- Reads checklist PDFs from input
- Extracts page-level equipment type and block numbers
- Writes JSON files to ocr in the format expected by main.py
- Merges checklist PDFs with matched defect images
- Produces per-run attachment audit files in output

## Generate JSON from PDFs

Script: generate_blocks_json.py

Default behavior:

- Input folder: /Users/alfredlim/Redpower/merge_pdf/input
- Output folder: /Users/alfredlim/Redpower/merge_pdf/ocr
- Output filename pattern: <PDF_BASENAME>_blocks.json

Run command:

/Users/alfredlim/Redpower/venv/bin/python /Users/alfredlim/Redpower/merge_pdf/generate_blocks_json.py

Optional custom paths:

/Users/alfredlim/Redpower/venv/bin/python /Users/alfredlim/Redpower/merge_pdf/generate_blocks_json.py --input-pdf-dir /path/to/input --output-json-dir /path/to/ocr

## Run Merge Pipeline

Script: main.py

Run command:

/Users/alfredlim/Redpower/venv/bin/python /Users/alfredlim/Redpower/merge_pdf/main.py

Pipeline behavior:

- Reads PDFs from input
- Reads block JSON mappings from ocr
- Matches images from images by equipment + block
- Writes merged PDFs into output
- Rebuilds audit files on every run (fresh)

## Output files

Main outputs in output:

- <REPORT_NAME> (with images)_combined.pdf

Audit outputs in output:

- attached_images_by_file.json: image filenames attached per report
- attachment_audit_summary.json: run summary (processed reports, attached count, unused count)
- unused_images.json: image filenames not attached in that run

## Recommended run order

1. Regenerate JSON mappings:

	/Users/alfredlim/Redpower/venv/bin/python /Users/alfredlim/Redpower/merge_pdf/generate_blocks_json.py

2. Run merge + fresh audit:

	/Users/alfredlim/Redpower/venv/bin/python /Users/alfredlim/Redpower/merge_pdf/main.py

## JSON schema

Each generated file contains:

- pdf: source PDF filename
- pages: list of page objects

Each page object:

- page_index: zero-based page number
- equipment: normalized equipment code (for example fas, hr, fe, pt, dr, sprinkler, genset)
- blocks: ordered block list found on that page

## Notes

- Running the generator overwrites existing JSON files with the same name.
- Existing extra JSON files in ocr that do not match current input PDFs are not deleted automatically.
- main.py overwrites audit files in output on each run so they always reflect the latest execution.
