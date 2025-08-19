import pytest
import sys
from pathlib import Path

# Ensure project root is on sys.path for imports like `shared.arxiv`
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.arxiv import client as arxiv_client


@pytest.mark.asyncio
async def test_download_pdf_by_url_simple():
    url = "https://arxiv.org/abs/2508.11736"
    result = await arxiv_client.download_pdf_by_url(url)

    assert result.filename.endswith(".pdf")
    assert result.content_type.lower().startswith("application/pdf")
    assert isinstance(result.pdf_bytes, (bytes, bytearray))
    # Expect a non-trivial PDF size
    assert len(result.pdf_bytes) > 10_000


