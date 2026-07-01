#!/usr/bin/env python3
"""Test Xiaomi MiMo Platform API connection."""

import os
import sys

# Add the agents directory to the path
sys.path.insert(0, r"D:\Projects\HordeForge")

from agents.llm_api import create_mimo_api

# Get token from environment variable
token = os.getenv("MIMO_ACCESS_TOKEN")

if __name__ == "__main__":
    if not token:
        print("ERROR: MIMO_ACCESS_TOKEN environment variable not set")
        print("")
        print("To get an API key:")
        print("1. Go to https://platform.xiaomimimo.com")
        print("2. Create an account or login")
        print("3. Navigate to API Keys section")
        print("4. Generate a new API key")
        print("")
        print("Then set the environment variable:")
        print("  set MIMO_ACCESS_TOKEN=your_api_key_here")
        sys.exit(1)

    print(f"Token loaded: {token[:20]}...")
    print("Base URL: https://api.xiaomimimo.com/v1")
    print("Model: mimo-v2.5-pro")
    print("-" * 50)

    try:
        api = create_mimo_api(api_key=token, model="mimo-v2.5-pro")
        print("MiMo API instance created successfully!")
        print(f"Provider: {api.config.provider}")
        print(f"Model: {api.config.model}")
        print(f"Base URL: {api.config.base_url}")
    except Exception as e:
        print(f"ERROR creating API: {type(e).__name__}: {e}")
        sys.exit(1)

    print("-" * 50)
    print("MiMo Platform API configured to use:")
    print("  - Endpoint: https://api.xiaomimimo.com/v1")
    print("  - Models: mimo-v2.5-pro, mimo-v2.5, mimo-v2.5-pro-ultraspeed")
    print("")
    print("Reference: https://platform.xiaomimimo.com")
