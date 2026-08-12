"""Read-only HeyGen catalog lookup — lists avatars and voices available to
your HeyGen account so you can pick IDs for Avatar Library by hand.

This tool makes NO video-generation calls and writes nothing anywhere — it
only calls HeyGen's "List Avatars" and "List Voices" endpoints and prints
the results. It exists purely to save you from hunting through the HeyGen
dashboard UI for Avatar ID / Voice ID values.

Usage:
    python tools/heygen_lookup.py avatars
    python tools/heygen_lookup.py voices
    python tools/heygen_lookup.py avatars --search fitness
    python tools/heygen_lookup.py voices --search male
"""

import argparse
import os
import sys

import requests
from dotenv import load_dotenv

AVATARS_URL = "https://api.heygen.com/v2/avatars"
VOICES_URL = "https://api.heygen.com/v2/voices"


def get_api_key():
    load_dotenv()
    key = os.environ.get("HEYGEN_API_KEY")
    if not key:
        sys.exit("HEYGEN_API_KEY is not set in .env")
    return key


def _get(url, api_key):
    resp = requests.get(url, headers={"X-Api-Key": api_key, "Accept": "application/json"}, timeout=30)
    if resp.status_code == 401:
        sys.exit(
            "HeyGen API returned 401 Unauthorized — check that HEYGEN_API_KEY in .env "
            "is a valid key from HeyGen Dashboard > Settings > API Keys."
        )
    resp.raise_for_status()
    return resp.json()


def list_avatars(api_key, search=None):
    data = _get(AVATARS_URL, api_key)
    avatars = data.get("data", {}).get("avatars", []) or data.get("data", [])
    if search:
        s = search.lower()
        avatars = [a for a in avatars if s in (a.get("avatar_name") or "").lower()]
    return avatars


def list_voices(api_key, search=None):
    data = _get(VOICES_URL, api_key)
    voices = data.get("data", {}).get("voices", []) or data.get("data", [])
    if search:
        s = search.lower()
        voices = [
            v for v in voices
            if s in (v.get("name") or "").lower() or s in (v.get("language") or "").lower()
            or s in (v.get("gender") or "").lower()
        ]
    return voices


def _cli():
    parser = argparse.ArgumentParser(description="Read-only HeyGen avatar/voice catalog lookup")
    sub = parser.add_subparsers(dest="command", required=True)

    avatars_p = sub.add_parser("avatars", help="List available avatars")
    avatars_p.add_argument("--search", help="Filter by avatar name substring (case-insensitive)")

    voices_p = sub.add_parser("voices", help="List available voices")
    voices_p.add_argument("--search", help="Filter by voice name/language/gender substring")

    args = parser.parse_args()
    api_key = get_api_key()

    if args.command == "avatars":
        avatars = list_avatars(api_key, args.search)
        print(f"{len(avatars)} avatar(s):\n")
        for a in avatars:
            print(f"  Avatar ID:   {a.get('avatar_id')}")
            print(f"  Avatar Name: {a.get('avatar_name')}")
            print(f"  Gender:      {a.get('gender', '')}")
            print(f"  Premium:     {a.get('premium', '')}")
            print()
    elif args.command == "voices":
        voices = list_voices(api_key, args.search)
        print(f"{len(voices)} voice(s):\n")
        for v in voices:
            print(f"  Voice ID:   {v.get('voice_id')}")
            print(f"  Voice Name: {v.get('name')}")
            print(f"  Language:   {v.get('language', '')}")
            print(f"  Gender:     {v.get('gender', '')}")
            print()


if __name__ == "__main__":
    _cli()
