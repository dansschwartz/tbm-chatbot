import subprocess, json, os, re, time, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

URLS = [
    "https://www.dcsoccerclub.org/About-Us",
    "https://www.dcsoccerclub.org/DC-Soccer-Club-FAQs",
    "https://www.dcsoccerclub.org/Futbol-Fiesta",
    "https://www.dcsoccerclub.org/GA-ASPIRE-FAQs",
    "https://www.dcsoccerclub.org/Len-Oliver-5v5-Tournament",
    "https://www.dcsoccerclub.org/Referee-for-DCSC",
    "https://www.dcsoccerclub.org/academy-level-id-sessions-schedule",
    "https://www.dcsoccerclub.org/adult-clinic",
    "https://www.dcsoccerclub.org/age-group-change",
    "https://www.dcsoccerclub.org/ball-mastery-clinic",
    "https://www.dcsoccerclub.org/board-of-directors",
    "https://www.dcsoccerclub.org/clinics",
    "https://www.dcsoccerclub.org/club-policies",
    "https://www.dcsoccerclub.org/club-resources",
    "https://www.dcsoccerclub.org/contact-your-agc",
    "https://www.dcsoccerclub.org/dc-soccer-club-accepted-into-mls-next-academy-division-beginning-20262027-season",
    "https://www.dcsoccerclub.org/elite-camps",
    "https://www.dcsoccerclub.org/es-co",
    "https://www.dcsoccerclub.org/financial-aid",
    "https://www.dcsoccerclub.org/holiday-camps",
    "https://www.dcsoccerclub.org/mls-next-academy-faqs",
    "https://www.dcsoccerclub.org/new-to-the-club",
    "https://www.dcsoccerclub.org/news",
    "https://www.dcsoccerclub.org/playmetrics-help",
    "https://www.dcsoccerclub.org/pre-k",
    "https://www.dcsoccerclub.org/pre-travel-academy",
    "https://www.dcsoccerclub.org/rec-all-star-cup",
    "https://www.dcsoccerclub.org/rec-goalkeeper-clinic",
    "https://www.dcsoccerclub.org/rec-league",
    "https://www.dcsoccerclub.org/rec-rules-and-age-groups",
    "https://www.dcsoccerclub.org/rec-skills-clinic",
    "https://www.dcsoccerclub.org/recreational-programs",
    "https://www.dcsoccerclub.org/safety-resources",
    "https://www.dcsoccerclub.org/school-programming",
    "https://www.dcsoccerclub.org/select-level-tryout-schedule",
    "https://www.dcsoccerclub.org/soccer-camps",
    "https://www.dcsoccerclub.org/soccer-parent-education",
    "https://www.dcsoccerclub.org/spring-registration",
    "https://www.dcsoccerclub.org/staff",
    "https://www.dcsoccerclub.org/summer-camps",
    "https://www.dcsoccerclub.org/summer-registration",
    "https://www.dcsoccerclub.org/the-district-cup-tournament",
    "https://www.dcsoccerclub.org/topsoccer-program",
    "https://www.dcsoccerclub.org/tots",
    "https://www.dcsoccerclub.org/tournaments-and-events",
    "https://www.dcsoccerclub.org/travel-coaching-slate",
    "https://www.dcsoccerclub.org/travel-level-tryout-schedule",
    "https://www.dcsoccerclub.org/travel-program",
    "https://www.dcsoccerclub.org/travel-program-and-tryout-faqs",
    "https://www.dcsoccerclub.org/travel-program-information",
    "https://www.dcsoccerclub.org/travel-tryout-schedule",
    "https://www.dcsoccerclub.org/travel-tryouts",
    "https://www.dcsoccerclub.org/winter-futsal",
    "https://www.dcsoccerclub.org/world-cup-3v3-tournament",
]

OUT_DIR = Path(__file__).parent / "raw"
OUT_DIR.mkdir(exist_ok=True)

def crawl_url(url):
    slug = url.rstrip("/").split("/")[-1] or "home"
    slug = re.sub(r'[^a-zA-Z0-9_-]', '_', slug)
    out_path = OUT_DIR / f"{slug}.md"
    
    try:
        result = subprocess.run(
            ["gsk", "crawl", url],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout
        # Extract the result text from JSON
        try:
            data = json.loads(output.split("\n", 1)[-1] if "[INFO]" in output else output)
            content = data.get("data", {}).get("result", "")
        except:
            # Try to find JSON in output
            for line in output.split("\n"):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        data = json.loads(line)
                        content = data.get("data", {}).get("result", "")
                        break
                    except:
                        continue
            else:
                content = ""
        
        if content and "No content found" not in content and len(content) > 50:
            # Add metadata header
            md = f"---\nsource: {url}\npage: {slug}\n---\n\n{content}\n"
            out_path.write_text(md)
            print(f"✅ {slug} ({len(content)} chars)")
            return slug, True
        else:
            print(f"⚠️  {slug} - empty or failed")
            return slug, False
    except Exception as e:
        print(f"❌ {slug} - {e}")
        return slug, False

# Crawl with limited concurrency to avoid rate limits
success = 0
failed = 0
with ThreadPoolExecutor(max_workers=4) as pool:
    futures = {pool.submit(crawl_url, url): url for url in URLS}
    for f in as_completed(futures):
        slug, ok = f.result()
        if ok:
            success += 1
        else:
            failed += 1

print(f"\nDone: {success} pages crawled, {failed} failed")
