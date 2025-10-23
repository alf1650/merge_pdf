#!/usr/bin/env python3
import os
import re
import json
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image, ImageFile
import io
import shutil

ImageFile.LOAD_TRUNCATED_IMAGES = True

# Normalize equipment names to match image prefixes
EQUIPMENT_TO_PREFIX = {
    "Fire Alarm": "fire_alarm",
    "Hosereel System": "hosereel_system",
    "Hosereel Pump": "hosereel_pump",
    "Fire Extinguisher": "fire_extinguisher",
    "Pressure Tank": "pressure_tank",
    "Decam": "decam",
}

PREFIX_TO_EQUIPMENT = {v: k for k, v in EQUIPMENT_TO_PREFIX.items()}

def get_base_block(block):
    match = re.search(r'\d{3,}', block)
    if match:
        return match.group(0)
    match = re.search(r'\d+', block)
    return match.group(0) if match else block

def extract_equipment_and_block_from_filename(filename):
    basename = os.path.basename(filename)
    name, ext = os.path.splitext(basename)
    for prefix, equip_name in PREFIX_TO_EQUIPMENT.items():
        if name.startswith(prefix + "_"):
            rest = name[len(prefix) + 1:]
            block_candidate = rest.split('_')[0]
            if block_candidate and block_candidate[0].isdigit():
                cleaned = re.sub(r'[^a-zA-Z0-9/]', '', block_candidate)
                if cleaned:
                    return equip_name, cleaned
    if name and name[0].isdigit():
        cleaned = re.sub(r'[^a-zA-Z0-9/]', '', name)
        if cleaned:
            return None, cleaned
    return None, None

def image_to_pdf_page(image_path, width_points, height_points, dpi=150):
    try:
        with Image.open(image_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            target_width_in = width_points / 72.0
            target_height_in = height_points / 72.0
            target_width_px = int(target_width_in * dpi)
            target_height_px = int(target_height_in * dpi)
            img_width, img_height = img.size
            img_ratio = img_width / img_height
            target_ratio = target_width_px / target_height_px
            if img_ratio > target_ratio:
                new_width = target_width_px
                new_height = int(new_width / img_ratio)
            else:
                new_height = target_height_px
                new_width = int(new_height * img_ratio)
            resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            canvas = Image.new('RGB', (target_width_px, target_height_px), (255, 255, 255))
            offset_x = (target_width_px - new_width) // 2
            offset_y = (target_height_px - new_height) // 2
            canvas.paste(resized_img, (offset_x, offset_y))
            pdf_buffer = io.BytesIO()
            canvas.save(pdf_buffer, format='PDF', resolution=dpi)
            pdf_buffer.seek(0)
            reader = PdfReader(pdf_buffer)
            return reader.pages[0]
    except Exception as e:
        print(f"  ⚠️ Skipped image: {os.path.basename(image_path)} | {e}")
        return None

def split_pdf_into_pages(pdf_path, temp_dir):
    """Split PDF into individual page files."""
    reader = PdfReader(pdf_path)
    page_paths = []
    for i in range(len(reader.pages)):
        writer = PdfWriter()
        writer.add_page(reader.pages[i])
        page_path = os.path.join(temp_dir, f"page_{i+1}.pdf")
        with open(page_path, "wb") as f:
            writer.write(f)
        page_paths.append(page_path)
    return page_paths

def main():
    input_pdf_dir = "/Users/alfredlim/Redpower/merge_pdf/input"
    image_dir = "/Users/alfredlim/Redpower/merge_pdf/images"
    json_dir = "/Users/alfredlim/Redpower/merge_pdf/ocr"
    output_dir = "/Users/alfredlim/Redpower/merge_pdf/output"
    temp_dir = "/Users/alfredlim/Redpower/merge_pdf/temp"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        pdf_files = [f for f in os.listdir(input_pdf_dir) if f.lower().endswith('.pdf')]
        if not pdf_files:
            print("❌ No PDFs found.")
            return

        # Build image index: (equipment, block) -> list of image paths
        image_files = [f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        images_by_equip_block = {}
        for img_file in image_files:
            img_path = os.path.join(image_dir, img_file)
            if os.path.getsize(img_path) == 0:
                continue
            equipment, block = extract_equipment_and_block_from_filename(img_file)
            if block is None:
                continue
            if equipment:
                key = (equipment, block)
                images_by_equip_block.setdefault(key, []).append(img_path)

        for pdf_filename in pdf_files:
            base_name = os.path.splitext(pdf_filename)[0]
            json_path = os.path.join(json_dir, f"{base_name}_blocks.json")
            pdf_path = os.path.join(input_pdf_dir, pdf_filename)
            output_path = os.path.join(output_dir, f"{base_name}_WITH_IMAGES.pdf")

            if not os.path.isfile(json_path):
                print(f"⚠️ Skipping {pdf_filename}: JSON not found")
                continue

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "pages" not in data:
                print(f"⚠️ Skipping {pdf_filename}: 'pages' key not found in JSON")
                continue

            pages_list = data["pages"]
            print(f"\n📄 Processing: {pdf_filename}")

            # Step 1: Split PDF into individual pages
            page_files = split_pdf_into_pages(pdf_path, temp_dir)
            total_pdf_pages = len(page_files)
            print(f"   Split into {total_pdf_pages} pages.")

            final_writer = PdfWriter()
            used_images = set()

            # Step 2: Process each page in isolation
            for i in range(total_pdf_pages):
                page_pdf_path = page_files[i]
                page_reader = PdfReader(page_pdf_path)
                original_page = page_reader.pages[0]
                final_writer.add_page(original_page)

                if i < len(pages_list):
                    page_info = pages_list[i]
                    if "blocks" not in page_info:
                        print(f"  ⚠️ Page {i+1}: missing 'blocks'")
                        continue

                    equipment = page_info.get("equipment", "Unknown")
                    blocks = page_info["blocks"]
                    print(f"  ➕ Page {i+1} ({equipment}): blocks {blocks}")

                    width_pts = float(original_page.mediabox.width)
                    height_pts = float(original_page.mediabox.height)

                    for block in blocks:
                        found = False
                        base_block = get_base_block(block)
                        candidates = [block]
                        if base_block != block:
                            candidates.append(base_block)

                        for cand_block in candidates:
                            key = (equipment, cand_block)
                            matched_images = []
                            if key in images_by_equip_block:
                                matched_images = images_by_equip_block[key]

                            if matched_images:
                                for img_path in matched_images:
                                    if img_path in used_images:
                                        print(f"    ➖ Skipping duplicate image: {os.path.basename(img_path)}")
                                        continue

                                    output_page_num = len(final_writer.pages) + 1
                                    print(f"    ➕ Added image as PDF page {output_page_num}: {os.path.basename(img_path)} (for block {cand_block})")

                                    img_page = image_to_pdf_page(img_path, width_pts, height_pts, dpi=150)
                                    if img_page:
                                        final_writer.add_page(img_page)
                                        used_images.add(img_path)
                                        found = True
                                if found:
                                    break

                        if not found:
                            print(f"    ➖ No image found for block {block} (tried: {candidates})")
                else:
                    print(f"  ⚠️ Page {i+1}: no JSON entry — no images added.")

            # Step 3: Save final PDF
            with open(output_path, "wb") as f:
                final_writer.write(f)
            print(f"✅ Output saved: {output_path}")

    finally:
        # Clean up temp directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

    print(f"\n🎉 All done! Outputs in: {output_dir}")

if __name__ == "__main__":
    main()