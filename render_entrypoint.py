import os
import subprocess
import json
import sys
import threading
import time
import signal
from pathlib import Path

# Paths
HOME = Path.home() / ".nanobot"
WORKSPACE = HOME / "workspace"
CONFIG_PATH = HOME / "config.json"

GH_TOKEN = os.getenv("GH_TOKEN", "").strip()
GH_REPO = os.getenv("GH_MEMORY_REPO", "xcode8908/nanobot-private-memory").strip()

def setup_private_memory():
    """Restore private memory & personality from GitHub on boot."""
    if not GH_TOKEN:
        print("[!] No GH_TOKEN provided. Running with container-local memory only.")
        return

    repo_url = f"https://x-access-token:{GH_TOKEN}@github.com/{GH_REPO}.git"
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    git_dir = WORKSPACE / ".git"

    if not git_dir.exists():
        print(f"📥 Restoring private memory from {GH_REPO}...")
        try:
            subprocess.run(["git", "init"], cwd=WORKSPACE, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "bot@nanobot.local"], cwd=WORKSPACE, check=True)
            subprocess.run(["git", "config", "user.name", "Nanobot Cloud"], cwd=WORKSPACE, check=True)
            subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=WORKSPACE, check=True)
            res = subprocess.run(["git", "fetch", "origin", "main"], cwd=WORKSPACE, capture_output=True, text=True)
            if res.returncode == 0:
                subprocess.run(["git", "checkout", "-f", "-B", "main", "origin/main"], cwd=WORKSPACE, check=True, capture_output=True)
                print("✓ Successfully restored private memory & soul from GitHub!")
                # Restore SQLite sessions if backed up
                sessions_backup = WORKSPACE / "sessions_backup"
                if sessions_backup.exists():
                    import shutil
                    shutil.copytree(sessions_backup, HOME / "sessions", dirs_exist_ok=True)
                    print("✓ Restored previous SQLite chat sessions from GitHub!")
            else:
                print("✓ Initialized new memory branch.")
        except Exception as e:
            print(f"[!] Warning restoring private memory: {e}")

def push_memory(reason="Auto-save"):
    """Commit & push all modified memory/workspace/sessions files to the private repo."""
    if not GH_TOKEN:
        return
    git_dir = WORKSPACE / ".git"
    if not git_dir.exists():
        return
    try:
        # Copy active SQLite chat sessions into workspace backup before commit
        sessions_src = HOME / "sessions"
        sessions_dst = WORKSPACE / "sessions_backup"
        if sessions_src.exists():
            import shutil
            shutil.copytree(sessions_src, sessions_dst, dirs_exist_ok=True)

        status = subprocess.run(["git", "status", "--porcelain"], cwd=WORKSPACE, capture_output=True, text=True)
        if status.stdout.strip():
            subprocess.run(["git", "add", "-A"], cwd=WORKSPACE, check=True, capture_output=True)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            subprocess.run(["git", "commit", "-m", f"{reason} [{timestamp}]"], cwd=WORKSPACE, check=True, capture_output=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=WORKSPACE, check=True, capture_output=True)
            print(f"✓ [{timestamp}] Complete workspace & chat sessions auto-saved to GitHub (0ms user lag).")
    except Exception as e:
        print(f"[!] Auto-save error: {e}")

def background_sync_worker(interval_seconds=180):
    """Background daemon: periodically syncs memory without slowing down chats."""
    if not GH_TOKEN:
        return
    print(f"🛡️ Private Auto-Sync Active: Backing up memory every {interval_seconds}s in background...")
    while True:
        try:
            time.sleep(interval_seconds)
            push_memory("Periodic sync")
        except Exception as e:
            print(f"[!] Background sync loop warning: {e}")

def main():
    print("=" * 60)
    print(" 🐈 Initializing Official HKUDS Nanobot on Render Cloud...")
    print("=" * 60)

    # 1. Restore private memory from GitHub before boot
    setup_private_memory()

    # 2. Run onboard --refresh to populate missing templates
    subprocess.run(["nanobot", "onboard", "--refresh"], check=False)

    # 3. Read Render assigned PORT & secrets
    port = int(os.getenv("PORT", "10000"))
    webui_secret = os.getenv("WEBUI_SECRET", "").strip() or "nanobot2026"

    # 4. Inject Environment Variables into config.json
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Set Gemini Provider with active gemini-3-flash-preview model
            gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
            if gemini_key:
                config.setdefault("providers", {}).setdefault("gemini", {})["apiKey"] = gemini_key
                config.setdefault("agents", {}).setdefault("defaults", {})["provider"] = "gemini"
                config.setdefault("agents", {}).setdefault("defaults", {})["model"] = "gemini-3-flash-preview"
                config.setdefault("agents", {}).setdefault("defaults", {})["fallbackModels"] = []
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

            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            print(f"✓ Configured WebUI & Gateway to listen on 0.0.0.0:{port} (Secret: {webui_secret})")
        except Exception as e:
            print(f"[!] Warning updating config: {e}")

    # 5. Push initial files if needed
    push_memory("Initial boot sync")

    # 6. Start non-blocking background sync thread (0ms latency for user)
    if GH_TOKEN:
        sync_thread = threading.Thread(target=background_sync_worker, args=(180,), daemon=True)
        sync_thread.start()

    # 7. Graceful shutdown handler
    def handle_shutdown(signum, frame):
        print("\n🛑 Shutdown signal received! Saving private memory before exit...")
        push_memory("Graceful shutdown save")
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

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
