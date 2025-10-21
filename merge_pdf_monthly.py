#!/usr/bin/env python3
import os
import re
import json
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image, ImageFile
import io

ImageFile.LOAD_TRUNCATED_IMAGES = True

# Normalize equipment names to match image prefixes
EQUIPMENT_TO_PREFIX = {
    "Fire Alarm": "fire_alarm",
    "Hosereel": "hosereel",
    "Fire Extinguisher": "fire_extinguisher",
    "Pressure Tank": "pressure_tank",
    "Decam": "decam",
    # Add more if needed
}

PREFIX_TO_EQUIPMENT = {v: k for k, v in EQUIPMENT_TO_PREFIX.items()}

def extract_equipment_and_block_from_filename(filename):
    """
    Extract (equipment, block) from image filename.
    Returns (equipment_name, block_id) or (None, None).
    """
    basename = os.path.basename(filename)
    name, ext = os.path.splitext(basename)

    # Try known prefixes
    for prefix, equip_name in PREFIX_TO_EQUIPMENT.items():
        if name.startswith(prefix + "_"):
            rest = name[len(prefix) + 1:]  # +1 for underscore
            block_candidate = rest.split('_')[0]
            if block_candidate and block_candidate[0].isdigit():
                cleaned = re.sub(r'[^a-zA-Z0-9/]', '', block_candidate)
                if cleaned:
                    return equip_name, cleaned

    # Fallback: if no prefix, assume block-only, but we can't infer equipment
    # So return (None, block) — will only match if page equipment is ignored (not recommended)
    if name and name[0].isdigit():
        cleaned = re.sub(r'[^a-zA-Z0-9/]', '', name)
        if cleaned:
            return None, cleaned

    return None, None

def image_to_pdf_page(image_path, width_points, height_points, dpi=150):
    # ... (keep your existing implementation unchanged) ...
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

    # Build image index: (equipment, block) -> list of image paths
    image_files = [f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    images_by_equip_block = {}  # key: (equip, block)
    images_by_block_only = {}   # fallback for images without equipment prefix

    for img_file in image_files:
        img_path = os.path.join(image_dir, img_file)
        if os.path.getsize(img_path) == 0:
            print(f"⚠️ Skipping empty file: {img_file}")
            continue

        equipment, block = extract_equipment_and_block_from_filename(img_file)
        if block is None:
            print(f"⚠️ Skipping (no valid block): {img_file}")
            continue

        if equipment:
            key = (equipment, block)
            images_by_equip_block.setdefault(key, []).append(img_path)
            print(f"  📌 Indexed: {key} <- {img_file}")
        else:
            # No equipment in filename — store separately
            images_by_block_only.setdefault(block, []).append(img_path)
            print(f"  📌 Indexed (no equip): {block} <- {img_file}")

    print(f"✅ Loaded {len(image_files)} images.")
    print(f"   - With equipment: {len(images_by_equip_block)} keys")
    print(f"   - Block-only: {len(images_by_block_only)} blocks")

    # Process each PDF
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
        reader = PdfReader(pdf_path)
        total_pdf_pages = len(reader.pages)
        print(f"   Found {total_pdf_pages} pages in PDF.")
        print(f"   JSON defines {len(pages_list)} pages.")

        final_writer = PdfWriter()

        for i in range(total_pdf_pages):
            original_page = reader.pages[i]
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
                image_added = False

                for block in blocks:
                    # First: try exact (equipment, block) match
                    key = (equipment, block)
                    matched_images = []
                    if key in images_by_equip_block:
                        matched_images = images_by_equip_block[key]
                    elif block in images_by_block_only:
                        # Fallback: use block-only images (less accurate)
                        matched_images = images_by_block_only[block]
                        print(f"    ⚠️ Using block-only image for {key} (no equipment match)")

                    for img_path in matched_images:
                        print(f"    ➕ Adding image after page {i+1}: {os.path.basename(img_path)}")
                        img_page = image_to_pdf_page(img_path, width_pts, height_pts, dpi=150)
                        if img_page:
                            final_writer.add_page(img_page)
                            image_added = True

                if not image_added:
                    print(f"    ➖ No images found for page {i+1}")
            else:
                print(f"  ⚠️ Page {i+1}: no JSON entry — no images added.")

        with open(output_path, "wb") as f:
            final_writer.write(f)
        print(f"✅ Output saved: {output_path}")

    print(f"\n🎉 All done! Outputs in: {output_dir}")

if __name__ == "__main__":
    main()