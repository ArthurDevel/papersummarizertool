import sys
from pathlib import Path
import fitz  # PyMuPDF

pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("2508.13149v1.pdf")

def words_to_text(words):
    if not words:
        return ""
    words_sorted = sorted(words, key=lambda w: (w[1], w[0]))
    lines = []
    current_y = None
    line_tokens = []
    line_tol = 3.0
    for x0, y0, x1, y1, token, *_ in words_sorted:
        if current_y is None or abs(y0 - current_y) > line_tol:
            if line_tokens:
                lines.append(" ".join(line_tokens))
                line_tokens = []
            current_y = y0
        line_tokens.append(token)
    if line_tokens:
        lines.append(" ".join(line_tokens))
    return "\n".join(lines)

def split_x_for_page(page, words):
    width = page.rect.width
    num_bins = 64
    bin_w = width / num_bins
    counts = [0] * num_bins
    for x0, y0, x1, y1, token, *_ in words:
        xc = (x0 + x1) / 2.0
        idx = max(0, min(num_bins - 1, int(xc / bin_w)))
        counts[idx] += 1
    # Smooth counts with a small moving average window
    win = 5
    smoothed = []
    for i in range(num_bins):
        s = 0
        n = 0
        for j in range(i - win // 2, i + win // 2 + 1):
            if 0 <= j < num_bins:
                s += counts[j]
                n += 1
        smoothed.append(s / (n or 1))
    start_i = int(num_bins * 0.3)
    end_i = int(num_bins * 0.7)
    local = smoothed[start_i:end_i] or smoothed
    local_min = min(range(len(local)), key=lambda k: local[k])
    split_idx = (start_i + local_min) if local is smoothed[start_i:end_i] else local_min
    return (split_idx + 0.5) * bin_w

doc = fitz.open(str(pdf_path))
page_texts = []
for page in doc:
    words = page.get_text("words") or []
    if not words:
        page_texts.append("")
        continue

    sx = split_x_for_page(page, words)
    left_words = [w for w in words if ((w[0] + w[2]) / 2.0) < sx]
    right_words = [w for w in words if ((w[0] + w[2]) / 2.0) >= sx]

    # If one side is almost empty, treat as single-column
    min_side = min(len(left_words), len(right_words))
    total = len(words)
    two_col = (min_side / total) > 0.2  # both sides have meaningful content

    if two_col:
        left_text = words_to_text(left_words)
        right_text = words_to_text(right_words)
        page_texts.append("\n".join([left_text, right_text]).strip())
    else:
        page_texts.append(words_to_text(words))

markdown_text = "\n\n".join(page_texts)
md_path = pdf_path.with_suffix(".md")
md_path.write_text(markdown_text, encoding="utf-8")
print(str(md_path))


