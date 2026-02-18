import requests
from bs4 import BeautifulSoup
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Sites that require JavaScript rendering (Playwright)
JS_REQUIRED_SITES = [
    "apple.com",
    "amazon.jobs",
    "tiktok.com",
    "metacareers.com",
    "careers.google.com",
    "snap.com",
    "uber.com",
    "careers.tubi.tv",
]

def needs_javascript(url):
    return any(domain in url for domain in JS_REQUIRED_SITES)

def scrape_with_requests(url):
    """Scrape a static page using requests + BeautifulSoup."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Remove noise: scripts, styles, nav, footer
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Trim to avoid massive token usage
        return text[:8000]
    except Exception as e:
        logger.warning(f"requests failed for {url}: {e}")
        return None

def scrape_with_playwright(url):
    """Scrape a JS-rendered page using Playwright."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers(HEADERS)
            page.goto(url, timeout=20000, wait_until="networkidle")
            content = page.content()
            browser.close()

        soup = BeautifulSoup(content, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:8000]
    except Exception as e:
        logger.warning(f"Playwright failed for {url}: {e}")
        return None

def scrape_all(url_file="job_sites.txt"):
    """Read URLs from file and scrape each one. Returns list of dicts."""
    results = []

    with open(url_file, "r") as f:
        urls = [
            line.strip()
            for line in f
            if line.strip() and not line.startswith("#")
        ]

    logger.info(f"Scraping {len(urls)} sites...")

    for url in urls:
        logger.info(f"Scraping: {url}")
        if needs_javascript(url):
            content = scrape_with_playwright(url)
        else:
            content = scrape_with_requests(url)

        if content:
            results.append({"url": url, "content": content})
        else:
            logger.warning(f"No content retrieved for {url}")

        # Be polite — don't hammer servers
        time.sleep(2)

    logger.info(f"Successfully scraped {len(results)} of {len(urls)} sites")
    return results

if __name__ == "__main__":
    results = scrape_all()
    for r in results:
        print(f"\n--- {r['url']} ---\n{r['content'][:300]}\n")
