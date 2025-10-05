import os
import re
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image
import io

def extract_block_numbers_from_filename(filename):
    match = re.match(r'^(\d{3})', filename)
    if match:
        return int(match.group(1))
    else:
        print(f"Warning: Could not extract block number from image: {filename}")
        return None

# ✅ HARDCODED BLOCKS PER PAGE — based on your actual PDF content
BLOCKS_PER_PAGE = [
    [107, 108, 109, 110, 111, 112, 113, 114],          # Page 1
    [115, 115, 115, 115, 116, 117, 118, 120],          # Page 2 (115A/B/C → 115)
    [121, 122, 123, 124, 125, 126, 128, 130],          # Page 3
    [131, 132, 134, 136, 137, 138, 139, 140],          # Page 4
    [141, 142, 145, 146, 147, 148, 149, 150],          # Page 5
    [151, 153, 154, 155, 157, 159, 160, 161],          # Page 6
    [162, 165, 166, 167, 170, 171, 172, 173],          # Page 7
    [174, 175, 265, 266, 269, 270, 272, 273],          # Page 8
    [274, 275, 276, 277, 278, 279, 280, 283],          # Page 9
    [284, 286, 287, 288, 289]                           # Page 10
]

def create_image_page(image_path, output_pdf_writer, width=612, height=792):
    img = Image.open(image_path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    img.thumbnail((width, height), Image.Resampling.LANCZOS)

    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader

    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    img_reader = ImageReader(img)
    img_width, img_height = img.size
    x = (width - img_width) / 2
    y = (height - img_height) / 2
    can.drawImage(img_reader, x, y, img_width, img_height)
    can.showPage()
    can.save()

    packet.seek(0)
    temp_reader = PdfReader(packet)
    output_pdf_writer.add_page(temp_reader.pages[0])

def main():
    pdf_file = "input/DRY RISER CP.pdf"
    image_dir = "/Users/alfredlim/Redpower/merge_pdf/images"
    output_file = "output/DRY_RISER_CP_WITH_IMAGES.pdf"

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # Get image files
    image_files = [f for f in os.listdir(image_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]

    # Group images by block number
    images_by_block = {}
    for img_file in image_files:
        block_num = extract_block_numbers_from_filename(img_file)
        if block_num is not None:
            images_by_block.setdefault(block_num, []).append(img_file)
        else:
            print(f"Skipping (no block): {img_file}")

    # Build output PDF
    reader = PdfReader(pdf_file)
    writer = PdfWriter()

    for page_num, blocks_on_page in enumerate(BLOCKS_PER_PAGE):
        # Add original checklist page
        writer.add_page(reader.pages[page_num])
        print(f"📄 Page {page_num + 1}: Blocks {blocks_on_page}")

        # Add matching images
        added = False
        for block in blocks_on_page:
            if block in images_by_block:
                for img_file in images_by_block[block]:
                    print(f"  ➕ Adding: {img_file}")
                    create_image_page(os.path.join(image_dir, img_file), writer)
                    added = True
        if not added:
            print("  ➖ No images for this page")

    # Save
    with open(output_file, "wb") as fh:
        writer.write(fh)

    print(f"\n✅ Done! Output saved as '{output_file}'")

if __name__ == "__main__":
    main()