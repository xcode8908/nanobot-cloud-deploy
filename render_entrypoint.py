import os
import subprocess
import json
import sys
from pathlib import Path

def main():
    print("=" * 60)
    print(" 🐈 Initializing Official HKUDS Nanobot on Render Cloud...")
    print("=" * 60)

    home_dir = Path.home() / ".nanobot"
    home_dir.mkdir(parents=True, exist_ok=True)
    config_path = home_dir / "config.json"

    # 1. Onboard / Refresh if config doesn't exist
    subprocess.run(["nanobot", "onboard", "--refresh"], check=False)

    # 2. Port for Render
    port = int(os.getenv("PORT", "10000"))

    # 3. Secret for WebUI authentication
    webui_secret = os.getenv("WEBUI_SECRET", "").strip() or "nanobot2026"

    # 4. Inject Environment Variables into config.json
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Set Gemini Provider
            gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
            if gemini_key:
                config.setdefault("providers", {}).setdefault("gemini", {})["apiKey"] = gemini_key
                config.setdefault("agents", {}).setdefault("defaults", {})["provider"] = "gemini"
                config.setdefault("agents", {}).setdefault("defaults", {})["model"] = "gemini-3-flash-preview"
                config.setdefault("agents", {}).setdefault("defaults", {})["fallbackModels"] = ["gemini-3.1-flash-lite-preview"]
                print("✓ Configured Gemini API Key & Model (gemini-3-flash-preview)")

            # Set Telegram Bot Channel if provided
            tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            if tg_token:
                tg = config.setdefault("channels", {}).setdefault("telegram", {})
                tg["enabled"] = True
                tg["token"] = tg_token
                tg["mode"] = "polling"
                tg["allowFrom"] = ["*"]
                print("✓ Enabled Telegram Channel (polling mode)")

            # Configure WebUI & WebSocket Server to bind to Render public PORT
            ws = config.setdefault("channels", {}).setdefault("websocket", {})
            ws["enabled"] = True
            ws["host"] = "0.0.0.0"
            ws["port"] = port
            ws["allowFrom"] = ["*"]
            ws["allow_from"] = ["*"]
            ws["tokenIssueSecret"] = webui_secret
            ws["token_issue_secret"] = webui_secret
            ws["websocketRequiresToken"] = True
            ws["websocket_requires_token"] = True

            # Internal Gateway Health Port on localhost
            gw = config.setdefault("gateway", {})
            gw["host"] = "127.0.0.1"
            gw["port"] = 18790

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            print(f"✓ Configured WebUI & Gateway to listen on 0.0.0.0:{port} (Secret: {webui_secret})")
        except Exception as e:
            print(f"[!] Warning updating config: {e}")

    print(f"✓ Starting Nanobot Gateway & WebUI in foreground on port {port}...")
    sys.stdout.flush()

    # Launch Nanobot Gateway in foreground
    subprocess.run([
        "nanobot", "gateway",
        "--foreground",
        "--port", "18790"
    ])

if __name__ == "__main__":
    main()
