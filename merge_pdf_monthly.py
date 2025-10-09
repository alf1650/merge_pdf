#!/usr/bin/env python3
import os
import re
import json
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image, ImageFile
import io

ImageFile.LOAD_TRUNCATED_IMAGES = True

def extract_block_from_filename(filename):
    """
    Extract block ID from image filename.
    Supports prefixes:
      - hosereel_
      - fire_extinguisher_
      - pressure_tank_
    Returns block as string (e.g., "115A", "269A") or None.
    """
    basename = os.path.basename(filename)
    basename = os.path.splitext(basename)[0]  # Remove extension

    valid_prefixes = [
        "hosereel_",
        "fire_extinguisher_",
        "pressure_tank_"
    ]

    for prefix in valid_prefixes:
        if basename.startswith(prefix):
            rest = basename[len(prefix):]
            block_candidate = rest.split('_')[0]
            if block_candidate and block_candidate[0].isdigit() and block_candidate.replace('-', '').replace(' ', '').isalnum():
                return block_candidate
    return None

def image_to_pdf_page(image_path, width_points, height_points, dpi=150):
    try:
        with Image.open(image_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Target size in inches
            target_width_in = width_points / 72.0
            target_height_in = height_points / 72.0

            # Convert to pixels at desired DPI
            target_width_px = int(target_width_in * dpi)
            target_height_px = int(target_height_in * dpi)

            img_width, img_height = img.size
            img_ratio = img_width / img_height
            target_ratio = target_width_px / target_height_px

            # Determine new size to fill the target dimensions while preserving aspect ratio
            if img_ratio > target_ratio:
                # Image is wider than target -> fit to target width
                new_width = target_width_px
                new_height = int(new_width / img_ratio)
            else:
                # Image is taller or equal ratio -> fit to target height
                new_height = target_height_px
                new_width = int(new_height * img_ratio)

            # Resize the image using the calculated dimensions
            # This will upscale if new dimensions are larger than original, downscale if smaller
            resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Create canvas at exact target size
            canvas = Image.new('RGB', (target_width_px, target_height_px), (255, 255, 255))

            # Center the resized image on the canvas
            offset_x = (target_width_px - new_width) // 2
            offset_y = (target_height_px - new_height) // 2
            canvas.paste(resized_img, (offset_x, offset_y))

            # Save canvas to PDF buffer
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

    # Build image index: block (str) -> list of image paths
    image_files = [f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    images_by_block = {}
    for img_file in image_files:
        img_path = os.path.join(image_dir, img_file)
        if os.path.getsize(img_path) == 0:
            print(f"⚠️ Skipping empty file: {img_file}")
            continue
        block = extract_block_from_filename(img_file)
        if block is not None:
            images_by_block.setdefault(block, []).append(img_path)
        else:
            print(f"⚠️ Skipping (no valid block): {img_file}")

    # Sort images within each block
    for block in images_by_block:
        images_by_block[block].sort()

    print(f"✅ Loaded {len(image_files)} images for {len(images_by_block)} blocks.")

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

        print(f"\n📄 Processing: {pdf_filename}")
        reader = PdfReader(pdf_path)
        total_pdf_pages = len(reader.pages)
        print(f"   Found {total_pdf_pages} pages in PDF.")

        final_writer = PdfWriter()
        all_collected_image_pages = []

        # First pass: add all original pages + collect matching images
        for i in range(total_pdf_pages):
            original_page = reader.pages[i]
            final_writer.add_page(original_page)

            # Get blocks for this page (if available)
            if i < len(data["pages"]):
                page_info = data["pages"][i]
                blocks = [str(b) for b in page_info["clean_blocks"]]
                print(f"  ➕ Page {i+1}: blocks {blocks}")

                # Collect matching images
                width_pts = float(original_page.mediabox.width)
                height_pts = float(original_page.mediabox.height)
                for block in blocks:
                    if block in images_by_block:
                        for img_path in images_by_block[block]:
                            print(f"    ➕ Queuing image: {os.path.basename(img_path)}")
                            img_page = image_to_pdf_page(img_path, width_pts, height_pts, dpi=150)
                            if img_page:
                                all_collected_image_pages.append(img_page)
            else:
                print(f"  ⚠️ Page {i+1}: no JSON entry — keeping original page only.")

        # Second pass: append all collected images at the END
        for img_page in all_collected_image_pages:
            final_writer.add_page(img_page)

        # Save final PDF
        with open(output_path, "wb") as f:
            final_writer.write(f)
        print(f"✅ Output saved: {output_path}")

    print(f"\n🎉 All done! Outputs in: {output_dir}")

if __name__ == "__main__":
    main()