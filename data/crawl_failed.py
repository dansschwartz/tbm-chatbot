import subprocess, json, os, re, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

FAILED_URLS = [
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

def crawl_url(url):
    slug = url.rstrip("/").split("/")[-1] or "home"
    slug = re.sub(r'[^a-zA-Z0-9_-]', '_', slug)
    out_path = OUT_DIR / f"{slug}.md"
    
    try:
        result = subprocess.run(
            ["gsk", "crawl", url, "--render_js"],
            capture_output=True, text=True, timeout=45
        )
        output = result.stdout
        try:
            lines = output.split("\n")
            json_str = ""
            for i, line in enumerate(lines):
                if line.strip().startswith("{"):
                    json_str = "\n".join(lines[i:])
                    break
            if not json_str:
                json_str = output
            data = json.loads(json_str)
            content = data.get("data", {}).get("result", "")
        except:
            content = ""
        
        if content and "No content found" not in content and len(content) > 50:
            md = f"---\nsource: {url}\npage: {slug}\n---\n\n{content}\n"
            out_path.write_text(md)
            print(f"✅ {slug} ({len(content)} chars)")
            return slug, True
        else:
            print(f"⚠️  {slug} - still empty")
            return slug, False
    except Exception as e:
        print(f"❌ {slug} - {e}")
        return slug, False

success = 0
failed = 0
failed_slugs = []
with ThreadPoolExecutor(max_workers=3) as pool:
    futures = {pool.submit(crawl_url, url): url for url in FAILED_URLS}
    for f in as_completed(futures):
        slug, ok = f.result()
        if ok:
            success += 1
        else:
            failed += 1
            failed_slugs.append(slug)

print(f"\nDone: {success} recovered, {failed} still failing")
if failed_slugs:
    print(f"Still failing: {', '.join(failed_slugs)}")
