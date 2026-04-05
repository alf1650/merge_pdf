import os
import re
import io
import img2pdf  # For reliable image-to-PDF conversion
from PyPDF2 import PdfReader, PdfWriter

# ✅ BLOCKS PER PAGE — extracted from DRY DISER NSC.pdf
# Alphanumeric blocks (e.g., 671A, 701B) are normalized to base number (671, 701) for image matching
BLOCKS_PER_PAGE = [
    [201, 202, 203, 204, 205, 208, 209, 210],
    [211, 211, 212, 212, 213, 214, 215, 216, 217, 218],
    [219, 220, 221, 222, 223, 224, 225, 227],
    [228, 229, 231, 232, 234, 235, 236, 237],
    [238, 240, 241, 242, 243, 244, 245, 246],
    [247, 249, 250, 253, 254, 255, 257, 259],
    [260, 262, 263, 264, 269, 269, 296, 296],   # 269A/B → 269, 296A → 296
    [297, 298, 299, 302, 303, 304, 305, 306],
    [308, 308, 309, 310, 311, 312, 314, 320, 321],
    [322, 323, 324, 325, 326, 327, 328, 329],
    [330, 331, 332, 342, 342, 342, 342, 343],   # 342A/B/C → 342
    [345, 346, 347, 347, 347, 348, 348, 348],   # 347A/B → 347, 348A/B/C → 348
    [348, 349, 350, 351, 352, 353, 354, 355],   # 348D → 348
    [356, 357, 359, 360, 362, 363, 365, 366],
    [367, 315, 315, 315, 315, 316, 316, 316],   # 315A/B/C → 315, 316A/B/C → 316
    [317, 317, 317, 317, 318, 318, 318, 333],   # 317A/B/C → 317, 318A/B/C → 318
    [333, 333, 333, 333, 334, 334, 334, 334],   # 333A/B/C/D → 333, 334A/B/C → 334
    [334, 335, 335, 335, 336, 336, 336, 381],   # 334D → 334, 335A/B/C → 335, 336A/B/C → 336, 381A → 381
    [381, 381, 381, 382, 382, 382, 383, 383],   # 381B/C/D → 381, 382A/B/C → 382, 383A/B → 383
    [384, 384]                                   # 384A/B → 384
]

def extract_block_from_filename(filename):
    """Extract leading 3+ digit block number (e.g., '602', '935') from filename."""
    match = re.match(r'^(\d{3,})', filename)
    return int(match.group(1)) if match else None

def image_to_pdf_page(image_path):
    """Convert image directly to a PDF page using img2pdf (no blank pages)."""
    with open(image_path, "rb") as f:
        pdf_bytes = img2pdf.convert(f)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return reader.pages[0]

def main():
    # 🔧 CONFIGURE THESE PATHS
    pdf_file = "input/DRY RISER NSE.pdf"        # Input PDF path
    image_dir = "images"                        # Folder with images (e.g., "674_MSCP_....jpg")
    output_file = "output/DRY_RISER_NSE_WITH_IMAGES.pdf"

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # Get all image files
    image_files = [
        f for f in os.listdir(image_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ]

    # Group images by block number
    images_by_block = {}
    for img in image_files:
        block = extract_block_from_filename(img)
        if block is not None:
            images_by_block.setdefault(block, []).append(img)
        else:
            print(f"⚠️ Skipping (no block prefix): {img}")

    # Build final PDF
    reader = PdfReader(pdf_file)
    writer = PdfWriter()

    total_pages_in_pdf = len(reader.pages)
    total_pages_defined = len(BLOCKS_PER_PAGE)

    if total_pages_in_pdf != total_pages_defined:
        print(f"⚠️ Warning: PDF has {total_pages_in_pdf} pages, but we defined {total_pages_defined}.")

    for i in range(min(total_pages_in_pdf, total_pages_defined)):
        blocks = BLOCKS_PER_PAGE[i]
        writer.add_page(reader.pages[i])
        print(f"📄 Page {i+1}: Blocks {blocks}")

        added = False
        for block in blocks:
            if block in images_by_block:
                for img_file in images_by_block[block]:
                    img_path = os.path.join(image_dir, img_file)
                    writer.add_page(image_to_pdf_page(img_path))
                    print(f"  ➕ Added: {img_file}")
                    added = True
        if not added:
            print("  ➖ No images for this page")

    # Save output PDF
    with open(output_file, "wb") as f:
        writer.write(f)
    
    print(f"\n✅ Done! Output saved as: {output_file}")

if __name__ == "__main__":
    main()