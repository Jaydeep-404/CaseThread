from __future__ import annotations
import re, time, json, csv
import os
import requests, trafilatura
from newspaper import Article
from readability import Document
from bs4 import BeautifulSoup
from pymongo import UpdateOne
from datetime import datetime, timezone
from data_processing.data_parsing import error_logger


os.makedirs("case_docs", exist_ok=True)

try:
    # from playwright.sync_api import sync_playwright
    from playwright.async_api import async_playwright
    PLAYWRIGHT = True
except ImportError:
    PLAYWRIGHT = False                 # JS fallback not installed

HEADERS = {
    "User-Agent": "MyResearchBot/1.1 (contact: you@example.com)",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close",
}

DATE_RE = re.compile(r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2})\b")

async def polite_get(url: str, *, timeout: int = 30) -> str:
    """Fetch page HTML, using Playwright if JS is mandatory."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 403 and PLAYWRIGHT:
            return await fetch_with_js(url, timeout)
        r.raise_for_status()
        return r.text
    except requests.RequestException as e:
        if PLAYWRIGHT:                 # try JS as last resort
            return await fetch_with_js(url, timeout)
        raise e

async def fetch_with_js(url: str, timeout: int) -> str:
    try:
        async with async_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=timeout*1000)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        raise Exception(f"Failed to fetch {url} with JS: {e}")
    
    
async def extract_with_cascade(html: str, url: str) -> dict:
    """Return dict with title, text, author, date."""
    # 1 ── Trafilatura
    try:
        result = trafilatura.extract(html, include_comments=False, favor_recall=True,
                                    url=url, output_format="json")
        if result:
            data = json.loads(result)
            return {
                "title": data.get("title") or "Untitled",
                "author": "; ".join(data.get("authors") or []) or "N/A",
                "date": data.get("date") or "N/A",
                "content": data.get("text") or "",
            }

        # 2 ── newspaper3k
        art = Article(url)
        art.set_html(html); art.parse()
        if art.text:
            return {
                "title": art.title or "Untitled",
                "author": "; ".join(art.authors) or "N/A",
                "date": art.publish_date.isoformat() if art.publish_date else "N/A",
                "content": art.text,
            }

        # 3 ── readability-lxml
        doc = Document(html)
        title = doc.short_title()
        soup = BeautifulSoup(doc.summary(html_partial=True), "html.parser")
        paragraphs = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
        if paragraphs:
            return {"title": title, "author": "N/A", "date": "N/A", "content": paragraphs}

        # 4 ── bare-bones fallback
        soup = BeautifulSoup(html, "html.parser")
        text = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
        title = (soup.title.get_text(strip=True) if soup.title else "Untitled")
        return {"title": title, "author": "N/A", "date": "N/A", "content": text}
    except Exception as e:
        print(f"Error in extract_with_cascade: {e}")
        return {"title": "", "author": "N/A", "date": "N/A", "content": ""}
    
    
async def sniff_metadata(html: str, extracted: dict) -> dict:
    """Fill in author/date if still N/A."""
    try:
        soup = BeautifulSoup(html, "html.parser")

        # DATE: <time>, meta, bold tag, regex sniff
        if extracted["date"] == "N/A":
            t = soup.find("time", attrs={"datetime": True})
            if t: extracted["date"] = t["datetime"]
            else:
                meta = soup.find("meta", attrs={"property": "article:published_time"}) \
                    or soup.find("meta", attrs={"name": "pubdate"})
                if meta and meta.get("content"):
                    extracted["date"] = meta["content"]
                else:
                    bold = soup.find("b", string=DATE_RE)
                    if bold:
                        extracted["date"] = bold.get_text(strip=True)

        # AUTHOR: meta or class contains 'author'
        if extracted["author"] == "N/A":
            meta = soup.find("meta", attrs={"name": "author"})
            if meta and meta.get("content"):
                extracted["author"] = meta["content"]
            else:
                tag = soup.find(attrs={"class": re.compile(r"author", re.I)})
                if tag:
                    extracted["author"] = tag.get_text(" ", strip=True)
        return extracted
    except Exception as e:
        print(f"Error sniffing metadata: {e}")
        return {}
    

async def scrape_any(url: str, csv_path: str | None = "corpus.csv",
               throttle: float = .3) -> dict:
    try:
        html = await polite_get(url)
        data = await extract_with_cascade(html, url)
        data = await sniff_metadata(html, data)
        data["url"] = url

        if csv_path:
            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=data.keys())
                if f.tell() == 0: w.writeheader()
                w.writerow(data)

        time.sleep(throttle)
        return data
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return {}


# Main scraper
async def scrape_content(db, limit: int = 10):
    try:
        cursor = db.documents.find(
            {"is_data_scraped":{"$ne": True}, "document_type": "link", "status": 'pending'},
            {"document_url": 1, "_id": 1}
            ).sort("created_at", 1).limit(limit)
        
        doc_to_update = []
        
        data = await cursor.to_list(length=limit)
        
        if not data:
            print("No documents to scrape.")
            return {"status": False, "message": "No pending documents to scrape."}
        
        for doc in data:
            try:
                doc_id = doc.get('_id')
                scraped_data = await scrape_any(doc.get("document_url"))
                content = scraped_data.get('content')
                file_path = f"./case_docs/doc_{doc_id}.md"
                
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                    
                doc_to_update.append(UpdateOne({"_id": doc_id},
                            {"$set": {"is_md_file": True, "md_file_path": file_path, "is_data_scraped": True, "updated_at": datetime.now(timezone.utc)}}))
            except Exception as e:
                print("scrape_content loop err")
                await error_logger(db, doc["_id"], e)
                
        await db.documents.bulk_write(doc_to_update)
        
        return {"status": True, "message": "Data scraped"}
    except Exception as e:
        print('scrape_content err', e)
        return {"status": False, "message": "Somthing went wrong"}





   