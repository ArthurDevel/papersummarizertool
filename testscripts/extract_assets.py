import fitz  # PyMuPDF
import os
import re

def find_asset_bbox_by_caption(page, asset_identifier):
    """
    Finds the bounding box of an asset (image or table) by looking for its caption.
    
    This is a heuristic. It finds the caption text and then looks for the nearest
    image or a large block of text (for a table).
    
    Args:
        page: The PyMuPDF page object.
        asset_identifier: The string to search for, e.g., "Figure 1".
        
    Returns:
        The bounding box (fitz.Rect) of the asset, or None if not found.
    """
    # Search for the asset identifier text
    text_instances = page.search_for(asset_identifier, quads=True)
    
    if not text_instances:
        # Sometimes identifiers have weird formatting, try a looser regex
        # e.g. "Figure 1:" or "Figure  1"
        words = asset_identifier.split()
        if len(words) > 1:
            pattern = r"\\s*".join(re.escape(word) for word in words)
            try:
                # Use re.IGNORECASE for robustness
                text_instances = page.search_for(pattern, quads=True, flags=re.IGNORECASE)
            except Exception:
                 # Some patterns can be invalid for PyMuPDF's regex engine
                 pass


    if not text_instances:
        return None

    # Assume the first match is the caption
    # A quad has 4 points: ul, ur, ll, lr. We create a rect from ul and lr.
    caption_quad = text_instances[0]
    # Handle cases where the quad might be irregular
    all_x = (caption_quad.ul.x, caption_quad.ur.x, caption_quad.ll.x, caption_quad.lr.x)
    all_y = (caption_quad.ul.y, caption_quad.ur.y, caption_quad.ll.y, caption_quad.lr.y)
    caption_bbox = fitz.Rect(min(all_x), min(all_y), max(all_x), max(all_y))


    # --- Heuristic to find the asset itself ---
    
    # 1. Look for images on the page
    images = page.get_images(full=True)
    closest_image_rect = None
    min_dist_to_image = float('inf')

    for img_info in images:
        img_rects = page.get_image_rects(img_info)
        for rect in img_rects:
            # Check vertical distance. Caption is usually below or above the image.
            # A good heuristic is to check if the horizontal centers are aligned
            caption_center_x = (caption_bbox.x0 + caption_bbox.x1) / 2
            rect_center_x = (rect.x0 + rect.x1) / 2
            
            if abs(caption_center_x - rect_center_x) < 100: # Aligned within 100 points
                dist = min(abs(rect.y1 - caption_bbox.y0), abs(rect.y0 - caption_bbox.y1))
                if dist < min_dist_to_image:
                    min_dist_to_image = dist
                    closest_image_rect = rect

    # 2. Look for tables on the page
    tables = page.find_tables()
    closest_table_bbox = None
    min_dist_to_table = float('inf')
    for table in tables:
        caption_center_x = (caption_bbox.x0 + caption_bbox.x1) / 2
        table_center_x = (table.bbox.x0 + table.bbox.x1) / 2
        if abs(caption_center_x - table_center_x) < 100:
            dist = min(abs(table.bbox.y1 - caption_bbox.y0), abs(table.bbox.y0 - caption_bbox.y1))
            if dist < min_dist_to_table:
                min_dist_to_table = dist
                closest_table_bbox = table.bbox

    # Decide whether it's more likely an image or table
    # Prefer the asset with the smallest vertical distance to the caption
    if min_dist_to_image < min_dist_to_table:
        if min_dist_to_image < 150: # Threshold distance in points
            return closest_image_rect
    
    if min_dist_to_table < min_dist_to_image:
        if min_dist_to_table < 150:
            return closest_table_bbox
            
    # If one is found and the other not
    if closest_image_rect and not closest_table_bbox and min_dist_to_image < 150:
        return closest_image_rect
    if closest_table_bbox and not closest_image_rect and min_dist_to_table < 150:
        return closest_table_bbox

    return None


def test_asset_extraction(pdf_path):
    """
    Test script to extract assets from a PDF by finding their captions.
    """
    output_dir = "test_output_images"
    os.makedirs(output_dir, exist_ok=True)
    
    doc = fitz.open(pdf_path)
    print(f"Opened PDF: {pdf_path}, {len(doc)} pages.")

    # Using the corrected asset locations provided by the user.
    assets_to_find = {
        5: ["Figure 1", "Figure 2"],
        6: ["Figure 3"]
    }


    print("\\n--- Finding Assets by Caption ---")
    for page_num, identifiers in assets_to_find.items():
        page_index = page_num - 1
        if page_index >= len(doc):
            print(f"Skipping page {page_num} as it is out of bounds.")
            continue
            
        page = doc.load_page(page_index)
        print(f"Processing Page {page_num}...")

        for identifier in identifiers:
            print(f"  - Searching for '{identifier}'")
            bbox = find_asset_bbox_by_caption(page, identifier)
            
            if bbox:
                print(f"    Found asset '{identifier}' at bbox: {bbox}")
                try:
                    # Add a small margin around the bounding box
                    bbox.x0 -= 5
                    bbox.y0 -= 5
                    bbox.x1 += 5
                    bbox.y1 += 5
                    pix = page.get_pixmap(clip=bbox)
                    safe_filename = identifier.replace(" ", "_").lower()
                    output_path = os.path.join(output_dir, f"page_{page_num}_{safe_filename}.png")
                    pix.save(output_path)
                    print(f"    Saved cropped asset to {output_path}")
                except Exception as e:
                    print(f"    Could not save asset: {e}")
            else:
                print(f"    Could not find asset '{identifier}' on page {page_num}.")


    doc.close()

if __name__ == "__main__":
    pdf_file = "testscripts/2507.18071v2.pdf"
    if not os.path.exists(pdf_file):
        print(f"Error: Test PDF not found at {pdf_file}")
    else:
        test_asset_extraction(pdf_file) 