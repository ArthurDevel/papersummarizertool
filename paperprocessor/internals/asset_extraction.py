import logging
import re
from typing import List, Dict, Any
import io
import os
from pathlib import Path

import cv2
import fitz  # PyMuPDF
import layoutparser as lp
import numpy as np
import requests
from PIL import Image
from scipy.spatial.distance import cdist

class AssetExtractor:
    """
    Handles the detection, mapping, and extraction of visual assets (figures and tables)
    from PDF documents.
    """

    def __init__(self):
        """
        Initializes the AssetExtractor by loading the layout detection model.
        """
        self.model = self._load_model()

    def _load_model(self) -> lp.Detectron2LayoutModel:
        """
        Loads the pre-downloaded Detectron2 layout model from the /models directory
        inside the Docker container.
        """
        # These paths are fixed as they are set in the Dockerfile
        config_path = "/models/publaynet_config.yml"
        weights_path = "/models/publaynet_model.pth"

        if not os.path.exists(config_path) or not os.path.exists(weights_path):
            logging.error("Model files not found in /models directory. Please ensure they are downloaded during the Docker build.")
            raise FileNotFoundError("Model files not found.")

        logging.info("Initializing LayoutParser model from local files...")
        model = lp.Detectron2LayoutModel(
            config_path=config_path,
            model_path=weights_path,
            label_map={0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"},
            extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.8]
        )
        logging.info("LayoutParser model loaded successfully.")
        return model

    def _map_assets_on_page(
        self, page: fitz.Page, layout: lp.Layout, image: np.ndarray
    ) -> Dict[tuple, str]:
        """
        Maps detected visual assets to their textual captions on a single page.
        """
        # Scale PDF coordinates to image coordinates
        scale_x = image.shape[1] / page.rect.width
        scale_y = image.shape[0] / page.rect.height

        text_blocks = page.get_text("dict")["blocks"]
        scaled_text_blocks = []
        for block in text_blocks:
            if block['type'] == 0:  # Text block
                for line in block['lines']:
                    line_text = "".join([span['text'] for span in line['spans']])
                    if line_text.strip():
                        x0 = min(span['bbox'][0] for span in line['spans']) * scale_x
                        y0 = min(span['bbox'][1] for span in line['spans']) * scale_y
                        x1 = max(span['bbox'][2] for span in line['spans']) * scale_x
                        y1 = max(span['bbox'][3] for span in line['spans']) * scale_y
                        scaled_text_blocks.append({"bbox": [x0, y0, x1, y1], "text": line_text.strip()})
        
        captions = [b for b in scaled_text_blocks if re.match(r'^(Figure|Table)\s+\d+', b['text'])]
        assets = [b for b in layout if b.type in ['Figure', 'Table']]
        
        asset_mapping = {}
        if not assets or not captions:
            return asset_mapping

        asset_centers = np.array([((b.block.x_1 + b.block.x_2) / 2, (b.block.y_1 + b.block.y_2) / 2) for b in assets])
        caption_centers = np.array([((c['bbox'][0] + c['bbox'][2]) / 2, (c['bbox'][1] + c['bbox'][3]) / 2) for c in captions])

        distances = cdist(asset_centers, caption_centers)

        for i, asset in enumerate(assets):
            # Find the closest caption that is located *below* the asset
            potential_matches = []
            for j, caption in enumerate(captions):
                asset_y2 = asset.block.y_2
                caption_y1 = caption['bbox'][1]
                if caption_y1 > asset_y2:
                    potential_matches.append((distances[i, j], j))
            
            if potential_matches:
                _, closest_caption_idx = min(potential_matches, key=lambda x: x[0])
                asset_mapping[asset.coordinates] = captions[closest_caption_idx]['text']
        
        return asset_mapping

    def extract_assets(self, pdf_contents: bytes) -> List[Dict[str, Any]]:
        """
        Processes a PDF document from bytes, extracts all figures and tables,
        and returns a structured list of these assets.
        """
        logging.info("Starting asset extraction from PDF.")
        all_assets = []
        doc = fitz.open(stream=pdf_contents, filetype="pdf")

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            
            # 1. Convert page to image for layout detection
            pix = page.get_pixmap(dpi=200)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            # 2. Run layout detection
            layout = self.model.detect(img_bgr)
            
            # 3. Map detected assets to their captions
            asset_mapping = self._map_assets_on_page(page, layout, img_bgr)

            if not asset_mapping:
                continue

            logging.info(f"Found {len(asset_mapping)} assets on page {page_num + 1}")

            # 4. Crop, encode, and store asset information
            for asset_block in [b for b in layout if b.coordinates in asset_mapping]:
                x1, y1, x2, y2 = [int(c) for c in asset_block.coordinates]
                
                # Add padding
                x1, y1 = max(0, x1 - 5), max(0, y1 - 5)
                x2, y2 = min(img_bgr.shape[1], x2 + 5), min(img_bgr.shape[0], y2 + 5)
                
                cropped_asset_img = img_bgr[y1:y2, x1:x2]
                
                # Encode image to bytes
                _, buffer = cv2.imencode('.png', cropped_asset_img)
                img_bytes = buffer.tobytes()

                # Log cropped asset image details
                try:
                    crop_h, crop_w = cropped_asset_img.shape[:2]
                    logging.info(
                        f"Cropped asset on page {page_num + 1} bbox=({x1},{y1},{x2},{y2}) size={crop_w}x{crop_h} px, bytes={len(img_bytes)} (PNG)"
                    )
                except Exception as e:
                    logging.warning(f"Could not log cropped asset details on page {page_num + 1}: {e}")

                asset_id = asset_mapping[asset_block.coordinates]
                asset_type = "Table" if "Table" in asset_id else "Figure"

                all_assets.append({
                    "identifier": asset_id,
                    "type": asset_type,
                    "page": page_num + 1,
                    "image_bytes": img_bytes,
                    "bounding_box": [x1, y1, x2, y2],
                    # Dimensions of the image coordinate space for bounding_box
                    # (width, height) corresponding to the pixmap at dpi=200
                    "source_image_size": [int(img_bgr.shape[1]), int(img_bgr.shape[0])]
                })

        doc.close()
        logging.info(f"Asset extraction complete. Found {len(all_assets)} total assets.")
        return all_assets 