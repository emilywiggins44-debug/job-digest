import os
import json
import base64
import logging
from datetime import datetime
from anthropic import Anthropic
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from scraper import scrape_all

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = Anthropic()

TARGET_ROLES = ["Senior Product Manager", "Principal Product Manager"]
YOUR_EMAIL = os.environ.get("YOUR_EMAIL")


def extract_jobs_from_page(url, content):
    """Send scraped content to Claude and extract matching jobs."""
    today = datetime.now().strftime("%B %d, %Y")
    prompt = f"""You are analyzing a careers page for job listings.

URL: {url}
Target roles: {', '.join(TARGET_ROLES)}
Today's date: {today}

Here is the raw text content from the page:
{content}

Your task:
1. Find ALL job listings that match or are closely related to: {', '.join(TARGET_ROLES)}
2. Only include jobs posted or updated within the last 24 hours IF a date is visible. If no dates are shown, include all matching roles.
3. For each matching job return a JSON array with this exact structure:

[
  {{
    "title": "exact job title",
    "company": "company name",
    "location": "city, state or Remote",
    "url": "direct link to job if found, otherwise use the careers page url",
    "summary": "one sentence description of the role"
  }}
]

If no matching jobs are found, return an empty array: []
Return ONLY the JSON array, no other text."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        text = response.content[0].text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        jobs = json.loads(text)
        return jobs if isinstance(jobs, list) else []
    except Exception as e:
        logger.warning(f"Failed to parse Claude response for {url}: {e}")
        return []


def build_email_html(all_jobs):
    """Build a plain text email digest."""
    today = datetime.now().strftime("%B %d, %Y")

    if not all_jobs:
        return f"🧭 Job Digest — {today}\n\nNo matching Senior PM or Principal PM roles found today.\n\n— Your Job Digest Bot"

    # Group jobs by company
    by_company = {}
    for job in all_jobs:
        company = job.get("company", "Unknown")
        if company not in by_company:
            by_company[company] = []
        by_company[company].append(job)

    lines = []
    lines.append(f"🧭 Job Digest — {today} | {len(all_jobs)} roles found")
    lines.append("=" * 50)
    lines.append("")

    for company, jobs in sorted(by_company.items()):
        lines.append(f"🏢 {company.upper()}")
        lines.append("─" * 40)
        for job in jobs:
            lines.append(f"📌 {job.get('title', '')}")
            lines.append(f"📍 {job.get('location', '')}")
            lines.append(f"📝 {job.get('summary', '')}")
            lines.append(f"🔗 {job.get('url', '')}")
            lines.append("")
        lines.append("")

    lines.append("— Your Job Digest Bot")

    return "\n".join(lines)


def send_email(html_content, job_count):
    """Send the digest email via Gmail API."""
    creds_json = os.environ.get("GMAIL_CREDENTIALS")
    creds_data = json.loads(creds_json)
    creds = Credentials(
        token=creds_data["token"],
        refresh_token=creds_data["refresh_token"],
        token_uri=creds_data["token_uri"],
        client_id=creds_data["client_id"],
        client_secret=creds_data["client_secret"],
        scopes=creds_data["scopes"]
    )

    service = build("gmail", "v1", credentials=creds)

    today = datetime.now().strftime("%B %d, %Y")
    subject = f"Job Digest: {job_count} new PM roles - {today}"

    email_lines = [
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        f"To: {YOUR_EMAIL}",
        f"From: {YOUR_EMAIL}",
        f"Subject: {subject}",
        "",
        html_content
    ]
    raw_email = "\n".join(email_lines)
    encoded = base64.urlsafe_b64encode(raw_email.encode()).decode()

    service.users().messages().send(
        userId="me",
        body={"raw": encoded}
    ).execute()

    logger.info(f"Email sent successfully with {job_count} jobs")


def main():
    logger.info("Starting job digest run...")

    # Step 1: Scrape all sites
    scraped_pages = scrape_all()

    # Step 2: Extract matching jobs from each page
    all_jobs = []
    for page in scraped_pages:
        logger.info(f"Extracting jobs from {page['url']}")
        jobs = extract_jobs_from_page(page["url"], page["content"])
        if jobs:
            logger.info(f"  Found {len(jobs)} matching jobs")
            all_jobs.extend(jobs)

    logger.info(f"Total matching jobs found: {len(all_jobs)}")

    # Step 3: Build the email
    html_content = build_email_html(all_jobs)

    # Step 4: Send it
    send_email(html_content, len(all_jobs))


if __name__ == "__main__":
    main()
