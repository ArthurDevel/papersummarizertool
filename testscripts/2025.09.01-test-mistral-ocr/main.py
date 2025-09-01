import os
import re
import base64
from dotenv import load_dotenv
from mistralai import Mistral

# --------- Constants (easy to change) ---------
MODEL = "mistral-ocr-latest"
DOCUMENT_TYPE = "document_url"
DOCUMENT_URL = "https://arxiv.org/pdf/2508.13149"
INCLUDE_IMAGE_BASE64 = True
OUTPUT_MD_NAME = "output.md"
IMAGES_SUBDIR = "images"
# ---------------------------------------------


load_dotenv()
api_key = os.environ["MISTRAL_API_KEY"]
client = Mistral(api_key=api_key)


def get_image_data_and_ext(data_str):
    """Return (base64_data, ext) using the official SDK image field format.
    - If a data URL, parse mime to get extension.
    - Otherwise, treat as base64 and default to 'jpeg'.
    """
    if not data_str or not isinstance(data_str, str):
        return None, None
    if data_str.startswith("data:"):
        header, b64_data = data_str.split(",", 1)
        mime = header.split(";")[0]  # e.g. data:image/jpeg
        ext = mime.split("/")[-1] if "/" in mime else "jpeg"
        return b64_data, ext
    return data_str, "jpeg"


def get_image_field(image_obj):
    """Return the base64 image data strictly from 'image_base64'.
    Works for both SDK objects and dicts.
    """
    val = getattr(image_obj, "image_base64", None)
    if val:
        return val
    if isinstance(image_obj, dict):
        return image_obj.get("image_base64")
    return None


def get_image_name(image_obj):
    """Return the filename provided by the SDK ('name'), e.g., 'img-0.jpeg'."""
    val = getattr(image_obj, "name", None)
    if not val and isinstance(image_obj, dict):
        val = image_obj.get("name")
    return os.path.basename(val.strip()) if isinstance(val, str) and val.strip() else None


# 1) Run OCR
ocr_response = client.ocr.process(
    model=MODEL,
    document={"type": DOCUMENT_TYPE, "document_url": DOCUMENT_URL},
    include_image_base64=INCLUDE_IMAGE_BASE64,
)


# 2) Prepare output paths
script_dir = os.path.dirname(os.path.abspath(__file__))
images_dir = os.path.join(script_dir, IMAGES_SUBDIR)
os.makedirs(images_dir, exist_ok=True)
md_path = os.path.join(script_dir, OUTPUT_MD_NAME)


# 3) Save markdown and images
with open(md_path, "w", encoding="utf-8") as md:
    for page in ocr_response.pages:
        page_markdown = getattr(page, "markdown", "") or ""
        images = getattr(page, "images", []) or []

        # Save images and remember any provided names so we can rewrite links
        name_map = {}  # original_name -> images/original_name
        saved_paths_in_order = []  # images/pageX-imageY.ext in order of appearance
        for idx, img in enumerate(images, start=1):
            data_str = get_image_field(img)
            b64_data, ext = get_image_data_and_ext(data_str)
            if not b64_data:
                continue

            suggested = get_image_name(img)
            if suggested and "." not in suggested:
                suggested = f"{suggested}.{ext}"
            filename = suggested or f"page{page.index}-image{idx}.{ext}"

            with open(os.path.join(images_dir, filename), "wb") as f:
                f.write(base64.b64decode(b64_data))

            if suggested:
                name_map[suggested] = f"{IMAGES_SUBDIR}/{filename}"
            saved_paths_in_order.append(f"{IMAGES_SUBDIR}/{filename}")

        # Rewrite markdown links using provided names first
        for original_name, saved_rel in name_map.items():
            page_markdown = page_markdown.replace(f"]({original_name})", f"]({saved_rel})")
            page_markdown = page_markdown.replace(f"](./{original_name})", f"]({saved_rel})")

        # Fallback: sequentially rewrite any remaining (img-*.ext) links to saved images
        img_link_pattern = re.compile(r"(\!\[[^\]]*\]\()\s*(?:\./)?(img-\d+\.[A-Za-z0-9]+)\s*(\))")

        replace_index = {"i": 0}

        def _seq_replacer(match):
            i = replace_index["i"]
            if i < len(saved_paths_in_order):
                repl = f"{match.group(1)}{saved_paths_in_order[i]}{match.group(3)}"
                replace_index["i"] += 1
                return repl
            return match.group(0)

        page_markdown = img_link_pattern.sub(_seq_replacer, page_markdown)

        md.write(f"## Page {page.index}\n\n")
        md.write(page_markdown + "\n\n")

        if images:
            md.write("### Images\n\n")
            for idx, img in enumerate(images, start=1):
                suggested = get_image_name(img)
                if suggested and suggested in name_map:
                    rel = name_map[suggested]
                else:
                    data_str = get_image_field(img)
                    _, ext = get_image_data_and_ext(data_str)
                    rel = f"{IMAGES_SUBDIR}/page{page.index}-image{idx}.{ext}"
                md.write(f"![page {page.index} image {idx}]({rel})\n\n")
