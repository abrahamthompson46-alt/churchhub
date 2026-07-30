#!/usr/bin/env python3
"""Capture ChurchHub marketing screenshots from a running local server.

Usage:
  pip install playwright
  playwright install chromium
  python churchhub/marketing/screenshots/capture_marketing_shots.py

Env overrides:
  CHURCHHUB_BASE_URL   default http://127.0.0.1:8001
  CHURCHHUB_USER       default instadmin
  CHURCHHUB_PASSWORD   default instadmin123
  CHURCHHUB_PLATFORM_USER / CHURCHHUB_PLATFORM_PASSWORD  default admin / admin12345
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

OUT = Path(__file__).resolve().parent
BASE = os.environ.get("CHURCHHUB_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
USER = os.environ.get("CHURCHHUB_USER", "instadmin")
PASSWORD = os.environ.get("CHURCHHUB_PASSWORD", "instadmin123")
PLATFORM_USER = os.environ.get("CHURCHHUB_PLATFORM_USER", "admin")
PLATFORM_PASSWORD = os.environ.get("CHURCHHUB_PLATFORM_PASSWORD", "admin12345")

VIEWPORT = {"width": 1440, "height": 900}
MOBILE = {"width": 390, "height": 844}


def login(page, username: str, password: str, login_path: str = "/accounts/login/") -> None:
    page.goto(f"{BASE}{login_path}", wait_until="domcontentloaded")
    # Common Django username/password field names
    user_sel = 'input[name="username"], input[name="login"], #id_username, #id_login'
    pass_sel = 'input[name="password"], #id_password'
    page.wait_for_selector(user_sel, timeout=15000)
    page.fill(user_sel, username)
    page.fill(pass_sel, password)
    page.click('button[type="submit"], input[type="submit"]')
    page.wait_for_load_state("networkidle")


def shot(page, name: str, full_page: bool = True) -> None:
    path = OUT / name
    page.wait_for_timeout(400)
    page.screenshot(path=str(path), full_page=full_page)
    print(f"  wrote {path.name} ({path.stat().st_size // 1024} KB)")


def safe_goto(page, path: str) -> bool:
    try:
        resp = page.goto(f"{BASE}{path}", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(500)
        if resp and resp.status >= 400:
            print(f"  skip {path} → HTTP {resp.status}")
            return False
        # bounced to login?
        if "/login" in page.url and path not in ("/accounts/login/", "/portal/login/"):
            print(f"  skip {path} → redirected to login ({page.url})")
            return False
        return True
    except PlaywrightTimeout:
        print(f"  skip {path} → timeout")
        return False


def first_confirm_url(page) -> str | None:
    if not safe_goto(page, "/transactions/transactions/"):
        return None
    html = page.content()
    # UUID in transaction detail / confirm links
    m = re.search(r"/transactions/(?:confirm|receipt|transactions)/([0-9a-f-]{36})/", html, re.I)
    if m:
        return f"/transactions/confirm/{m.group(1)}/"
    return None


def run() -> int:
    print(f"Capturing from {BASE} -> {OUT}")
    with sync_playwright() as p:
        # Prefer installed Chrome/Edge to avoid downloading Playwright's Chromium (~180MB).
        browser = None
        for channel in ("chrome", "msedge", None):
            try:
                browser = (
                    p.chromium.launch(headless=True, channel=channel)
                    if channel
                    else p.chromium.launch(headless=True)
                )
                print(f"Browser: {channel or 'playwright-chromium'}")
                break
            except Exception as exc:
                print(f"  launch {channel or 'chromium'} failed: {exc}")
        if browser is None:
            print("No browser available.")
            return 1
        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
        page = context.new_page()

        print("Login (institution)…")
        try:
            login(page, USER, PASSWORD)
        except Exception as exc:
            print(f"Login failed: {exc}")
            # fallback common demo users
            for u, pw in (("pastor", "pastor123"), ("treasury", "treasury123"), ("admin", "admin12345")):
                print(f"  retry as {u}…")
                try:
                    login(page, u, pw)
                    break
                except Exception:
                    continue
            else:
                print("Could not log in with demo credentials.")
                browser.close()
                return 1

        # 01 Mission Control
        if safe_goto(page, "/dashboard/"):
            shot(page, "01-mission-control.png")

        # 02 Teller console — same page, scroll to teller if present
        if safe_goto(page, "/dashboard/"):
            for sel in (".teller", "#teller", "text=Teller", "text=Business date", "text=Business Date"):
                loc = page.locator(sel).first
                if loc.count():
                    try:
                        loc.scroll_into_view_if_needed()
                        break
                    except Exception:
                        pass
            shot(page, "02-teller-console.png", full_page=False)

        # 11 Finance trend — dashboard chart area
        if safe_goto(page, "/dashboard/"):
            for sel in ("canvas", ".chart", "text=Income", "text=expense"):
                loc = page.locator(sel).first
                if loc.count():
                    try:
                        loc.scroll_into_view_if_needed()
                        break
                    except Exception:
                        pass
            shot(page, "11-finance-trend.png", full_page=False)

        # 12 Cut-off
        if safe_goto(page, "/dashboard/cutoff/"):
            shot(page, "12-remittance-cutoff.png")

        # 03 Hierarchy
        if safe_goto(page, "/organization/"):
            shot(page, "03-organization-hierarchy.png")

        # 05 Members
        if safe_goto(page, "/members/"):
            shot(page, "05-members-directory.png")

        # 06 Church history
        if safe_goto(page, "/organization/church-history/"):
            shot(page, "06-church-history.png")

        # 07 Calendar
        if safe_goto(page, "/announcements/upcoming/"):
            shot(page, "07-announcements-calendar.png")

        # 09 Permissions matrix
        if safe_goto(page, "/permissions/matrix/"):
            shot(page, "09-permissions-matrix.png")

        # 04 Receipt confirmation
        confirm = first_confirm_url(page)
        if confirm and safe_goto(page, confirm):
            shot(page, "04-receipt-confirmation.png")
        else:
            print("  skip 04-receipt-confirmation.png → no transaction found")

        context.close()

        # Platform lane
        print("Login (platform)…")
        ctx2 = browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
        page2 = ctx2.new_page()
        try:
            login(page2, PLATFORM_USER, PLATFORM_PASSWORD)
            if safe_goto(page2, "/platform/denominations/"):
                shot(page2, "10-platform-tenancy.png")
            elif safe_goto(page2, "/platform/"):
                shot(page2, "10-platform-tenancy.png")
        except Exception as exc:
            print(f"  platform capture failed: {exc}")
        ctx2.close()

        # Portal mobile — login page or home if session works
        print("Portal (mobile viewport)…")
        ctx3 = browser.new_context(viewport=MOBILE, device_scale_factor=2)
        page3 = ctx3.new_page()
        if safe_goto(page3, "/portal/"):
            # if login required, capture login; else home
            shot(page3, "08-portal-mobile.png")
        ctx3.close()

        browser.close()

    written = sorted(OUT.glob("*.png"))
    print(f"Done. {len(written)} PNG(s) in {OUT}")
    for f in written:
        print(f"  - {f.name}")
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(run())
