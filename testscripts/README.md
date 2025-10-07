# Test Script for Asset Detection

This directory contains a test script (`detectron_test.py`) for detecting and cropping figures and tables from PDF documents using Detectron2 and LayoutParser.

## Setup Instructions

These instructions are for setting up a dedicated virtual environment to run the test script.

### 1. Create and Activate a Virtual Environment

It is highly recommended to use a virtual environment to avoid conflicts with other projects. This was tested with Python 3.10.

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

Install PyTorch, Detectron2, and other required packages. The following commands include the specific flags needed for a successful installation.

```bash
# 1. Install PyTorch (CPU version)
pip install torch torchvision

# 2. Install Detectron2 with no-build-isolation to avoid errors
pip install "git+https://github.com/facebookresearch/detectron2.git" --no-build-isolation

# 3. Install other required packages
pip install layoutparser opencv-python PyMuPDF numpy requests
```

## How to Run

1.  **Place a PDF** in the `testscripts` directory. The script is currently configured to use `2507.18071v2.pdf`.
2.  **Modify the script** to point to your PDF file and the desired page number.

    ```python
    # in detectron_test.py
    if __name__ == "__main__":
        pdf_file = "testscripts/2507.18071v2.pdf"
        page_to_test = 5
        # ...
    ```

3.  **Execute the script** from the root of the project:

    ```bash
    python testscripts/detectron_test.py
    ```

4.  **Check the output**: The script will create a `debug_output` directory containing:
    *   `page_{page_num}_all_detections.png`: A visualization of all detected layout elements on the page.
    *   `page_{page_num}_{asset_type}_{i}.png`: Cropped images of the detected figures and tables.

## Hume AI TTS Test

This directory also contains a test for the Hume AI Text-to-Speech API.

See `2025.10.07-test-hume-tts/README.md` for setup instructions and usage. 