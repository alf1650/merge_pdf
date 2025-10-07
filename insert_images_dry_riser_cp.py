# merge_pdf_with_easyocr.py

import os
import re
import io
import tempfile
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
import pdf2image
import easyocr
import numpy as np
from natsort import natsorted


def extract_block_from_filename(filename):
    """Extract leading 3-digit block number (e.g., '107' from '107_L5_....jpg')."""
    match = re.match(r'^(\d{3})', filename)
    return int(match.group(1)) if match else None


def get_blocks_from_page_header(pil_image):
    """OCR only the top portion of the page to get clean block numbers."""
    # Crop top 15% of the image (where block numbers appear)
    width, height = pil_image.size
    cropped = pil_image.crop((0, 0, width, int(height * 0.15)))

    reader = easyocr.Reader(['en'], verbose=False)
    results = reader.readtext(np.array(cropped), detail=0)
    text = " ".join(results).replace('\n', ' ')

    # Extract 3-digit blocks (100-999)
    blocks = [int(x) for x in re.findall(r'\b\d{3}\b', text) if 100 <= int(x) <= 999]
    
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for b in blocks:
        if b not in seen:
            unique.append(b)
            seen.add(b)
    return unique


def image_to_pdf_page_safe(image_path, target_width_points, target_height_points, dpi=150):
    try:
        if not os.path.isfile(image_path) or os.path.getsize(image_path) == 0:
            raise OSError("File missing or empty")

        img = Image.open(image_path)
        img.load()
        if img.mode != 'RGB':
            img = img.convert('RGB')

        width_inch = target_width_points / 72.0
        height_inch = target_height_points / 72.0
        target_w = int(width_inch * dpi)
        target_h = int(height_inch * dpi)

        img.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
        canvas = Image.new('RGB', (target_w, target_h), (255, 255, 255))
        offset = ((target_w - img.width) // 2, (target_h - img.height) // 2)
        canvas.paste(img, offset)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            canvas.save(tmp.name, "PDF", resolution=dpi)
            tmp_path = tmp.name

        reader = PdfReader(tmp_path)
        page = reader.pages[0]
        os.unlink(tmp_path)
        return page

    except Exception as e:
        print(f"  ⚠️ Skipped image: {os.path.basename(image_path)} | {e}")
        return None


def main():
    input_pdf_dir = "/Users/alfredlim/Redpower/merge_pdf/input"
    image_dir = "/Users/alfredlim/Redpower/merge_pdf/images"
    output_dir = "/Users/alfredlim/Redpower/merge_pdf/output"
    os.makedirs(output_dir, exist_ok=True)

    pdf_files = [f for f in os.listdir(input_pdf_dir) if f.lower().endswith('.pdf')]
    if not pdf_files:
        print("❌ No PDF files found!")
        return

    # Index images by block
    image_files = [f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    images_by_block = {}
    for img in image_files:
        block = extract_block_from_filename(img)
        if block is not None:
            images_by_block.setdefault(block, []).append(img)

    # Sort naturally
    for block in images_by_block:
        images_by_block[block] = natsorted(images_by_block[block])

    print(f"✅ Loaded {len(image_files)} images for {len(images_by_block)} blocks.")

    for pdf_filename in pdf_files:
        print(f"\n{'='*60}")
        print(f"📄 Processing: {pdf_filename}")
        print('='*60)

        pdf_path = os.path.join(input_pdf_dir, pdf_filename)
        output_path = os.path.join(output_dir, pdf_filename.replace('.pdf', '_WITH_IMAGES.pdf'))

        # Convert PDF to images
        print("🖼️ Converting PDF pages to images...")
        pil_images = pdf2image.convert_from_path(pdf_path, dpi=150)

        orig_reader = PdfReader(pdf_path)
        writer = PdfWriter()

        for i, pil_img in enumerate(pil_images):
            if i >= len(orig_reader.pages):
                break

            # Step 1: Add original page
            writer.add_page(orig_reader.pages[i])

            # Step 2: Extract block numbers from header (top of page)
            blocks = get_blocks_from_page_header(pil_img)
            print(f"\n📄 Page {i+1} | Header blocks: {blocks}")

            # Step 3: Insert matching images
            added = False
            page = orig_reader.pages[i]
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)

            for block in blocks:
                if block in images_by_block:
                    for img_file in images_by_block[block]:
                        img_path = os.path.join(image_dir, img_file)
                        pdf_page = image_to_pdf_page_safe(img_path, w, h, dpi=150)
                        if pdf_page:
                            writer.add_page(pdf_page)
                            print(f"  ➕ Inserted: {img_file}")
                            added = True

            if not added:
                print("  ➖ No matching images")

        # Save
        print(f"\n📊 Final page count: {len(writer.pages)}")
        with open(output_path, "wb") as f:
            writer.write(f)
        print(f"✅ Output: {output_path}")

    print(f"\n🎉 Done! Outputs in: {output_dir}")


if __name__ == "__main__":
    main()