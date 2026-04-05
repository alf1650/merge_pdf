# merge_pdf_with_easyocr.py  (updated: dedup + sort blocks DESC per page)

import os
import re
import io
from PyPDF2 import PdfReader, PdfWriter
import pdf2image  # Converts PDF pages to PIL images
import easyocr
import numpy as np

from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True

# ----------------------------
# Filename → block extraction
# ----------------------------

def extract_block_from_filename(filename: str):
    """Extract leading 3-digit block number (e.g., '107' from '107_L5_....jpg')."""
    match = re.match(r'^(\d{3})', filename)
    return int(match.group(1)) if match else None


# ----------------------------
# Intra-block image sorting
# ----------------------------

L_RE   = re.compile(r'_L(\d+)\b', re.IGNORECASE)                 # _L5, _L10, etc.
SEQ_RE = re.compile(r'(?:_|-)(\d{1,3})(?=\D|$)')                 # trailing _01, -12, etc.

def image_sort_key(name: str):
    """
    Sort inside each block by:
      1) Level number after '_L' (if any)
      2) A simple trailing number token (if any)
      3) Filename (lowercased) as stable fallback
    """
    lvl_match = L_RE.search(name)
    lvl_val = int(lvl_match.group(1)) if lvl_match else 9999

    seq_match = SEQ_RE.search(name)
    seq_val = int(seq_match.group(1)) if seq_match else 9999

    return (lvl_val, seq_val, name.lower())


# ----------------------------
# OCR extraction
# ----------------------------

def get_blocks_per_page_with_ocr(pdf_path: str):
    """
    Use OCR + automatic noise removal.
    - Keeps duplicates per page (no per-page dedup) to match checklist-like behavior
    - Removes "global noise" (numbers present on every page) using presence (set) not counts
    """
    print("🖼️ Converting PDF pages to images for OCR...")
    pil_images = pdf2image.convert_from_path(pdf_path, dpi=150)
    reader = easyocr.Reader(['en'], verbose=False)

    raw_blocks_per_page = []   # keeps duplicates in page order
    page_sets = []             # sets per page for global-noise detection

    for i, pil_img in enumerate(pil_images):
        print(f"  📄 OCR Page {i+1}...", end="")
        img_array = np.array(pil_img)
        results = reader.readtext(img_array, detail=0)
        text = " ".join(results)

        # Only 3-digit numbers from 100 to 999; KEEP duplicates
        blocks = [int(x) for x in re.findall(r'\b\d{3}\b', text) if 100 <= int(x) <= 999]
        raw_blocks_per_page.append(blocks)
        page_sets.append(set(blocks))
        print(f" {blocks}")

    # Numbers that appear on EVERY page (presence-based)
    global_noise = set.intersection(*page_sets) if page_sets else set()
    if global_noise:
        print(f"\n🗑️ Auto-removed global noise (appears on all pages): {sorted(global_noise)}\n")
    else:
        print("\n✅ No global noise detected.\n")

    # Remove only global-noise numbers, preserving order and duplicates of others
    clean_blocks_per_page = []
    for page_blocks in raw_blocks_per_page:
        filtered = [b for b in page_blocks if b not in global_noise]
        clean_blocks_per_page.append(filtered)

    for i, blocks in enumerate(clean_blocks_per_page):
        print(f"  ✅ Page {i+1}: {blocks}")   # shows duplicates if present

    return clean_blocks_per_page


# ----------------------------
# Normalize per-page block list
# ----------------------------

def normalize_page_blocks(
    blocks,
    images_by_block,
    coverage_window=20,
    min_present_for_fill=3,
    coverage_ratio=0.6,
    cluster_gap=3
):
    """
    Normalize OCR-detected blocks for a page.

    Steps:
      - Keep only blocks we have images for.
      - Drop consecutive duplicates.
      - Cluster by proximity (gap <= cluster_gap).
      - Choose the best cluster (most items, then smallest span).
      - Optionally fill within that cluster if coverage looks good.
    """
    # keep only blocks we have images for
    present = [b for b in blocks if b in images_by_block]
    if not present:
        return []

    # drop consecutive duplicates (preserve order)
    dedup_consec = []
    last = None
    for b in present:
        if b != last:
            dedup_consec.append(b)
        last = b

    # sort unique for clustering
    uniq_sorted = sorted(set(dedup_consec))
    if not uniq_sorted:
        return []

    # cluster contiguous-ish sequences by gap
    clusters = []
    cur = [uniq_sorted[0]]
    for b in uniq_sorted[1:]:
        if b - cur[-1] <= cluster_gap:
            cur.append(b)
        else:
            clusters.append(cur)
            cur = [b]
    clusters.append(cur)

    # pick best cluster: by size desc, then span asc
    def score(c):
        return (len(c), -(c[-1] - c[0]))  # bigger count, then tighter range
    best = max(clusters, key=score)

    bmin, bmax = best[0], best[-1]
    window = bmax - bmin
    seen_ratio = len(best) / max(1, len(set(dedup_consec)))

    ok_for_fill = (
        len(best) >= min_present_for_fill and
        (window <= coverage_window or seen_ratio >= coverage_ratio)
    )

    if ok_for_fill:
        return [b for b in range(bmin, bmax + 1) if b in images_by_block]
    else:
        return best


# ----------------------------
# NEW: post-process helper (dedup + sort desc)
# ----------------------------

def dedup_and_sort_desc(seq):
    """Remove duplicates (keep first occurrence), then sort descending."""
    return sorted(dict.fromkeys(seq), reverse=True)


# ----------------------------
# Image → single-page PDF
# ----------------------------

def image_to_pdf_page(image_path, target_width_points, target_height_points, dpi=150):
    try:
        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        if os.path.getsize(image_path) == 0:
            raise OSError(f"Image is empty (0 bytes): {image_path}")

        with Image.open(image_path) as img:
            # try to load & convert early (salvages many truncated JPEGs)
            img.load()
            if img.mode != "RGB":
                img = img.convert("RGB")

            width_inch = target_width_points / 72.0
            height_inch = target_height_points / 72.0
            target_width_px = int(width_inch * dpi)
            target_height_px = int(height_inch * dpi)

            img.thumbnail((target_width_px, target_height_px), Image.Resampling.LANCZOS)
            canvas = Image.new('RGB', (target_width_px, target_height_px), (255, 255, 255))
            offset = ((target_width_px - img.width) // 2, (target_height_px - img.height) // 2)
            canvas.paste(img, offset)

        # Save image as PDF into buffer
        pdf_buffer = io.BytesIO()
        canvas.save(pdf_buffer, format='PDF', resolution=dpi)
        pdf_buffer.seek(0)

        # Read and return the page in a way that detaches it from the buffer
        temp_reader = PdfReader(pdf_buffer)
        temp_writer = PdfWriter()
        temp_writer.add_page(temp_reader.pages[0])

        output_buffer = io.BytesIO()
        temp_writer.write(output_buffer)
        output_buffer.seek(0)

        final_reader = PdfReader(output_buffer)
        return final_reader.pages[0]

    except (OSError, FileNotFoundError, ValueError, Exception) as e:
        print(f"  ⚠️ Skipping corrupted/invalid image: {os.path.basename(image_path)}")
        print(f"    Reason: {e}")
        return None


# ----------------------------
# Pretty printer for logs
# ----------------------------

def pretty_first_n(pairs, n=10):
    return ", ".join([f"{b}:{os.path.basename(f)}" for b, f in pairs[:n]]) + \
           ("" if len(pairs) <= n else f" (+{len(pairs)-n} more)")


# ----------------------------
# Main
# ----------------------------

def main():
    input_pdf_dir = "/Users/alfredlim/Redpower/merge_pdf/input"
    image_dir = "/Users/alfredlim/Redpower/merge_pdf/images"
    output_dir = "/Users/alfredlim/Redpower/merge_pdf/output"

    os.makedirs(output_dir, exist_ok=True)

    # Get PDF files
    pdf_files = [f for f in os.listdir(input_pdf_dir) if f.lower().endswith('.pdf')]
    if not pdf_files:
        print("❌ No PDF files found in input directory!")
        return

    print(f"📁 Found {len(pdf_files)} PDF file(s) to process:\n  - " + "\n  - ".join(pdf_files) + "\n")

    # Load and group images by block
    image_files = [f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    images_by_block = {}
    skipped_files = []

    for img in image_files:
        block = extract_block_from_filename(img)
        if block is not None:
            images_by_block.setdefault(block, []).append(img)
        else:
            skipped_files.append(img)

    # Stable sort to keep human-friendly order
    for block in images_by_block:
        images_by_block[block] = sorted(images_by_block[block], key=image_sort_key)

    if skipped_files:
        print("\n⚠️ Skipped image files (no valid 3-digit block prefix):")
        for f in skipped_files:
            print(f"  - {f}")
    else:
        print("\n✅ All image files have valid block prefixes.")

    print("\n🖼️ Images grouped by block (first 8 shown each block):")
    if images_by_block:
        for block in sorted(images_by_block):
            subset = images_by_block[block][:8]
            more = "" if len(images_by_block[block]) <= 8 else f" (+{len(images_by_block[block])-8} more)"
            print(f"  Block {block:03d}: {subset}{more}")
    else:
        print("  ❌ No valid images found.")

    # Process each PDF
    for pdf_filename in pdf_files:
        print(f"\n{'='*60}")
        print(f"📄 Processing: {pdf_filename}")
        print('='*60)

        pdf_path = os.path.join(input_pdf_dir, pdf_filename)
        output_filename = os.path.splitext(pdf_filename)[0] + "_WITH_IMAGES.pdf"
        output_path = os.path.join(output_dir, output_filename)

        try:
            blocks_per_page_ocr = get_blocks_per_page_with_ocr(pdf_path)
            reader = PdfReader(pdf_path)
            writer = PdfWriter()

            for i, blocks in enumerate(blocks_per_page_ocr):
                if i >= len(reader.pages):
                    break

                # Normalize the page's block list to follow checklist-like contiguous runs
                normalized_blocks = normalize_page_blocks(blocks, images_by_block)

                # ✅ NEW: de-duplicate then sort DESC (highest block first)
                normalized_blocks = dedup_and_sort_desc(normalized_blocks)

                # Add original checklist page first
                writer.add_page(reader.pages[i])

                print(f"\n📄 Page {i+1} | OCR blocks: {blocks if blocks else '[]'}")
                print(f"   🔧 Normalized (dedup + DESC): {normalized_blocks if normalized_blocks else '[]'}")

                # Get current PDF page size
                media_box = reader.pages[i].mediabox
                page_width = float(media_box.width)
                page_height = float(media_box.height)

                insert_log = []
                for block in normalized_blocks:
                    if block in images_by_block:
                        # Insert all images for this block in stable order
                        for img_file in images_by_block[block]:
                            img_path = os.path.join(image_dir, img_file)
                            pdf_page = image_to_pdf_page(
                                img_path,
                                target_width_points=page_width,
                                target_height_points=page_height,
                                dpi=150
                            )
                            if pdf_page is not None:
                                writer.add_page(pdf_page)
                                insert_log.append((block, img_file))

                if insert_log:
                    print(f"  ➕ Inserted (first 10): {pretty_first_n(insert_log, 10)}")
                else:
                    print("  ➖ No matching images")

            # Save final PDF
            with open(output_path, "wb") as f:
                writer.write(f)
            print(f"\n✅ Success! Output: {output_filename}")

        except Exception as e:
            print(f"\n❌ Error processing {pdf_filename}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n🎉 All done! Processed {len(pdf_files)} PDF(s). Outputs in: {output_dir}")


if __name__ == "__main__":
    main()