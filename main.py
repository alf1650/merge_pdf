#!/usr/bin/env python3
import json
import os
import re
import shutil
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta

from PIL import Image, ImageFile
from pypdf import PdfReader, PdfWriter

ImageFile.LOAD_TRUNCATED_IMAGES = True

_CANONICAL_EQUIPMENT = [
    ("FAS", "fas"),
    ("HR", "hr"),
    ("FE", "fe"),
    ("PT", "pt"),
    ("Decam", "decam"),
    ("RHE", "rhe"),
    ("Sprinkler System", "sprinkler_system"),
    ("BP", "bp"),
    ("TP", "tp"),
    ("RCFS", "rcfs"),
    ("Genset", "genset"),
    ("Sprinkler", "sprinkler"),
    ("DRY RISER", "dr"),
]

PREFIX_TO_EQUIPMENT = {prefix: display for display, prefix in _CANONICAL_EQUIPMENT}

EQUIPMENT_TO_PREFIX = {}
for display, prefix in _CANONICAL_EQUIPMENT:
    EQUIPMENT_TO_PREFIX[display] = prefix
    EQUIPMENT_TO_PREFIX[display.lower()] = prefix
    EQUIPMENT_TO_PREFIX[display.upper()] = prefix
    EQUIPMENT_TO_PREFIX[display.title()] = prefix


def natural_sort_key(filename):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", filename)]


def get_base_block(block):
    match = re.search(r"\d{3,}", block)
    if match:
        return match.group(0)
    match = re.search(r"\d+", block)
    return match.group(0) if match else block


def extract_equipment_and_block_from_filename(filename):
    basename = os.path.basename(filename)
    name, _ext = os.path.splitext(basename)

    for prefix in PREFIX_TO_EQUIPMENT:
        if name.startswith(prefix + "_"):
            rest = name[len(prefix) + 1 :]
            block_candidate = rest.split("_")[0]
            if block_candidate and block_candidate[0].isdigit():
                cleaned = re.sub(r"[^a-zA-Z0-9/]", "", block_candidate)
                if cleaned:
                    return prefix, cleaned

    if name and name[0].isdigit():
        cleaned = re.sub(r"[^a-zA-Z0-9/]", "", name)
        if cleaned:
            return None, cleaned

    return None, None


def _parse_day_first_date(raw_value):
    cleaned = raw_value.strip().replace(".", "-").replace("/", "-")
    for fmt in ("%d-%m-%Y", "%d-%m-%y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def extract_weekly_start_date(pdf_reader):
    # Weekly checklist date is usually near "DATE OF SERVICING" on early pages.
    candidate_text = []
    for page in pdf_reader.pages[: min(3, len(pdf_reader.pages))]:
        candidate_text.append(page.extract_text() or "")
    text = "\n".join(candidate_text)

    servicing_match = re.search(
        r"DATE\s*OF\s*SERVICING[^0-9]{0,40}(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        text,
        re.IGNORECASE,
    )
    if servicing_match:
        parsed = _parse_day_first_date(servicing_match.group(1))
        if parsed:
            return parsed

    for match in re.finditer(r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b", text):
        parsed = _parse_day_first_date(match.group(1))
        if parsed:
            return parsed

    return None


def extract_image_date_from_filename(filename):
    basename = os.path.basename(filename)

    ymd_token = re.search(r"_(\d{8})_PHOTO", basename, re.IGNORECASE)
    if ymd_token:
        try:
            return datetime.strptime(ymd_token.group(1), "%Y%m%d").date()
        except ValueError:
            pass

    photo_iso = re.search(r"PHOTO-(\d{4})-(\d{2})-(\d{2})", basename, re.IGNORECASE)
    if photo_iso:
        try:
            return datetime.strptime("-".join(photo_iso.groups()), "%Y-%m-%d").date()
        except ValueError:
            pass

    return None


def convert_image_to_pdf_file(img_path, width_pts, height_pts, temp_dir):
    try:
        with Image.open(img_path) as img:
            if img.mode != "RGB":
                img = img.convert("RGB")

            target_width_px = int((width_pts / 72.0) * 150)
            target_height_px = int((height_pts / 72.0) * 150)

            img_ratio = img.width / img.height
            target_ratio = target_width_px / target_height_px

            if img_ratio > target_ratio:
                new_width = target_width_px
                new_height = int(new_width / img_ratio)
            else:
                new_height = target_height_px
                new_width = int(new_height * img_ratio)

            resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (target_width_px, target_height_px), "white")
            offset = ((target_width_px - new_width) // 2, (target_height_px - new_height) // 2)
            canvas.paste(resized, offset)

            temp_filename = f"{os.path.basename(img_path)}.pdf"
            temp_path = os.path.join(temp_dir, temp_filename)
            canvas.save(temp_path, "PDF", dpi=(150, 150))
            return temp_path
    except Exception as e:
        print(f"    Error converting image {os.path.basename(img_path)}: {e}")
        return None


def combine_output_pdfs(output_dir):
    print("\nCombining page PDFs...")

    all_files = [f for f in os.listdir(output_dir) if f.lower().endswith(".pdf")]
    page_pattern = re.compile(r"^page(\d+)_(.+)\.pdf$")
    groups = defaultdict(list)

    for f in all_files:
        match = page_pattern.match(f)
        if match:
            site_prefix = match.group(2)
            groups[site_prefix].append(f)

    if not groups:
        print("No pageN_*.pdf files found.")
        return

    for site_prefix, files in groups.items():
        # Always combine by extracted page number to preserve original report order.
        sorted_files = sorted(files, key=lambda f: int(page_pattern.match(f).group(1)))
        merged_writer = PdfWriter()
        total_pages = 0

        print(f"Merging {len(sorted_files)} files for '{site_prefix}'...")
        for file in sorted_files:
            filepath = os.path.join(output_dir, file)
            try:
                reader = PdfReader(filepath)
                page_count = len(reader.pages)
                for page in reader.pages:
                    merged_writer.add_page(page)
                total_pages += page_count
            except Exception as e:
                print(f"  Skip {file}: {e}")

        if total_pages > 0:
            combined_path = os.path.join(output_dir, f"{site_prefix}_combined.pdf")
            with open(combined_path, "wb") as f:
                merged_writer.write(f)
            print(f"  Saved {total_pages}-page PDF: {os.path.basename(combined_path)}")
            for file in sorted_files:
                os.remove(os.path.join(output_dir, file))


def main():
    input_pdf_dir = "/Users/alfredlim/Redpower/merge_pdf/input"
    image_dir = "/Users/alfredlim/Redpower/merge_pdf/images"
    json_dir = "/Users/alfredlim/Redpower/merge_pdf/ocr"
    output_dir = "/Users/alfredlim/Redpower/merge_pdf/output"
    os.makedirs(output_dir, exist_ok=True)

    pdf_files = sorted([f for f in os.listdir(input_pdf_dir) if f.lower().endswith(".pdf")])
    if not pdf_files:
        print("No PDFs found.")
        return

    image_files = [f for f in os.listdir(image_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    total_images_available = len(image_files)
    images_by_equip_block = {}
    attached_images_by_file = {}
    all_attached_images = set()

    for img_file in image_files:
        img_path = os.path.join(image_dir, img_file)
        if os.path.getsize(img_path) == 0:
            continue
        equipment, block = extract_equipment_and_block_from_filename(img_file)
        if block is None:
            continue
        key = (equipment, block)
        images_by_equip_block.setdefault(key, []).append(img_path)

    print(f"Loaded {len(image_files)} images.")
    print(f"Indexed {len(images_by_equip_block)} equipment-block keys.")

    for pdf_filename in pdf_files:
        base_name = os.path.splitext(pdf_filename)[0]
        is_weekly = "WEEKLY" in pdf_filename.upper()
        json_path = os.path.join(json_dir, f"{base_name}_blocks.json")
        pdf_path = os.path.join(input_pdf_dir, pdf_filename)

        if not os.path.isfile(json_path):
            print(f"Skipping {pdf_filename}: JSON not found")
            continue

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        pages_list = data.get("pages")
        if not isinstance(pages_list, list):
            print(f"Skipping {pdf_filename}: invalid 'pages' in JSON")
            continue

        pages_by_index = {
            p.get("page_index"): p
            for p in pages_list
            if isinstance(p, dict) and isinstance(p.get("page_index"), int)
        }

        def should_attach_on_page(page_index):
            """Attach on 2nd page if two consecutive pages have identical blocks/equipment."""
            curr = pages_by_index.get(page_index)
            if not curr:
                return False

            curr_eq = str(curr.get("equipment", "")).strip().lower()
            curr_blocks = curr.get("blocks", [])

            prev = pages_by_index.get(page_index - 1)
            if prev:
                prev_eq = str(prev.get("equipment", "")).strip().lower()
                if prev_eq == curr_eq and prev.get("blocks", []) == curr_blocks:
                    return True

            nxt = pages_by_index.get(page_index + 1)
            if nxt:
                nxt_eq = str(nxt.get("equipment", "")).strip().lower()
                if nxt_eq == curr_eq and nxt.get("blocks", []) == curr_blocks:
                    return False

            return True

        print(f"\nProcessing: {pdf_filename}")
        reader = PdfReader(pdf_path)
        total_pdf_pages = len(reader.pages)
        print(f"  PDF pages: {total_pdf_pages}, JSON entries: {len(pages_list)}")

        weekly_start_date = None
        weekly_end_date = None
        if is_weekly:
            weekly_start_date = extract_weekly_start_date(reader)
            if weekly_start_date:
                weekly_end_date = weekly_start_date + timedelta(days=6)
                print(
                    f"  Weekly date window: {weekly_start_date.isoformat()} to {weekly_end_date.isoformat()}"
                )
            else:
                print("  Weekly date window: not found in checklist, using all matching pictures")

        cache_dir = tempfile.mkdtemp(prefix=f"merge_pdf_{base_name[:20]}_")
        used_images = set()
        report_attached_images = []

        try:
            for i in range(total_pdf_pages):
                page_writer = PdfWriter()
                original_page = reader.pages[i]
                page_writer.add_page(original_page)

                appended_count = 0
                if i in pages_by_index:
                    page_info = pages_by_index[i]
                    raw_equipment = str(page_info.get("equipment", "unknown")).strip()
                    equipment = EQUIPMENT_TO_PREFIX.get(raw_equipment.lower(), raw_equipment.lower())
                    blocks = page_info.get("blocks", [])

                    if not is_weekly and not should_attach_on_page(i):
                        print(f"    Deferring attachments to next page for repeated block set: {blocks}")
                        blocks = []

                    for block in blocks:
                        candidates = [block]
                        base_block = get_base_block(block)
                        if base_block != block:
                            candidates.append(base_block)

                        for cand_block in candidates:
                            key = (equipment, cand_block)
                            matched_images = images_by_equip_block.get(key, [])

                            for img_path in matched_images:
                                if img_path in used_images:
                                    continue

                                if weekly_start_date and weekly_end_date:
                                    image_date = extract_image_date_from_filename(img_path)
                                    if not image_date:
                                        continue
                                    if image_date < weekly_start_date or image_date > weekly_end_date:
                                        continue

                                temp_pdf_path = convert_image_to_pdf_file(
                                    img_path,
                                    float(original_page.mediabox.width),
                                    float(original_page.mediabox.height),
                                    cache_dir,
                                )
                                if not temp_pdf_path:
                                    continue

                                try:
                                    img_reader = PdfReader(temp_pdf_path)
                                    # Add image as next page after remarks section.
                                    page_writer.add_page(img_reader.pages[0])
                                    used_images.add(img_path)
                                    report_attached_images.append(os.path.basename(img_path))
                                    appended_count += 1
                                except Exception as e:
                                    print(
                                        f"    Error appending image {os.path.basename(img_path)} "
                                        f"for block {cand_block}: {e}"
                                    )

                site_prefix = f"{base_name} (with images)"
                output_filename = f"page{i+1}_{site_prefix}.pdf"
                output_path = os.path.join(output_dir, output_filename)

                with open(output_path, "wb") as f:
                    page_writer.write(f)

                print(f"  Saved {output_filename} (appended pages: {appended_count})")

            attached_images_by_file[pdf_filename] = report_attached_images
            all_attached_images.update(report_attached_images)

        finally:
            try:
                shutil.rmtree(cache_dir)
            except Exception as e:
                print(f"Could not clean temp directory {cache_dir}: {e}")

    combine_output_pdfs(output_dir)

    attached_json_path = os.path.join(output_dir, "attached_images_by_file.json")
    with open(attached_json_path, "w", encoding="utf-8") as f:
        json.dump(attached_images_by_file, f, indent=2)

    unused_images = sorted(set(image_files) - all_attached_images)
    summary = {
        "processed_reports": len(pdf_files),
        "files_with_attached_images": sum(1 for v in attached_images_by_file.values() if v),
        "total_attached_images": len(all_attached_images),
        "total_images_available": total_images_available,
        "unused_images_count": len(unused_images),
    }

    summary_json_path = os.path.join(output_dir, "attachment_audit_summary.json")
    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    unused_json_path = os.path.join(output_dir, "unused_images.json")
    with open(unused_json_path, "w", encoding="utf-8") as f:
        json.dump(unused_images, f, indent=2)

    print(f"\nDone. Outputs in: {output_dir}")


if __name__ == "__main__":
    main()
