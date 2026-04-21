#!/usr/bin/env python3
"""Seed the database with a demo tenant and sample documents."""

import asyncio
import hashlib
import secrets
import sys
from pathlib import Path

import asyncpg


DEMO_TENANT = {
    "name": "Demo NFP Organization",
    "slug": "demo-nfp",
    "api_key": f"tbm_{secrets.token_urlsafe(32)}",
    "system_prompt": (
        "You are the helpful AI assistant for Demo NFP Organization. "
        "You help visitors learn about our mission, programs, and how to get involved. "
        "Be friendly, informative, and encourage people to support our cause."
    ),
    "widget_config": {
        "primary_color": "#2563eb",
        "text_color": "#ffffff",
        "logo_url": None,
        "welcome_message": "Welcome to Demo NFP! How can I help you today?",
        "placeholder_text": "Ask us anything...",
        "position": "bottom-right",
    },
}

SAMPLE_DOCUMENTS = [
    {
        "title": "About Our Organization",
        "content": """Demo NFP Organization was founded in 2010 with a mission to provide educational
resources to underserved communities. We operate in 15 cities across the country and have helped
over 50,000 students gain access to quality learning materials.

Our core programs include:
- After-School Tutoring: Free tutoring for K-12 students in math, science, and reading
- Digital Literacy: Computer skills training for adults and seniors
- College Prep: SAT/ACT prep courses and college application assistance
- Community Library: Mobile library service bringing books to rural areas

We are funded primarily through individual donations, corporate partnerships, and government grants.
Our annual budget is approximately $5 million, with 85% going directly to program delivery.""",
    },
    {
        "title": "How to Volunteer",
        "content": """We welcome volunteers from all backgrounds! Here are the ways you can get involved:

Tutoring Volunteers:
- Commitment: 2-4 hours per week for at least 3 months
- Requirements: Background check, brief training session
- Subjects: Math, science, reading, writing, or ESL
- Sign up at our website or email volunteer@demonpf.org

Event Volunteers:
- Help at fundraising events, book drives, and community gatherings
- Flexible scheduling - sign up for individual events
- Great for groups and corporate volunteer days

Board Members:
- We are always looking for passionate community leaders
- Board members serve 2-year terms
- Meetings held monthly on the first Tuesday

To get started, fill out our volunteer application form on our website or
call us at (555) 123-4567.""",
    },
    {
        "title": "Donation Information",
        "content": """Your donations make our work possible. Here's how you can support us:

One-Time Donations:
- Online: Visit our website and click "Donate Now"
- By mail: Send checks to Demo NFP, 123 Main St, Anytown, USA 12345
- By phone: Call (555) 123-4567

Monthly Giving:
- Join our Sustainer Circle with a recurring monthly donation
- $25/month provides tutoring supplies for 5 students
- $50/month funds a mobile library visit to a rural community
- $100/month sponsors a full semester of college prep for one student

Corporate Partnerships:
- Matching gift programs
- Sponsored events and programs
- In-kind donations of technology and supplies

All donations are tax-deductible. Our EIN is 12-3456789.
We are a registered 501(c)(3) nonprofit organization.""",
    },
]


async def seed():
    database_url = None
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                database_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
                break

    if not database_url:
        print("ERROR: DATABASE_URL not found.")
        sys.exit(1)

    conn = await asyncpg.connect(database_url)
    try:
        # Check if demo tenant already exists
        existing = await conn.fetchrow("SELECT id FROM tenants WHERE slug = $1", DEMO_TENANT["slug"])
        if existing:
            print(f"Demo tenant already exists (id: {existing['id']}). Skipping.")
            return

        # Insert tenant
        import json

        tenant_id = await conn.fetchval(
            """INSERT INTO tenants (name, slug, api_key, system_prompt, widget_config)
               VALUES ($1, $2, $3, $4, $5::jsonb) RETURNING id""",
            DEMO_TENANT["name"],
            DEMO_TENANT["slug"],
            DEMO_TENANT["api_key"],
            DEMO_TENANT["system_prompt"],
            json.dumps(DEMO_TENANT["widget_config"]),
        )
        print(f"Created demo tenant: {tenant_id}")
        print(f"  API Key: {DEMO_TENANT['api_key']}")

        # Insert documents (without embeddings - those require OpenAI API)
        for doc in SAMPLE_DOCUMENTS:
            content_hash = hashlib.sha256(doc["content"].encode()).hexdigest()
            doc_id = await conn.fetchval(
                """INSERT INTO documents (tenant_id, title, content_hash, status)
                   VALUES ($1, $2, $3, 'pending') RETURNING id""",
                tenant_id,
                doc["title"],
                content_hash,
            )
            print(f"  Created document: {doc['title']} ({doc_id})")

        print("\nDemo seed complete!")
        print("Note: Documents are in 'pending' status. Use the API to re-upload them to trigger embedding generation.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
