"""
Quick Crawl4AI comparison test against FTMO and ForexFactory.
"""
import asyncio
import sys

# Use synchronous interface for crawl4ai
from crawl4ai import AsyncWebCrawler
from crawl4ai import BrowserConfig, CrawlerRunConfig, CacheMode

async def crawl_and_report(url, label):
    print(f"\n{'='*60}")
    print(f"Crawl4AI: {label}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
    
    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url, config=config)
            print(f"Success: {result.success}")
            print(f"Status: {result.status_code}")
            
            if result.success:
                print(f"Content length: {len(result.html)} bytes")
                
                # Extract headings
                import re
                h2s = re.findall(r'<h2[^>]*>(.*?)</h2>', result.html, re.IGNORECASE)
                print(f"H2 headings: {[h.strip()[:60] for h in h2s[:10]]}")
                
                text = result.markdown or result.fit_markdown or ""
                print(f"Markdown length: {len(text)}")
                print(f"\nFirst 1500 chars:\n{text[:1500]}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(crawl_and_report('https://ftmo.com/en/trading-objectives/', 'FTMO Trading Objectives'))
    print("\n" + "="*60)
    asyncio.run(crawl_and_report('https://www.forexfactory.com/calendar', 'ForexFactory Calendar'))
