#!/usr/bin/env python3
"""
Upload the complete DCSC Knowledge Base to the chatbot.
Updates the system prompt with Part 1 instructions, then uploads Part 2 as documents.

Usage:
    python3 scripts/upload_kb.py --api-url https://tbm-chatbot-production.up.railway.app --admin-key YOUR_ADMIN_KEY
"""

import argparse
import json
import re
import sys
import time

import httpx

def main():
    parser = argparse.ArgumentParser(description="Upload DCSC Knowledge Base")
    parser.add_argument("--api-url", required=True, help="Base API URL")
    parser.add_argument("--admin-key", required=True, help="Admin API key")
    parser.add_argument("--kb-file", default="docs/DCSC_Complete_Knowledge_Base.md", help="Knowledge base file")
    parser.add_argument("--tenant-slug", default="dcsc", help="Tenant slug")
    args = parser.parse_args()

    headers = {"X-Admin-Key": args.admin_key, "Content-Type": "application/json"}
    client = httpx.Client(base_url=args.api_url, headers=headers, timeout=120)

    # Read KB file
    print(f"📖 Reading {args.kb_file}...")
    with open(args.kb_file) as f:
        kb_text = f.read()

    # Split into Part 1 and Part 2
    part1_match = re.search(r'# Part 1 — Chatbot Instructions\n(.*?)(?=# Part 2)', kb_text, re.DOTALL)
    part2_match = re.search(r'# Part 2 — Knowledge Base\n(.*?)(?=\*End of Knowledge Base\*|$)', kb_text, re.DOTALL)

    if not part1_match:
        print("❌ Could not find Part 1 in KB file")
        sys.exit(1)

    part1 = part1_match.group(1).strip()
    part2 = part2_match.group(1).strip() if part2_match else ""

    print(f"  Part 1 (instructions): {len(part1)} chars")
    print(f"  Part 2 (knowledge):    {len(part2)} chars")

    # Get tenant
    print(f"\n🔍 Finding tenant '{args.tenant_slug}'...")
    resp = client.get("/api/tenants")
    resp.raise_for_status()
    tenants = resp.json()
    tenant = next((t for t in tenants if t["slug"] == args.tenant_slug), None)
    if not tenant:
        print(f"❌ Tenant '{args.tenant_slug}' not found")
        sys.exit(1)
    tenant_id = tenant["id"]
    print(f"  Found: {tenant['name']} ({tenant_id})")

    # Update system prompt with Part 1
    print(f"\n📝 Updating system prompt with Part 1 instructions...")
    resp = client.patch(f"/api/tenants/{tenant_id}", json={
        "system_prompt": part1
    })
    resp.raise_for_status()
    print(f"  ✅ System prompt updated ({len(part1)} chars)")

    # Delete existing documents
    print(f"\n🗑️  Deleting existing documents...")
    resp = client.get(f"/api/tenants/{tenant_id}/documents")
    resp.raise_for_status()
    existing_docs = resp.json()
    for doc in existing_docs:
        client.delete(f"/api/tenants/{tenant_id}/documents/{doc['id']}")
    print(f"  Deleted {len(existing_docs)} documents")

    # Split Part 2 into sections for upload
    print(f"\n📤 Uploading knowledge base sections...")
    sections = re.split(r'\n## (\d+\.\d+ .+)\n', part2)

    documents = []
    i = 1
    while i < len(sections) - 1:
        title = sections[i].strip()
        content = sections[i + 1].strip()
        i += 2

        if len(content) < 50:
            continue

        # Extract source URL if present
        source_match = re.search(r'\[Source: DCSC website — (https?://[^\]]+)\]', content)
        source_url = source_match.group(1) if source_match else f"https://www.dcsoccerclub.org"

        documents.append({
            "title": title,
            "content": content,
            "source_url": source_url
        })

    # If we got very few sections (content wasn't split well), upload as one big doc
    if len(documents) < 5:
        print("  Uploading as subsections instead...")
        # Split by ### headers
        subsections = re.split(r'\n### (.+)\n', part2)
        documents = []
        i = 1
        while i < len(subsections) - 1:
            title = subsections[i].strip()
            content = subsections[i + 1].strip()
            i += 2
            if len(content) < 100:
                continue
            source_match = re.search(r'\[Source: DCSC website — (https?://[^\]]+)\]', content)
            source_url = source_match.group(1) if source_match else "https://www.dcsoccerclub.org"
            documents.append({
                "title": title,
                "content": content,
                "source_url": source_url
            })

    print(f"  Prepared {len(documents)} documents for upload")

    # Bulk upload with rate limit handling
    batch_size = 5
    total_uploaded = 0
    total_failed = 0

    for batch_start in range(0, len(documents), batch_size):
        batch = documents[batch_start:batch_start + batch_size]
        print(f"  Uploading batch {batch_start // batch_size + 1} ({len(batch)} docs)...")

        try:
            resp = client.post(
                f"/api/tenants/{tenant_id}/documents/bulk",
                json={"documents": batch},
                timeout=300
            )
            resp.raise_for_status()
            result = resp.json()
            total_uploaded += result.get("succeeded", 0)
            total_failed += result.get("failed", 0)
            print(f"    ✅ {result.get('succeeded', 0)} succeeded, {result.get('failed', 0)} failed")
        except Exception as e:
            print(f"    ❌ Error: {e}")
            total_failed += len(batch)

        # Small delay between batches to avoid rate limits
        if batch_start + batch_size < len(documents):
            print("    Waiting 5s to avoid rate limits...")
            time.sleep(5)

    print(f"\n{'='*50}")
    print(f"✅ Done!")
    print(f"  System prompt: Updated with Part 1 instructions")
    print(f"  Documents uploaded: {total_uploaded}")
    print(f"  Documents failed: {total_failed}")
    print(f"  Total KB size: {len(kb_text)} chars")
    print(f"\n🧪 Test it: {args.api_url}/demo")


if __name__ == "__main__":
    main()
