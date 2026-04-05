import os
import re
import io
import img2pdf  # For reliable image-to-PDF conversion
from PyPDF2 import PdfReader, PdfWriter

# ✅ BLOCKS PER PAGE — extracted from DRY DISER NSC.pdf
# Alphanumeric blocks (e.g., 671A, 701B) are normalized to base number (671, 701) for image matching
BLOCKS_PER_PAGE = [
    [602, 603, 604, 605, 606, 607, 609, 610],
    [611, 612, 613, 614, 615, 617, 618, 619],
    [632, 633, 634, 635, 636, 637, 638, 639],
    [640, 641, 642, 643, 644, 645, 646, 647],
    [651, 652, 653, 654, 655, 657, 658, 660],
    [661, 662, 663, 664, 665, 666, 671, 671],   # 671A → 671
    [671, 672, 672, 672, 673, 673, 673, 673],   # 672A/B/C → 672, etc.
    [674, 674, 674, 675, 675, 675, 675, 676],   # 674A/B → 674
    [676, 676, 676, 677, 677, 677, 701, 701],   # 701B → 701
    [703, 704, 706, 707, 709, 710, 712, 713],
    [714, 715, 716, 717, 718, 719, 720, 721],
    [722, 723, 724, 725, 726, 727, 728, 729],
    [730, 733, 734, 735, 736, 737, 738, 739],
    [740, 741, 742, 745, 746, 749, 750, 751],
    [752, 754, 755, 756, 757, 758, 759, 760],
    [762, 764, 765, 766, 768, 770, 771, 772],
    [773, 774, 926, 927, 928, 930, 931, 932],
    [935]  # Last page
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
    pdf_file = "input/DRY RISER NSC.pdf"        # Input PDF path
    image_dir = "images"                        # Folder with images (e.g., "674_MSCP_....jpg")
    output_file = "output/DRY_RISER_NSC_WITH_IMAGES.pdf"

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