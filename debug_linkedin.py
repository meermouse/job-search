"""
Quick debug script for LinkedIn profile analysis.
Usage: python debug_linkedin.py

Paste your LinkedIn profile text when prompted, then press Ctrl+D (or Ctrl+Z on Windows).
"""
import sys
import json
from dotenv import load_dotenv

load_dotenv()

print("Paste your LinkedIn profile text below, then press Ctrl+Z + Enter (Windows) or Ctrl+D (Mac/Linux):")
text = sys.stdin.read().strip()

if not text:
    print("No text provided.")
    sys.exit(1)

print(f"\n--- Analysing ({len(text)} chars) ---")

import linkedin_parser

try:
    result = linkedin_parser.analyse_profile(text)
    print(json.dumps(result, indent=2))
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)
