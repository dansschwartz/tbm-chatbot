"""
Clean and restructure raw crawled data for RAG ingestion.
Removes junk, normalizes whitespace, adds metadata, and categorizes content.
"""
import os
import re
from pathlib import Path

RAW_DIR = Path(__file__).parent / "raw"
CLEAN_DIR = Path(__file__).parent / "clean"
CLEAN_DIR.mkdir(exist_ok=True)

# Files to skip entirely (empty, nav-only, or duplicate content)
SKIP_FILES = {
    "club-resources.md",     # Nav page with Squarespace template text only
    "es-co.md",              # Spanish homepage - just nav labels
    "news.md",               # Headlines only, articles are in separate pages
    "travel-tryout-schedule.md",  # Nav page, content in level-specific pages
}

# Category mapping for better RAG retrieval
CATEGORIES = {
    "About-Us": "about",
    "board-of-directors": "about",
    "staff": "about",
    "DC-Soccer-Club-FAQs": "faq",
    "GA-ASPIRE-FAQs": "faq",
    "mls-next-academy-faqs": "faq",
    "travel-program-and-tryout-faqs": "faq",
    "tots": "programs-recreational",
    "pre-k": "programs-recreational",
    "rec-league": "programs-recreational",
    "rec-rules-and-age-groups": "programs-recreational",
    "recreational-programs": "programs-recreational",
    "winter-futsal": "programs-recreational",
    "pre-travel-academy": "programs-competitive",
    "travel-program": "programs-competitive",
    "travel-program-information": "programs-competitive",
    "travel-coaching-slate": "programs-competitive",
    "travel-tryouts": "programs-competitive",
    "travel-level-tryout-schedule": "tryouts",
    "select-level-tryout-schedule": "tryouts",
    "academy-level-id-sessions-schedule": "tryouts",
    "age-group-change": "tryouts",
    "dc-soccer-club-accepted-into-mls-next-academy-division-beginning-20262027-season": "news-announcements",
    "soccer-camps": "camps-clinics",
    "summer-camps": "camps-clinics",
    "holiday-camps": "camps-clinics",
    "elite-camps": "camps-clinics",
    "clinics": "camps-clinics",
    "ball-mastery-clinic": "camps-clinics",
    "rec-skills-clinic": "camps-clinics",
    "rec-goalkeeper-clinic": "camps-clinics",
    "adult-clinic": "camps-clinics",
    "school-programming": "camps-clinics",
    "financial-aid": "registration-fees",
    "spring-registration": "registration-fees",
    "summer-registration": "registration-fees",
    "playmetrics-help": "registration-fees",
    "club-policies": "policies-safety",
    "safety-resources": "policies-safety",
    "contact-your-agc": "contacts",
    "Referee-for-DCSC": "contacts",
    "new-to-the-club": "getting-started",
    "soccer-parent-education": "parent-resources",
    "Futbol-Fiesta": "events",
    "Len-Oliver-5v5-Tournament": "events",
    "the-district-cup-tournament": "events",
    "world-cup-3v3-tournament": "events",
    "rec-all-star-cup": "events",
    "tournaments-and-events": "events",
    "topsoccer-program": "programs-inclusive",
}

def clean_content(text):
    """Remove artifacts, normalize whitespace, clean up Squarespace junk."""
    # Remove Squarespace slide placeholders
    text = re.sub(r'\s*Slide title\s*\n\s*Write your caption here\s*', '', text)
    
    # Remove standalone "Button" lines
    text = re.sub(r'^\s*Button\s*$', '', text, flags=re.MULTILINE)
    
    # Remove "List Item N" artifacts  
    text = re.sub(r'\s*List Item\s+\d+\s*', '', text)
    
    # Remove "For this project, the challenge was..." Squarespace placeholder
    text = re.sub(r'For this project, the challenge was in rebranding.*?outstanding\.\s*', '', text)
    
    # Collapse excessive whitespace (3+ blank lines -> 2)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove lines that are just whitespace
    text = re.sub(r'^\s+$', '', text, flags=re.MULTILINE)
    
    # Collapse multiple spaces
    text = re.sub(r' {3,}', ' ', text)
    
    # Remove leading/trailing whitespace per line
    lines = [line.rstrip() for line in text.split('\n')]
    text = '\n'.join(lines)
    
    # Collapse again after line cleanup
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

def process_file(filepath):
    """Read, clean, and restructure a single file."""
    with open(filepath) as f:
        content = f.read()
    
    # Extract frontmatter
    match = re.match(r'^---\n(.*?)\n---\n\n?(.*)', content, re.DOTALL)
    if match:
        frontmatter_text = match.group(1)
        body = match.group(2)
    else:
        frontmatter_text = ""
        body = content
    
    # Parse existing frontmatter
    source = ""
    page = filepath.stem
    for line in frontmatter_text.split('\n'):
        if line.startswith('source:'):
            source = line.split(':', 1)[1].strip()
        elif line.startswith('page:'):
            page = line.split(':', 1)[1].strip()
    
    # Clean the body
    body = clean_content(body)
    
    # Skip if body is too short after cleaning
    if len(body) < 100:
        print(f"  SKIP (too short after cleaning): {filepath.name}")
        return None
    
    # Determine category
    category = CATEGORIES.get(filepath.stem, "general")
    
    # Build clean frontmatter
    clean_fm = f"""---
source: {source}
page: {page}
category: {category}
---"""
    
    return f"{clean_fm}\n\n{body}\n"

# Process all files
processed = 0
skipped = 0

for filepath in sorted(RAW_DIR.glob("*.md")):
    if filepath.name in SKIP_FILES:
        print(f"  REMOVE: {filepath.name} (junk/duplicate)")
        skipped += 1
        continue
    
    result = process_file(filepath)
    if result:
        out_path = CLEAN_DIR / filepath.name
        with open(out_path, 'w') as f:
            f.write(result)
        processed += 1
        print(f"  ✅ {filepath.name}")
    else:
        skipped += 1

print(f"\nDone: {processed} files cleaned, {skipped} skipped")
