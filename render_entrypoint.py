import os
# Memory management for 512MB RAM environment (Zero-Crash Architecture)
os.environ["MALLOC_ARENA_MAX"] = "1"
os.environ["PYTHONMALLOC"] = "malloc"
os.environ["MALLOC_TRIM_THRESHOLD_"] = "65536"
# Extended timeouts for deep reasoning & large code generation
os.environ["NANOBOT_STREAM_IDLE_TIMEOUT_S"] = "180"
os.environ["NANOBOT_OPENAI_COMPAT_TIMEOUT_S"] = "180"
import gc
import ctypes
import subprocess
import json
import sys
import threading
import time
import signal
from pathlib import Path

_libc = None
try:
    _libc = ctypes.CDLL("libc.so.6")
except Exception:
    pass

def trim_memory():
    """Aggressively flush Python GC & return all freed pages to Linux OS."""
    try:
        gc.collect(2)
        if _libc and hasattr(_libc, "malloc_trim"):
            _libc.malloc_trim(0)
    except Exception:
        pass

def get_process_rss_mb():
    """Read actual resident set size (RSS) memory in MB from Linux /proc."""
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except Exception:
        pass
    return 0.0

def memory_guard_worker(interval=15, soft_limit_mb=300, hard_limit_mb=380):
    """24/7 Background Sentinel: Keeps container RAM strictly below 400MB."""
    print("🛡️ [MemoryGuard] Active: Monitoring RAM with 380MB hard ceiling (512MB safe envelope)...")
    while True:
        try:
            time.sleep(interval)
            rss = get_process_rss_mb()
            if rss > soft_limit_mb:
                trim_memory()
                rss_after = get_process_rss_mb()
                if rss_after > hard_limit_mb:
                    import re
                    re.purge()
                    trim_memory()
                    final_rss = get_process_rss_mb()
                    print(f"🛡️ [MemoryGuard] Flushed RAM: {rss:.1f}MB -> {final_rss:.1f}MB (Available: {512 - final_rss:.1f}MB)")
        except Exception:
            pass

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
                import shutil
                # 1. Restore config_backup.json if previously saved (contains custom channels, WhatsApp, custom APIs)
                cfg_backup = WORKSPACE / "config_backup.json"
                if cfg_backup.exists():
                    shutil.copy2(cfg_backup, CONFIG_PATH)
                    print("✓ Restored custom channels & API configurations from GitHub!")
                # 2. Restore SQLite sessions if backed up
                sessions_backup = WORKSPACE / "sessions_backup"
                if sessions_backup.exists():
                    shutil.copytree(sessions_backup, HOME / "sessions", dirs_exist_ok=True)
                    print("✓ Restored previous SQLite chat sessions from GitHub!")
                # 3. Restore custom skills if backed up
                skills_backup = WORKSPACE / "skills_backup"
                if skills_backup.exists():
                    shutil.copytree(skills_backup, HOME / "skills", dirs_exist_ok=True)
                    print("✓ Restored custom skills from GitHub!")
                # 4. Restore Cron automations, CLI Apps, WhatsApp / channel auth if backed up
                for auth_dir in ["cron", "cli-apps", "whatsapp", "auth", "channels"]:
                    src = WORKSPACE / f"{auth_dir}_backup"
                    if src.exists():
                        shutil.copytree(src, HOME / auth_dir, dirs_exist_ok=True)
                        print(f"✓ Restored {auth_dir} state from GitHub!")
            else:
                print("✓ Initialized new memory branch.")
        except Exception as e:
            print(f"[!] Warning restoring private memory: {e}")

def restore_installed_apps():
    """Auto-reinstall any CLI apps that were installed previously if the container reset."""
    try:
        import shutil
        from nanobot.apps.cli import CliAppManager
        manager = CliAppManager(workspace=WORKSPACE)
        installed = manager._load_installed()
        for name, data in installed.items():
            entry_point = str(data.get("entry_point") or "")
            if entry_point and not shutil.which(entry_point):
                print(f"📦 Container reset detected! Auto-reinstalling app: {name}...")
                try:
                    manager.install(name)
                    print(f"✓ Successfully restored app: {name}")
                except Exception as err:
                    print(f"[!] Note on restoring app {name}: {err}")
    except Exception as e:
        print(f"[!] App auto-restore check notice: {e}")

def install_system_tools():
    """Install standalone portable Linux binaries for gh and tmux so Skills are 100% Ready."""
    bin_dir = Path.home() / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PATH"] = f"{bin_dir}:{os.environ.get('PATH', '')}"

    # 1. Install GitHub CLI (gh)
    gh_bin = bin_dir / "gh"
    if not gh_bin.exists():
        try:
            print("📦 Installing standalone GitHub CLI (gh)...")
            import urllib.request, tarfile, io
            url = "https://github.com/cli/cli/releases/download/v2.67.0/gh_2.67.0_linux_amd64.tar.gz"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                with tarfile.open(fileobj=io.BytesIO(resp.read()), mode="r:gz") as tar:
                    for member in tar.getmembers():
                        if member.name.endswith("/bin/gh"):
                            f = tar.extractfile(member)
                            if f:
                                with open(gh_bin, "wb") as out:
                                    out.write(f.read())
                                gh_bin.chmod(0o755)
                                print("✓ GitHub CLI (gh) ready!")
                                break
        except Exception as e:
            print(f"[!] Warning installing gh: {e}")

    # 2. Install tmux
    tmux_bin = bin_dir / "tmux"
    if not tmux_bin.exists():
        try:
            print("📦 Installing standalone tmux binary...")
            import urllib.request
            url = "https://github.com/pythops/tmux-linux-binary/releases/download/v3.5a/tmux-linux-x86_64"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                with open(tmux_bin, "wb") as out:
                    out.write(resp.read())
                tmux_bin.chmod(0o755)
                print("✓ tmux binary ready!")
        except Exception as e:
            print(f"[!] Warning installing tmux: {e}")

def push_memory(reason="Auto-save"):
    """Commit & push all modified memory/workspace/sessions files to the private repo."""
    if not GH_TOKEN:
        return
    git_dir = WORKSPACE / ".git"
    if not git_dir.exists():
        return
    try:
        import shutil
        # 1. Backup full config.json (preserves any custom channels, WhatsApp, custom APIs, model presets)
        if CONFIG_PATH.exists():
            shutil.copy2(CONFIG_PATH, WORKSPACE / "config_backup.json")

        # 2. Backup active SQLite chat sessions into workspace backup before commit
        sessions_src = HOME / "sessions"
        sessions_dst = WORKSPACE / "sessions_backup"
        if sessions_src.exists():
            shutil.copytree(sessions_src, sessions_dst, dirs_exist_ok=True)

        # 3. Backup custom skills if installed
        skills_src = HOME / "skills"
        if skills_src.exists():
            shutil.copytree(skills_src, WORKSPACE / "skills_backup", dirs_exist_ok=True)

        # 4. Backup Cron automations, CLI Apps, WhatsApp / channel auth credentials if created
        for auth_dir in ["cron", "cli-apps", "whatsapp", "auth", "channels"]:
            src = HOME / auth_dir
            if src.exists():
                shutil.copytree(src, WORKSPACE / f"{auth_dir}_backup", dirs_exist_ok=True)

        status = subprocess.run(["git", "status", "--porcelain"], cwd=WORKSPACE, capture_output=True, text=True)
        if status.stdout.strip():
            subprocess.run(["git", "add", "-A"], cwd=WORKSPACE, check=True, capture_output=True)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            subprocess.run(["git", "commit", "-m", f"{reason} [{timestamp}]"], cwd=WORKSPACE, check=True, capture_output=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=WORKSPACE, check=True, capture_output=True)
            print(f"✓ [{timestamp}] Complete workspace & chat sessions auto-saved to GitHub (0ms user lag).")
        trim_memory()
    except Exception as e:
        print(f"[!] Auto-save error: {e}")

def background_sync_worker(interval_seconds=900):
    """Background daemon: periodically syncs memory every 15 mins without commit bloat or slowing down chats."""
    if not GH_TOKEN:
        return
    print(f"🛡️ Private Smart-Sync Active: Backing up memory every {interval_seconds // 60} minutes in background...")
    while True:
        try:
            time.sleep(interval_seconds)
            push_memory("Periodic sync (15m)")
            trim_memory()
        except Exception as e:
            print(f"[!] Background sync loop warning: {e}")

def patch_nanobot_head_health():
    """Support HTTP HEAD requests and /health endpoints for UptimeRobot & keep-alive monitors."""
    try:
        import nanobot.channels.websocket.runtime as ws_runtime
        file_path = ws_runtime.__file__
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        target = "async def handle_binary(request: web.BaseRequest) -> web.StreamResponse:\n            try:\n                with self.bus.admission.activity():"
        replacement = """async def handle_binary(request: web.BaseRequest) -> web.StreamResponse:
            try:
                if request.method == "HEAD" or request.path in ["/health", "/ping"]:
                    return web.Response(status=200, text="OK")
                with self.bus.admission.activity():"""
        if target in content and 'request.method == "HEAD"' not in content:
            content = content.replace(target, replacement, 1)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print("✓ Patched Nanobot WebSocket listener to support HTTP HEAD & /health for UptimeRobot.")
    except Exception as e:
        print(f"[!] Warning patching HEAD health support: {e}")

def patch_nanobot_commands():
    """Make /new, /reset, /clear instant priority commands, prevent self-cancellation, and reply immediately."""
    try:
        # 1. Patch CommandRouter so /new, /reset, /clear (with or without arguments) are matched as priority
        import nanobot.command.router as router_mod
        router_file = router_mod.__file__
        with open(router_file, "r", encoding="utf-8") as f:
            r_content = f.read()

        target_prio = "def is_priority(self, text: str) -> bool:\n        return normalize_command_text(text).lower() in self._priority"
        repl_prio = """def is_priority(self, text: str) -> bool:
        cmd = normalize_command_text(text).split(maxsplit=1)[0].lower()
        return cmd in self._priority"""

        target_disp = "        ctx.raw = normalize_command_text(ctx.raw)\n        handler = self._priority.get(ctx.raw.lower())"
        repl_disp = """        ctx.raw = normalize_command_text(ctx.raw)
        cmd = ctx.raw.split(maxsplit=1)[0].lower()
        handler = self._priority.get(cmd)"""

        if target_prio in r_content:
            r_content = r_content.replace(target_prio, repl_prio, 1)
        if target_disp in r_content:
            r_content = r_content.replace(target_disp, repl_disp, 1)

        with open(router_file, "w", encoding="utf-8") as f:
            f.write(r_content)

        # 2. Patch builtin.py: Register /new, /reset, /clear as priority & customize friendly response
        import nanobot.command.builtin as cmd_builtin
        cmd_file = cmd_builtin.__file__
        with open(cmd_file, "r", encoding="utf-8") as f:
            b_content = f.read()

        target_msg = 'content="New session started."'
        repl_msg = 'content="✨ Naya session start ho gaya hai! Purani chat clear ho gayi hai. Ab aap jo chahein pooch sakte hain!"'
        if target_msg in b_content:
            b_content = b_content.replace(target_msg, repl_msg, 1)

        target_reg = '    router.exact("/new", cmd_new)'
        repl_reg = """    router.priority("/new", cmd_new)
    router.priority("/reset", cmd_new)
    router.priority("/clear", cmd_new)
    router.exact("/new", cmd_new)"""
        if target_reg in b_content:
            b_content = b_content.replace(target_reg, repl_reg, 1)

        with open(cmd_file, "w", encoding="utf-8") as f:
            f.write(b_content)

        # 3. Patch loop.py so _cancel_active_tasks excludes current task (prevents self-cancellation)
        import nanobot.agent.loop as loop_mod
        loop_file = loop_mod.__file__
        with open(loop_file, "r", encoding="utf-8") as f:
            l_content = f.read()

        target_cancel = "tasks = tuple(self._active_tasks.pop(key, set()))"
        repl_cancel = """current_t = asyncio.current_task()
        tasks = tuple(t for t in self._active_tasks.pop(key, set()) if t is not current_t)"""
        if target_cancel in l_content:
            l_content = l_content.replace(target_cancel, repl_cancel, 1)

        target_outbound = "await self.bus.publish_outbound(result)"
        repl_outbound = """await self.bus.publish_outbound(result)
        try:
            import gc, ctypes
            gc.collect(1)
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass"""
        if target_outbound in l_content:
            l_content = l_content.replace(target_outbound, repl_outbound, 1)

        with open(loop_file, "w", encoding="utf-8") as f:
            f.write(l_content)

        # 4. Patch base.py: Strict privacy - robust ID matching & explicit Access Denied message
        import nanobot.channels.base as ch_base
        base_file = ch_base.__file__
        with open(base_file, "r", encoding="utf-8") as f:
            c_content = f.read()

        target_match = "# allowFrom entries are opaque tokens — must match exactly.\n        if str(sender_id) in allow_list:\n            return True"
        repl_match = """# allowFrom entries: check exact match or split token (id|username)
        tokens = set(str(sender_id).split("|")) | {str(sender_id)}
        if any(t in allow_list for t in tokens):
            return True"""

        target_dm = "content=format_pairing_reply(code),"
        repl_dm = 'content="⛔ Access Denied: Yeh bot private hai. Sirf owner (@Infinity_0wner) hi ise access kar sakta hai.",'

        if target_match in c_content:
            c_content = c_content.replace(target_match, repl_match, 1)
        if target_dm in c_content:
            c_content = c_content.replace(target_dm, repl_dm, 1)

        with open(base_file, "w", encoding="utf-8") as f:
            f.write(c_content)

        print("✓ Patched Nanobot security on disk: Private Admin Mode & /new priority active.")
    except Exception as e:
        print(f"[!] Warning patching commands: {e}")

def patch_antigravity_sliding_window():
    """Antigravity-Grade Sliding Window & Token Trimmer to eliminate 10-turn timeouts forever."""
    try:
        import nanobot.agent.loop as loop_mod
        file_path = loop_mod.__file__
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        target = "    def _build_transcript_input(self, ctx: TurnContext) -> TranscriptInput:\n        assert ctx.session is not None\n        return TranscriptInput(\n            history=ctx.history,"
        
        replacement = """    def _build_transcript_input(self, ctx: TurnContext) -> TranscriptInput:
        assert ctx.session is not None
        # Antigravity Sliding Window Optimizer: keep only last 8 turns & trim huge tool outputs
        h_slice = ctx.history[-8:] if ctx.history and len(ctx.history) > 8 else (ctx.history or [])
        clean_history = []
        for item in h_slice:
            if isinstance(item, dict):
                c = item.get("content")
                if isinstance(c, str) and len(c) > 3000 and item.get("role") in ("tool", "system"):
                    item = dict(item)
                    item["content"] = c[:3000] + "\\n... [Old output trimmed to preserve token bandwidth]"
            clean_history.append(item)
        return TranscriptInput(
            history=clean_history,"""

        if target in content and "Antigravity Sliding Window Optimizer" not in content:
            content = content.replace(target, replacement, 1)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print("✓ Injected Antigravity Sliding Window Optimizer (Max 8 turns & tool trimmer)")
    except Exception as e:
        print(f"[!] Warning patching sliding window: {e}")

def main():
    print("=" * 60)
    print(" 🐈 Initializing Official HKUDS Nanobot on Render Cloud...")
    print("=" * 60)

    # 1. Restore private memory from GitHub before boot
    setup_private_memory()

    # 1.1 Install standalone gh & tmux binaries
    install_system_tools()

    # 2. Run onboard --refresh to populate missing templates
    subprocess.run(["nanobot", "onboard", "--refresh"], check=False)

    # 2.1 Auto-reinstall any apps if container was reset
    restore_installed_apps()

    # 2.2 Patch Nanobot to support HTTP HEAD and /health for UptimeRobot
    patch_nanobot_head_health()

    # 2.3 Patch Nanobot to support /new with arguments, /reset, and /clear
    patch_nanobot_commands()

    # 2.4 Patch Nanobot with Antigravity Sliding Window (Max 8 turns & Tool Trimmer)
    patch_antigravity_sliding_window()

    # 3. Read Render assigned PORT & secrets
    port = int(os.getenv("PORT", "10000"))
    webui_secret = os.getenv("WEBUI_SECRET", "").strip() or "nanobot2026"

    # 4. Inject Environment Variables into config.json
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Set Gemini Provider with active key
            gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
            if gemini_key:
                config.setdefault("providers", {}).setdefault("gemini", {})["apiKey"] = gemini_key
                print("✓ Configured Gemini API Key")

            # Set Groq Provider with active key
            groq_key = os.getenv("GROQ_API_KEY", "").strip()
            if groq_key:
                config.setdefault("providers", {}).setdefault("groq", {})["apiKey"] = groq_key
                print("✓ Configured Groq High-Speed API Key")

            # Set OpenRouter Provider if provided
            openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
            if openrouter_key:
                config.setdefault("providers", {}).setdefault("openrouter", {})["apiKey"] = openrouter_key
                print("✓ Configured OpenRouter API Key")

            # Set Custom / FreeLLMAPI / TokenHarbor Provider
            custom_key = os.getenv("CUSTOM_API_KEY", "").strip() or os.getenv("FREELLM_API_KEY", "").strip() or os.getenv("TOKENHARBOR_API_KEY", "").strip()
            custom_base = os.getenv("CUSTOM_API_BASE", "").strip() or "https://freellm.silentxop.workers.dev/v1"
            if custom_key:
                cust = config.setdefault("providers", {}).setdefault("custom", {})
                cust["apiKey"] = custom_key
                cust["apiBase"] = custom_base
                print(f"✓ Configured FreeLLMAPI / Custom Provider ({custom_base})")

            # Setup High-Power Resilient Model Presets (1M Context, FreeLLMAPI Gemini Engine)
            presets = config.setdefault("modelPresets", {})
            presets["freellmapi-gemini"] = {
                "model": "gemini-3.5-flash-lite",
                "provider": "custom",
                "maxTokens": 8192,
                "contextWindowTokens": 1000000,
                "temperature": 0.1,
                "extraHeaders": None, "extraQuery": None, "extraBody": None, "reasoningEffort": None, "api": None
            }
            presets["freellmapi-flash-lite"] = {
                "model": "gemini-flash-lite",
                "provider": "custom",
                "maxTokens": 8192,
                "contextWindowTokens": 1000000,
                "temperature": 0.1,
                "extraHeaders": None, "extraQuery": None, "extraBody": None, "reasoningEffort": None, "api": None
            }
            presets["freellmapi-flash"] = {
                "model": "gemini-3.5-flash",
                "provider": "custom",
                "maxTokens": 8192,
                "contextWindowTokens": 1000000,
                "temperature": 0.1,
                "extraHeaders": None, "extraQuery": None, "extraBody": None, "reasoningEffort": None, "api": None
            }
            presets["freellmapi-haiku"] = {
                "model": "claude-haiku-4-5",
                "provider": "custom",
                "maxTokens": 8192,
                "contextWindowTokens": 200000,
                "temperature": 0.1,
                "extraHeaders": None, "extraQuery": None, "extraBody": None, "reasoningEffort": None, "api": None
            }
            presets["freellmapi-auto"] = {
                "model": "gemini-3.5-flash-lite",
                "provider": "custom",
                "maxTokens": 8192,
                "contextWindowTokens": 1000000,
                "temperature": 0.1,
                "extraHeaders": None, "extraQuery": None, "extraBody": None, "reasoningEffort": None, "api": None
            }
            presets["groq-backup"] = {
                "model": "openai/gpt-oss-120b",
                "provider": "groq",
                "maxTokens": 8192,
                "contextWindowTokens": 128000,
                "temperature": 0.1,
                "extraHeaders": None, "extraQuery": None, "extraBody": None, "reasoningEffort": None, "api": None
            }
            presets["gemini-flash"] = {
                "model": "gemini-3.5-flash",
                "provider": "gemini",
                "maxTokens": 8192,
                "contextWindowTokens": 1000000,
                "temperature": 0.1,
                "extraHeaders": None, "extraQuery": None, "extraBody": None, "reasoningEffort": None, "api": None
            }

            default_provider = os.getenv("DEFAULT_PROVIDER", "custom").strip() or "custom"
            default_model = os.getenv("DEFAULT_MODEL", "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite"
            default_preset = os.getenv("DEFAULT_PRESET", "freellmapi-gemini").strip() or "freellmapi-gemini"

            agent_defaults = config.setdefault("agents", {}).setdefault("defaults", {})
            agent_defaults["provider"] = default_provider
            agent_defaults["model"] = default_model
            agent_defaults["modelPreset"] = default_preset
            agent_defaults["fallbackModels"] = ["freellmapi-flash-lite", "freellmapi-flash"]
            agent_defaults["contextWindowTokens"] = 1000000
            # Antigravity Context Limits: prevent prompt bloat & memory spikes
            agent_defaults["maxToolResultChars"] = 3000
            agent_defaults["idleCompactAfterMinutes"] = 5
            agent_defaults["idleCompactCheckIntervalSeconds"] = 30
            print(f"✓ Activated Primary Model: {default_provider} / {default_model} via preset {default_preset} with Fallbacks (FreeLLMAPI Active)")

            # Set Telegram Bot Channel if provided
            tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            if tg_token:
                tg = config.setdefault("channels", {}).setdefault("telegram", {})
                tg["enabled"] = True
                tg["token"] = tg_token
                tg["mode"] = "polling"
                # Strict Private Admin Whitelist
                allowed_env = os.getenv("ALLOWED_TELEGRAM_USERS", "").strip()
                if allowed_env:
                    tg["allowFrom"] = [x.strip() for x in allowed_env.split(",") if x.strip()]
                else:
                    tg["allowFrom"] = [
                        "7198790563", "Infinity_0wner", "7198790563|Infinity_0wner",
                        "6161463701", "SILENTXOP", "6161463701|SILENTXOP"
                    ]
                print(f"🔒 Locked Telegram Channel (Private Admin Mode: {tg['allowFrom']})")

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

            # Allow installing optional channel features & packages from remote WebUI
            tools = config.setdefault("tools", {})
            tools["webuiAllowRemotePackageInstall"] = True
            tools["webui_allow_remote_package_install"] = True

            # Register Mailflare MCP Server
            mcp_servers = tools.setdefault("mcpServers", {})
            mcp_servers["mailflare"] = {
                "url": "https://mailflare.silentxop.workers.dev/mcp",
                "headers": {
                    "Authorization": "Bearer ep_82cd0825ac73dbcba99364754770e936"
                }
            }
            print("✓ Configured Mailflare MCP Server integration")

            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            print(f"✓ Configured WebUI & Gateway to listen on 0.0.0.0:{port} (Secret: {webui_secret})")
        except Exception as e:
            print(f"[!] Warning updating config: {e}")

    # 5. Push initial files if needed
    push_memory("Initial boot sync")

    # 5.1 Start 24/7 Memory Guard thread (Zero-Crash RAM Watchdog)
    guard_thread = threading.Thread(target=memory_guard_worker, daemon=True)
    guard_thread.start()

    # 6. Start non-blocking background sync thread (0ms latency, 15m clean interval)
    if GH_TOKEN:
        sync_thread = threading.Thread(target=background_sync_worker, args=(900,), daemon=True)
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
