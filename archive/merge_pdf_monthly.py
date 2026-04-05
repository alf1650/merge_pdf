#!/usr/bin/env python3
import os
import re
import json
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image, ImageFile
import io
import tempfile

ImageFile.LOAD_TRUNCATED_IMAGES = True

EQUIPMENT_TO_PREFIX = {
    "FAS": "fas",
    "HR": "hr", 
    "FE": "fe",
    "PT": "pt",
    "Decam": "decam",
    "RHE": "rhe",
    "Sprinkler System": "sprinkler_system",
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

def main():
    input_pdf_dir = "/Users/alfredlim/Redpower/merge_pdf/input"
    image_dir = "/Users/alfredlim/Redpower/merge_pdf/images"
    json_dir = "/Users/alfredlim/Redpower/merge_pdf/ocr"
    output_dir = "/Users/alfredlim/Redpower/merge_pdf/output"
    os.makedirs(output_dir, exist_ok=True)

    pdf_files = [f for f in os.listdir(input_pdf_dir) if f.lower().endswith('.pdf')]
    if not pdf_files:
        print("❌ No PDFs found.")
        return

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

    print(f"✅ Loaded {len(image_files)} images.")
    print(f"   - With equipment: {len(images_by_equip_block)} keys")

    for pdf_filename in pdf_files:
        base_name = os.path.splitext(pdf_filename)[0]
        json_path = os.path.join(json_dir, f"{base_name}_blocks.json")
        pdf_path = os.path.join(input_pdf_dir, pdf_filename)

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
        reader = PdfReader(pdf_path)
        total_pdf_pages = len(reader.pages)
        print(f"   Found {total_pdf_pages} pages in PDF.")
        print(f"   JSON defines {len(pages_list)} pages.")

        used_images = set()

        for i in range(total_pdf_pages):
            page_writer = PdfWriter()
            original_page = reader.pages[i]
            page_writer.add_page(original_page)

            if i < len(pages_list):
                page_info = pages_list[i]
                if "blocks" not in page_info:
                    print(f"  ⚠️ Page {i+1}: missing 'blocks'")
                else:
                    equipment = page_info.get("equipment", "Unknown")
                    blocks = page_info["blocks"]
                    print(f"  ➕ Page {i+1} ({equipment}): blocks {blocks}")

                    width_pts = float(original_page.mediabox.width)
                    height_pts = float(original_page.mediabox.height)
                    image_added = False

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

                                    print(f"    ➕ Adding image: {os.path.basename(img_path)} (for block {cand_block})")

                                    # ✅ CRITICAL: Use temporary file to avoid PyPDF2 buffer bug
                                    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
                                        temp_path = tmp_pdf.name

                                    try:
                                        with Image.open(img_path) as img:
                                            if img.mode != 'RGB':
                                                img = img.convert('RGB')
                                            target_width_in = width_pts / 72.0
                                            target_height_in = height_pts / 72.0
                                            target_width_px = int(target_width_in * 150)
                                            target_height_px = int(target_height_in * 150)
                                            img_ratio = img.width / img.height
                                            target_ratio = target_width_px / target_height_px
                                            if img_ratio > target_ratio:
                                                new_width = target_width_px
                                                new_height = int(new_width / img_ratio)
                                            else:
                                                new_height = target_height_px
                                                new_width = int(new_height * img_ratio)
                                            resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                                            canvas = Image.new('RGB', (target_width_px, target_height_px), 'white')
                                            offset = ((target_width_px - new_width) // 2, (target_height_px - new_height) // 2)
                                            canvas.paste(resized, offset)
                                            canvas.save(temp_path, "PDF", resolution=150)

                                        with open(temp_path, 'rb') as f:
                                            img_reader = PdfReader(f)
                                            page_writer.add_page(img_reader.pages[0])
                                        used_images.add(img_path)
                                        image_added = True
                                        found = True
                                    finally:
                                        if os.path.exists(temp_path):
                                            os.remove(temp_path)

                                if found:
                                    break

                        if not found:
                            print(f"    ➖ No image found for block {block} (tried: {candidates})")

                    if not image_added:
                        print(f"    ➖ No images found for page {i+1}")
            else:
                print(f"  ⚠️ Page {i+1}: no JSON entry — no images added.")

            site_prefix = base_name.split()[0].lower()
            output_filename = f"page{i+1}_{site_prefix}.pdf"
            output_path = os.path.join(output_dir, output_filename)
            
            with open(output_path, "wb") as f:
                page_writer.write(f)
            print(f"✅ Saved: {output_filename}")

    print(f"\n🎉 All done! Outputs in: {output_dir}")

if __name__ == "__main__":
    main()