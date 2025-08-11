import layoutparser as lp
import cv2
import fitz  # PyMuPDF
import os
import numpy as np
import requests
import re
from scipy.spatial.distance import cdist

def download_file(url, file_path):
    """Downloads a file if it doesn't exist."""
    if not os.path.exists(file_path):
        print(f"Downloading file from {url} to {file_path}...")
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print("Download complete.")

def detect_and_crop_assets(pdf_path, page_num):
    """
    Detects layout elements on a given PDF page using layoutparser,
    maps them to their semantic identifiers (e.g., "Figure 1"),
    visualizes them, and saves cropped images of figures and tables.
    """
    output_dir = "debug_output"
    os.makedirs(output_dir, exist_ok=True)

    # --- 1. Ensure Model and Config are Available Locally ---
    config_url = "https://www.dropbox.com/s/f3b12qc4hc0yh4m/config.yml?dl=1"
    weights_url = "https://www.dropbox.com/s/dgy9c10wykk4lq4/model_final.pth?dl=1"
    
    config_path = "publaynet_config.yml"
    weights_path = "publaynet_model.pth"
    
    download_file(config_url, config_path)
    download_file(weights_url, weights_path)

    # --- 2. Load the Model Using Local Paths ---
    print("Initializing LayoutParser model from local files...")
    model = lp.Detectron2LayoutModel(
        config_path=config_path,
        model_path=weights_path,
        label_map={0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"},
        extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.8]
    )
    print("Model loaded successfully.")

    # --- 3. Convert PDF page to an image and extract text ---
    print(f"Loading page {page_num} from {pdf_path}...")
    doc = fitz.open(pdf_path)
    if page_num > len(doc):
        print(f"Error: Page {page_num} is out of bounds for this {len(doc)}-page document.")
        return
        
    page = doc.load_page(page_num - 1)
    
    # Get high-resolution image for detection
    pix = page.get_pixmap(dpi=200)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    # Get text blocks with coordinates from PDF
    print("Extracting text blocks for mapping...")
    pdf_page_width = page.rect.width
    pdf_page_height = page.rect.height
    image_width = img_bgr.shape[1]
    image_height = img_bgr.shape[0]

    # Scaling factors to map PDF coordinates to image coordinates
    scale_x = image_width / pdf_page_width
    scale_y = image_height / pdf_page_height

    text_blocks = page.get_text("dict")["blocks"]
    scaled_text_blocks = []
    for block in text_blocks:
        if block['type'] == 0:  # It's a text block
            for line in block['lines']:
                # Combine spans to get a single line of text and its bbox
                line_text = "".join([span['text'] for span in line['spans']])
                x0 = min([span['bbox'][0] for span in line['spans']])
                y0 = min([span['bbox'][1] for span in line['spans']])
                x1 = max([span['bbox'][2] for span in line['spans']])
                y1 = max([span['bbox'][3] for span in line['spans']])
                
                # Scale the bbox to image coordinates
                scaled_bbox = [x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y]
                scaled_text_blocks.append({"bbox": scaled_bbox, "text": line_text.strip()})

    # --- 4. Run Detection ---
    print("Running layout detection...")
    layout = model.detect(img_bgr)
    
    # --- 5. Identify Captions and Map to Assets ---
    print("Identifying captions and mapping to assets...")
    captions = [block for block in scaled_text_blocks if re.match(r'^(Figure|Table)\s+\d+', block['text'])]
    assets = [b for b in layout if b.type in ['Figure', 'Table']]
    
    asset_mapping = {}

    if assets and captions:
        asset_centers = np.array([((b.block.x_1 + b.block.x_2) / 2, (b.block.y_1 + b.block.y_2) / 2) for b in assets])
        caption_centers = np.array([((c['bbox'][0] + c['bbox'][2]) / 2, (c['bbox'][1] + c['bbox'][3]) / 2) for c in captions])
        
        # Calculate pairwise distances between all assets and captions
        distances = cdist(asset_centers, caption_centers)
        
        # Find the closest caption for each asset
        for i, asset in enumerate(assets):
            closest_caption_idx = np.argmin(distances[i])
            asset_y2 = asset.block.y_2
            caption_y1 = captions[closest_caption_idx]['bbox'][1]
            
            # A simple heuristic: the caption must be below the asset
            if caption_y1 > asset_y2:
                # Use asset's coordinate tuple as a unique key
                asset_mapping[asset.coordinates] = captions[closest_caption_idx]['text']

    print("Asset mapping complete:")
    for key, val in asset_mapping.items():
        print(f"  - Asset at {key} mapped to '{val}'")

    # --- 6. Visualize Detections using OpenCV ---
    print("Visualizing all detected elements using OpenCV...")
    vis_image = img_bgr.copy()
    color_map = {
        "Text": (0, 255, 0), "Title": (0, 0, 255), "List": (255, 0, 0),
        "Table": (0, 255, 255), "Figure": (255, 0, 255)
    }

    for block in layout:
        x1, y1, x2, y2 = [int(c) for c in block.coordinates]
        color = color_map.get(block.type, (128, 128, 128)) # Default to gray
        cv2.rectangle(vis_image, (x1, y1), (x2, y2), color, 2)
        
        # Add a label background
        mapped_id = asset_mapping.get(block.coordinates)
        if mapped_id:
             label_text = f"{mapped_id} ({block.score:.2f})"
        else:
             label_text = f"{block.type} ({block.score:.2f})"

        (text_w, text_h), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(vis_image, (x1, y1 - text_h - 4), (x1 + text_w, y1), color, -1)
        cv2.putText(vis_image, label_text, (x1, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    vis_path = os.path.join(output_dir, f"page_{page_num}_all_detections.png")
    cv2.imwrite(vis_path, vis_image)
    print(f"Saved full visualization to {vis_path}")

    # --- 7. Crop and Save Figures/Tables ---
    print("Cropping figures and tables...")
    
    if not assets:
        print("No figures or tables were detected on this page.")
        doc.close()
        return
        
    for i, asset in enumerate(assets):
        x1, y1, x2, y2 = [int(c) for c in asset.coordinates]
        
        # Add a 5px padding
        x1 = max(0, x1 - 5)
        y1 = max(0, y1 - 5)
        x2 = min(img_bgr.shape[1], x2 + 5)
        y2 = min(img_bgr.shape[0], y2 + 5)
        
        cropped_asset = img_bgr[y1:y2, x1:x2]
        
        asset_id = asset_mapping.get(asset.coordinates)
        if asset_id:
            # Sanitize filename (e.g., "Figure 1: Title" -> "Figure_1_Title")
            safe_id = re.sub(r'[^a-zA-Z0-9_-]+', '_', asset_id)
            crop_filename = f"page_{page_num}_{safe_id}.png"
        else:
            asset_type = asset.type.lower()
            crop_filename = f"page_{page_num}_{asset_type}_{i}_unidentified.png"
            
        crop_path = os.path.join(output_dir, crop_filename)
        cv2.imwrite(crop_path, cropped_asset)
        print(f"  - Saved cropped '{asset.type}' to {crop_path}")

    doc.close()

if __name__ == "__main__":
    pdf_file = "testscripts/2507.18071v2.pdf"
    page_to_test = 5
    
    if not os.path.exists(pdf_file):
        print(f"Error: Test PDF not found at {pdf_file}")
    else:
        try:
            detect_and_crop_assets(pdf_file, page_to_test)
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            print("Please ensure layoutparser[detectron2] and its dependencies are installed correctly.") 