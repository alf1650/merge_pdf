#!/usr/bin/env python3
import os
import re
import json
import argparse
import numpy as np
import pdf2image
import easyocr


def extract_3digit_blocks(text):
    """Extract all 3-digit numbers from text (100–999)."""
    return [int(x) for x in re.findall(r'\b\d{3}\b', text) if 100 <= int(x) <= 999]


def crop_block_table_region(pil_image, page_index=None):
    """
    Crop the right-side remarks section where block numbers like 'Blk107Lvl 05' appear.
    Adjust ratios based on actual layout inspection.
    """
    width, height = pil_image.size
    # Focus on the right side
    left = int(width * 0.60)    # Start from 60% width (more rightward)
    right = width               # Full right edge

    # Focus on middle-bottom where remarks usually are
    top = int(height * 0.50)    # Start from 50% height (middle)
    bottom = int(height * 0.90) # Go down to 90% height (near bottom)

    cropped = pil_image.crop((left, top, right, bottom))

    # DEBUG: Save first page crop to inspect
    if page_index == 0:
        cropped.save("debug_remarks_crop_page1.jpg")
        print("📸 Saved debug crop of remarks area: debug_remarks_crop_page1.jpg")

    return cropped


def ocr_pdf(pdf_path: str, dpi: int = 200, lang: str = "en"):
    print(f"🖼️ Converting pages for OCR: {os.path.basename(pdf_path)} (dpi={dpi})")
    pil_pages = pdf2image.convert_from_path(pdf_path, dpi=dpi)
    reader = easyocr.Reader([lang], verbose=False)

    raw_pages = []
    cleaned_pages = []

    for i, im in enumerate(pil_pages):
        print(f"  📄 OCR page {i+1} (block table only)...", end="")

        # Crop to block table region (top-right)
        table_img = crop_block_table_region(im)
        arr = np.array(table_img)
        text_items = reader.readtext(arr, detail=0)
        text = " ".join(text_items)

        blocks = extract_3digit_blocks(text)
        raw_pages.append(blocks)

        # Deduplicate (keep first occurrence), then sort ascending
        unique = list(dict.fromkeys(blocks))
        sorted_blocks = sorted(unique)
        cleaned_pages.append(sorted_blocks)

        print(f" {sorted_blocks}")

    print("\n✅ Block extraction complete (no global noise removal).\n")
    return raw_pages, cleaned_pages, []


def main():
    ap = argparse.ArgumentParser(description="Extract 3-digit block numbers per page → JSON")
    ap.add_argument("--input-pdf-dir", default="/Users/alfredlim/Redpower/merge_pdf/input")
    ap.add_argument("--output-json-dir", default="/Users/alfredlim/Redpower/merge_pdf/ocr")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--lang", default="en")
    args = ap.parse_args()

    os.makedirs(args.output_json_dir, exist_ok=True)
    pdf_files = [f for f in os.listdir(args.input_pdf_dir) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print("❌ No PDFs found.")
        return

    for pdf_name in pdf_files:
        pdf_path = os.path.join(args.input_pdf_dir, pdf_name)
        raw_pages, cleaned_pages, _ = ocr_pdf(pdf_path, dpi=args.dpi, lang=args.lang)

        payload = {
            "pdf": pdf_name,
            "dpi": args.dpi,
            "pages": [
                {
                    "page_index": i,
                    "raw_blocks": raw,
                    "clean_blocks": clean
                }
                for i, (raw, clean) in enumerate(zip(raw_pages, cleaned_pages))
            ],
            "global_noise_blocks": [],  # Not used — removed for safety
        }

        out_json = os.path.join(
            args.output_json_dir,
            os.path.splitext(pdf_name)[0] + "_blocks.json"
        )
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"✅ JSON saved → {out_json}")


if __name__ == "__main__":
    main()