import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from scraper.tiktok_scraper import _extract_pdp_via_requests, _build_requests_session

pdp_url = "https://www.tiktok.com/shop/vn/pdp/set-quan-ao-nam-nu-uma-vai-cotton-thoang-mat-thoi-trang-the-thao/1731952104423983818?chain_key=%7B%22cck%22%3A%22Cx37iAnYwVKBnq1rLRs14hQ0IQXp7hm9eMxy1FkCuhG3ukM3O3BfQpO9vNgRFjo5sEtzfIErbIeu6rJv2tEHVD6oIVkuN97vNIRQrw%3D%3D%22%2C%22mck%22%3A%22T9ingKu6%2FjdlwwxXftQCrOazCcMEKrquEK3o7l5ugQ%2FDnPT9Fe8z%2F%2FoVrBD3zrkD99PjbT0A%2B6KhUNR2BqPUu1E6CXb9mG%2FRkZEEwA%3D%3D%22%2C%22v%22%3A1%7D&source=anchor"

session = _build_requests_session([])
details = _extract_pdp_via_requests(pdp_url, session)
print("Extracted details:", details)
