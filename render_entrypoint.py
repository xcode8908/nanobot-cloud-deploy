import os
import subprocess
import json
import sys
from pathlib import Path

def main():
    print("=" * 60)
    print(" 🐈 Initializing Official HKUDS Nanobot for Render Deployment...")
    print("=" * 60)

    home_dir = Path.home() / ".nanobot"
    home_dir.mkdir(parents=True, exist_ok=True)
    config_path = home_dir / "config.json"

    # 1. Onboard / Refresh if config doesn't exist
    subprocess.run(["nanobot", "onboard", "--refresh"], check=False)

    # 2. Inject Environment Variables into config.json
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Set Gemini
            gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
            if gemini_key:
                config.setdefault("providers", {}).setdefault("gemini", {})["apiKey"] = gemini_key
                config.setdefault("agents", {}).setdefault("defaults", {})["provider"] = "gemini"
                config.setdefault("agents", {}).setdefault("defaults", {})["model"] = "gemini-3.5-flash"
                print("✓ Configured Gemini API Key and Model (gemini-3.5-flash)")

            # Set Telegram if provided
            tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            if tg_token:
                config.setdefault("channels", {}).setdefault("telegram", {})["enabled"] = True
                config.setdefault("channels", {}).setdefault("telegram", {})["token"] = tg_token
                config.setdefault("channels", {}).setdefault("telegram", {})["mode"] = "polling"
                print("✓ Enabled Telegram Channel with BOT_TOKEN")

            # Allow public host binding for Render
            config.setdefault("gateway", {})["host"] = "0.0.0.0"

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            print("✓ Saved config to ~/.nanobot/config.json")
        except Exception as e:
            print(f"[!] Warning updating config: {e}")

    # 3. Port for Render
    port = os.getenv("PORT", "10000")
    print(f"✓ Starting Nanobot WebUI & Gateway on port {port}...")

    # Execute WebUI on Render's assigned port
    sys.stdout.flush()
    subprocess.run([
        "nanobot", "webui",
        "--port", str(port),
        "--yes",
        "--no-open"
    ])

if __name__ == "__main__":
    main()
