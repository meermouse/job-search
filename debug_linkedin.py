"""
Quick debug script for LinkedIn profile fetching.
Usage: python debug_linkedin.py https://www.linkedin.com/in/some-profile
"""
import sys
import json
from dotenv import load_dotenv

load_dotenv()

url = sys.argv[1] if len(sys.argv) > 1 else input("Enter LinkedIn URL: ").strip()

print(f"\n--- Fetching: {url} ---")

import linkedin_parser

print("\n[1] fetch_profile ...")
try:
    profile = linkedin_parser.fetch_profile(url)
    print(f"Name      : {profile.get('firstName', '')} {profile.get('lastName', '')}")
    print(f"Headline  : {profile.get('headline', '')}")
    exp = profile.get("experience", [])
    if exp:
        print(f"Current   : {exp[0].get('title', '')} at {exp[0].get('companyName', '')}")
    skills = [s.get("name") for s in profile.get("skills", []) if s.get("name")]
    print(f"Skills    : {', '.join(skills[:8]) or 'none'}")
    print(f"Raw keys  : {list(profile.keys())}")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

print("\n[2] analyse_profile ...")
try:
    result = linkedin_parser.analyse_profile(profile)
    print(json.dumps(result, indent=2))
except Exception as e:
    print(f"FAILED: {e}")
