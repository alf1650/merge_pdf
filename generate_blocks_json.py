#!/usr/bin/env python3
import argparse
import json
import os
import re

from pypdf import PdfReader


EQUIPMENT_PATTERNS = [
    (re.compile(r"FIRE\s*ALARM|\bFAS\b", re.IGNORECASE), "fas"),
    (re.compile(r"HOSE\s*REEL|HOSEREEL|\bHR\b", re.IGNORECASE), "hr"),
    (re.compile(r"FIRE\s*EXTINGUISHER|\bFE\b", re.IGNORECASE), "fe"),
    (re.compile(r"PRESSURE\s*TANK|\bPT\b", re.IGNORECASE), "pt"),
    (re.compile(r"DECAM", re.IGNORECASE), "decam"),
    (re.compile(r"\bRHE\b", re.IGNORECASE), "rhe"),
    (re.compile(r"SPRINKLER\s*SYSTEM|\bSPRINKLER\b", re.IGNORECASE), "sprinkler"),
    (re.compile(r"GENSET|GENERATOR", re.IGNORECASE), "genset"),
    (re.compile(r"DRY\s*RISER|DRY\s*RIZER", re.IGNORECASE), "dr"),
    (re.compile(r"BOOSTER\s*PUMP|\bBP\b", re.IGNORECASE), "bp"),
    (re.compile(r"TRANSFER\s*PUMP|\bTP\b", re.IGNORECASE), "tp"),
    (re.compile(r"\bRCFS\b", re.IGNORECASE), "rcfs"),
]

BLOCK_RE = re.compile(r"\b(\d{3}[A-Z]?)\b")


def dedupe_keep_order(items):
    seen = set()
    out = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def equipment_from_filename(pdf_name):
    upper = pdf_name.upper()
    hints = [
        ("FAS", "fas"),
        ("HOSEREEL", "hr"),
        ("FIRE EXTINGUISHER", "fe"),
        ("PRESSURE TANK", "pt"),
        ("DECAM", "decam"),
        ("RHE", "rhe"),
        ("SPRINKLER", "sprinkler"),
        ("GENSET", "genset"),
        ("DRY RISER", "dr"),
        ("BP", "bp"),
        ("TP", "tp"),
        ("RCFS", "rcfs"),
    ]
    for needle, code in hints:
        if needle in upper:
            return code
    return "unknown"


def extract_equipment(text, fallback):
    for pattern, code in EQUIPMENT_PATTERNS:
        if pattern.search(text):
            return code
    return fallback


def extract_blocks(text):
    lines = text.splitlines()
    upper_lines = [line.upper() for line in lines]

    candidate_parts = []
    for i, line in enumerate(upper_lines):
        if "CHECKLIST" in line or "BLOCK NO" in line:
            candidate_parts.append(line)
            if i + 1 < len(upper_lines):
                candidate_parts.append(upper_lines[i + 1])

    if candidate_parts:
        blocks = BLOCK_RE.findall(" ".join(candidate_parts))
        if blocks:
            return dedupe_keep_order(blocks)

    upper = text.upper()
    for anchor in ("CHECKLIST", "BLOCK NO"):
        idx = upper.find(anchor)
        if idx >= 0:
            segment = upper[idx : idx + 400]
            blocks = BLOCK_RE.findall(segment)
            if blocks:
                return dedupe_keep_order(blocks)

    return []


def build_json_for_pdf(pdf_path):
    pdf_name = os.path.basename(pdf_path)
    fallback_equipment = equipment_from_filename(pdf_name)
    reader = PdfReader(pdf_path)

    pages = []
    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        equipment = extract_equipment(text, fallback_equipment)
        blocks = extract_blocks(text)
        pages.append({"page_index": idx, "equipment": equipment, "blocks": blocks})

    return {"pdf": pdf_name, "pages": pages}


def main():
    parser = argparse.ArgumentParser(description="Generate *_blocks.json from PDFs")
    parser.add_argument("--input-pdf-dir", default="/Users/alfredlim/Redpower/merge_pdf/input")
    parser.add_argument("--output-json-dir", default="/Users/alfredlim/Redpower/merge_pdf/ocr")
    args = parser.parse_args()

    os.makedirs(args.output_json_dir, exist_ok=True)
    pdf_files = sorted(f for f in os.listdir(args.input_pdf_dir) if f.lower().endswith(".pdf"))

    if not pdf_files:
        print("No PDFs found.")
        return

    for pdf_name in pdf_files:
        pdf_path = os.path.join(args.input_pdf_dir, pdf_name)
        payload = build_json_for_pdf(pdf_path)
        out_path = os.path.join(args.output_json_dir, os.path.splitext(pdf_name)[0] + "_blocks.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        print(f"Generated: {os.path.basename(out_path)}")


if __name__ == "__main__":
    main()
