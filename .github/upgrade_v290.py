from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"Missing patch anchor: {label}")
    return text.replace(old, new, 1)


# ---- cli.py ----
cli_path = ROOT / "iptv_scraper" / "cli.py"
cli = cli_path.read_text(encoding="utf-8")

cli = replace_once(
    cli,
    "from urllib.parse import urljoin, urlparse",
    "from urllib.parse import urljoin, urlparse, parse_qs",
    "urllib imports",
)

anchor = '''    def _extract_public_stream_candidates(self, html_content, base_url):\n'''
new_helpers = '''    def _is_protected_player_url(self, url):\n        \"\"\"Return True for signed/authenticated/DRM-style player URLs.\n\n        Browser source mode may observe these URLs, but it deliberately does not\n        reuse credentials, signatures, tokens, cookies, or license endpoints.\n        \"\"\"\n        if not url or not url.startswith(('http://', 'https://')):\n            return False\n\n        try:\n            parsed = urlparse(url)\n            params = {key.lower() for key in parse_qs(parsed.query, keep_blank_values=True)}\n        except Exception:\n            return False\n\n        protected_params = {\n            'sig', 'signature', 'token', 'auth', 'authorization', 'jwt',\n            'hdnts', 'hdnea', 'policy', 'key-pair-id', 'license',\n        }\n        if params.intersection(protected_params):\n            return True\n\n        path = (parsed.path or '').lower()\n        return any(marker in path for marker in (\n            '/license', 'widevine', 'playready', 'fairplay',\n        ))\n\n'''
cli = replace_once(cli, anchor, new_helpers + anchor, "protected player helper")

old_extract = '''            for tag_name in ('video', 'source', 'iframe', 'embed'):\n                for tag in soup.find_all(tag_name):\n                    raw_url = tag.get('src') or tag.get('data-src')\n                    if not raw_url:\n                        continue\n\n                    raw_url = raw_url.strip()\n                    if raw_url.startswith('//'):\n                        raw_url = 'https:' + raw_url\n\n                    resolved = urljoin(base_url, raw_url)\n                    if not resolved.startswith(('http://', 'https://')):\n                        continue\n\n                    if tag_name in ('iframe', 'embed'):\n                        embed_urls.add(resolved)\n\n                    if self._is_public_stream_candidate(resolved):\n                        stream_urls.add(resolved)\n\n            # Many players place the media URL inside inline JavaScript/JSON.\n'''
new_extract = '''            for tag_name in ('video', 'source', 'iframe', 'embed'):\n                for tag in soup.find_all(tag_name):\n                    raw_url = tag.get('src') or tag.get('data-src')\n                    if not raw_url:\n                        continue\n\n                    raw_url = raw_url.strip()\n                    if raw_url.startswith('//'):\n                        raw_url = 'https:' + raw_url\n\n                    resolved = urljoin(base_url, raw_url)\n                    if not resolved.startswith(('http://', 'https://')):\n                        continue\n\n                    if tag_name in ('iframe', 'embed') and not self._is_protected_player_url(resolved):\n                        embed_urls.add(resolved)\n\n                    if self._is_public_stream_candidate(resolved) and not self._is_protected_player_url(resolved):\n                        stream_urls.add(resolved)\n\n            # Dynamic players often keep the next player URL on buttons or links\n            # and assign it to an iframe later with JavaScript (frame.src = ...).\n            for tag in soup.find_all(attrs={'data-src': True}):\n                raw_url = (tag.get('data-src') or '').strip()\n                if not raw_url:\n                    continue\n                if raw_url.startswith('//'):\n                    raw_url = 'https:' + raw_url\n                resolved = urljoin(base_url, raw_url)\n                if not resolved.startswith(('http://', 'https://')):\n                    continue\n                if self._is_protected_player_url(resolved):\n                    continue\n                if self._is_public_stream_candidate(resolved):\n                    stream_urls.add(resolved)\n                elif tag.name in ('button', 'a', 'iframe', 'embed'):\n                    embed_urls.add(resolved)\n\n            # Many players place the media URL inside inline JavaScript/JSON.\n'''
cli = replace_once(cli, old_extract, new_extract, "data-src extraction")

# Source URL mode should use normal TLS verification. Leave legacy scraper code unchanged.
start = cli.index("    def _validate_hls_segment_delivery")
end = cli.index("    def extract_iframe_streams", start)
source_block = cli[start:end]
source_block = source_block.replace("\n                    verify=False,", "")
source_block = source_block.replace("\n                    verify=False,", "")
source_block = source_block.replace("\n                        verify=False,", "")

# Do not crawl signed/authenticated player URLs in static mode.
source_block = replace_once(
    source_block,
    '''                page_url, depth = queue.pop(0)\n                if page_url in visited_pages:\n                    continue\n                visited_pages.add(page_url)\n\n                try:\n''',
    '''                page_url, depth = queue.pop(0)\n                if page_url in visited_pages:\n                    continue\n                visited_pages.add(page_url)\n\n                if self._is_protected_player_url(page_url):\n                    print(colored(\n                        f"[!] Signed/authenticated player skipped: {urlparse(page_url).netloc}",\n                        "yellow"\n                    ))\n                    continue\n\n                try:\n''',
    "static protected page guard",
)
source_block = replace_once(
    source_block,
    '''                            if embed_url not in visited_pages:\n                                queue.append((embed_url, depth + 1))\n                                embeds_seen_for_source += 1\n''',
    '''                            if self._is_protected_player_url(embed_url):\n                                print(colored(\n                                    f"[!] Signed/authenticated embedded player skipped: {urlparse(embed_url).netloc}",\n                                    "yellow"\n                                ))\n                                continue\n                            if embed_url not in visited_pages:\n                                queue.append((embed_url, depth + 1))\n                                embeds_seen_for_source += 1\n''',
    "static protected embed guard",
)

browser_method = r'''    def scrape_source_urls_browser(self, source_urls, num_links=10, channel_name='', wait_player=False):
        """Use a real browser to inspect public dynamic players without bypassing access controls."""
        if isinstance(source_urls, str):
            source_urls = [source_urls]

        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
        except ImportError:
            print(colored("[!] Browser mode requires Playwright.", "red"))
            print(colored('    Install with: python3 -m pip install -e ".[browser]"', "yellow"))
            print(colored("    Then run: python3 -m playwright install chromium", "yellow"))
            return 0

        candidates = {}
        protected_seen = set()
        wait_seconds = 12 if wait_player else 2

        def countdown_hint(page):
            texts = []
            try:
                texts.append(page.locator('body').inner_text(timeout=1000))
            except Exception:
                pass
            for frame in page.frames:
                if self._is_protected_player_url(frame.url):
                    continue
                try:
                    texts.append(frame.locator('body').inner_text(timeout=700))
                except Exception:
                    pass
            joined = '\n'.join(texts)
            match = re.search(
                r'(?:espera|wait|segundos|seconds|continuar|continue)[^0-9]{0,24}(\d{1,2})'
                r'|(\d{1,2})[^\n]{0,24}(?:segundos|seconds)',
                joined,
                flags=re.IGNORECASE,
            )
            if match:
                return match.group(1) or match.group(2)
            return None

        print(colored(f"[*] Browser mode loading {len(source_urls)} source page(s)...", "cyan"))

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                        'AppleWebKit/537.36 Chrome/128.0 Safari/537.36'
                    )
                )

                for source_url in source_urls:
                    if self.shutdown_flag.is_set() or self.total_working >= num_links:
                        break
                    if not source_url.startswith(('http://', 'https://')):
                        print(colored(f"[!] Skipping invalid URL: {source_url}", "red"))
                        continue
                    if self._is_protected_player_url(source_url):
                        print(colored("[!] Signed/authenticated source URL skipped.", "yellow"))
                        continue

                    page = context.new_page()
                    page_candidates = {}
                    fallback_title = urlparse(source_url).netloc or 'Web Stream'
                    current_title = channel_name or fallback_title

                    def observe_request(request):
                        nonlocal current_title
                        request_url = request.url
                        try:
                            frame_url = request.frame.url
                        except Exception:
                            frame_url = ''

                        if self._is_protected_player_url(request_url) or self._is_protected_player_url(frame_url):
                            host = urlparse(request_url).netloc or request_url
                            protected_seen.add(host)
                            return

                        if self._is_public_stream_candidate(request_url):
                            page_candidates.setdefault(request_url, current_title)

                    page.on('request', observe_request)

                    try:
                        print(colored(f"[*] Opening: {source_url}", "white"))
                        page.goto(source_url, wait_until='domcontentloaded', timeout=30000)
                        try:
                            current_title = channel_name or page.title() or fallback_title
                        except Exception:
                            current_title = channel_name or fallback_title

                        # Inspect the fully rendered page first.
                        streams, embeds = self._extract_public_stream_candidates(page.content(), page.url)
                        for stream_url in streams:
                            page_candidates.setdefault(stream_url, current_title)
                        for embed_url in embeds:
                            if self._is_protected_player_url(embed_url):
                                protected_seen.add(urlparse(embed_url).netloc or embed_url)

                        options = page.locator('.option[data-src]')
                        option_count = min(options.count(), 6)
                        if option_count:
                            print(colored(f"[+] Found {option_count} player option(s).", "green"))

                        for index in range(option_count):
                            option = options.nth(index)
                            data_src = option.get_attribute('data-src') or ''
                            label = (option.inner_text(timeout=1000) or f'Option {index + 1}').strip()

                            if self._is_protected_player_url(data_src):
                                protected_seen.add(urlparse(data_src).netloc or data_src)
                                print(colored(f"[!] {label}: signed/authenticated URL skipped.", "yellow"))
                                continue

                            print(colored(f"[*] Opening {label} and waiting for normal player initialization...", "cyan"))
                            try:
                                option.click(timeout=5000)
                            except PlaywrightTimeoutError:
                                print(colored(f"[!] Could not click {label}; continuing.", "yellow"))
                                continue

                            for second in range(wait_seconds):
                                page.wait_for_timeout(1000)
                                if wait_player:
                                    hint = countdown_hint(page)
                                    if hint:
                                        print(colored(f"    countdown detected: {hint}", "cyan"))

                            # Inspect frame URLs and rendered HTML after the normal wait.
                            for frame in page.frames:
                                frame_url = frame.url or ''
                                if self._is_protected_player_url(frame_url):
                                    protected_seen.add(urlparse(frame_url).netloc or frame_url)
                                    continue
                                if self._is_public_stream_candidate(frame_url):
                                    page_candidates.setdefault(frame_url, current_title)
                                try:
                                    frame_streams, _ = self._extract_public_stream_candidates(
                                        frame.content(), frame_url or page.url
                                    )
                                    for stream_url in frame_streams:
                                        page_candidates.setdefault(stream_url, current_title)
                                except Exception:
                                    pass

                        for stream_url, title in page_candidates.items():
                            candidates.setdefault(stream_url, title)

                    except PlaywrightTimeoutError:
                        print(colored(f"[✗] Browser timeout: {source_url}", "red"))
                    except Exception as exc:
                        print(colored(f"[✗] Browser error for {source_url}: {exc}", "red"))
                    finally:
                        page.close()

                context.close()
                browser.close()
        except Exception as exc:
            print(colored(f"[!] Could not start browser mode: {exc}", "red"))
            print(colored("[*] If Chromium is missing, run: python3 -m playwright install chromium", "yellow"))
            return 0

        if protected_seen:
            print(colored(
                "[!] Signed/authenticated player layer detected; protected downstream media was not extracted.",
                "yellow"
            ))
            for host in sorted(protected_seen):
                print(colored(f"    - {host}", "yellow"))

        if not candidates:
            print(colored(
                "[!] Browser mode did not expose any unprotected public .m3u8/.m3u/.mpd/.ts URL.",
                "yellow"
            ))
            return 0

        print(colored(f"[*] Browser observed {len(candidates)} public candidate stream URL(s).", "cyan"))
        print(colored("[*] Validating candidates...", "yellow"))

        for index, (stream_url, title) in enumerate(candidates.items(), 1):
            if self.shutdown_flag.is_set() or self.total_working >= num_links:
                break
            if self._is_protected_player_url(stream_url):
                continue

            print(colored(f"[{index}/{len(candidates)}] {title}", "white"), end=" ")
            path_only = stream_url.lower().split('?', 1)[0]
            if path_only.endswith('.m3u8'):
                if not self._validate_hls_segment_delivery(stream_url):
                    print(colored("✗ manifest reachable, but no media segment", "red"))
                    continue
            elif not self.test_iptv_link(stream_url, show_progress=False):
                print(colored("✗", "red"))
                continue

            self.total_working += 1
            saved_title = title
            if any(item.get('title') == saved_title for item in self.scraped_links):
                saved_title = f"{title} {self.total_working}"
            self.scraped_links.append({'title': saved_title, 'url': stream_url})
            print(colored(f"✓ [{self.total_working}/{num_links}]", "green"))

        return len(self.scraped_links)

'''
source_block = source_block + browser_method
cli = cli[:start] + source_block + cli[end:]

# Add browser CLI switches.
source_arg_anchor = '''    parser.add_argument(\n        '--source-url',\n        action='append',\n        default=[],\n        metavar='URL',\n        help='Scrape direct public stream URLs from a channel web page (repeatable)'\n    )\n\n'''
browser_args = source_arg_anchor + '''    parser.add_argument(\n        '--browser',\n        action='store_true',\n        help='Use Playwright for JavaScript-rendered public channel pages'\n    )\n\n    parser.add_argument(\n        '--wait-player',\n        action='store_true',\n        help='With --browser, wait up to 12 seconds after each player option'\n    )\n\n'''
cli = replace_once(cli, source_arg_anchor, browser_args, "browser CLI args")

cli = replace_once(
    cli,
    '''            scraper.scrape_source_urls(\n                args.source_url,\n                num_links=num_links,\n                channel_name=channel_name,\n            )\n''',
    '''            if args.wait_player and not args.browser:\n                parser.error("--wait-player requires --browser")\n\n            if args.browser:\n                scraper.scrape_source_urls_browser(\n                    args.source_url,\n                    num_links=num_links,\n                    channel_name=channel_name,\n                    wait_player=args.wait_player,\n                )\n            else:\n                scraper.scrape_source_urls(\n                    args.source_url,\n                    num_links=num_links,\n                    channel_name=channel_name,\n                )\n''',
    "browser mode dispatch",
)

cli = cli.replace("Advanced Multi-Source Stream Finder v2.8.0", "Advanced Multi-Source Stream Finder v2.9.0")
cli_path.write_text(cli, encoding="utf-8")

# ---- package version / extras ----
setup_path = ROOT / "setup.py"
setup = setup_path.read_text(encoding="utf-8")
setup = setup.replace('version="2.8.0"', 'version="2.9.0"', 1)
setup = replace_once(
    setup,
    '''    install_requires=[\n        "beautifulsoup4>=4.9.0",\n        "requests>=2.25.0",\n        "termcolor>=1.1.0",\n        "colorama>=0.4.0",\n        "art>=5.0",\n    ],\n''',
    '''    install_requires=[\n        "beautifulsoup4>=4.9.0",\n        "requests>=2.25.0",\n        "termcolor>=1.1.0",\n        "colorama>=0.4.0",\n        "art>=5.0",\n    ],\n    extras_require={\n        "browser": ["playwright>=1.40.0"],\n    },\n''',
    "browser extra",
)
setup_path.write_text(setup, encoding="utf-8")

init_path = ROOT / "iptv_scraper" / "__init__.py"
init_text = init_path.read_text(encoding="utf-8").replace('__version__ = "2.8.0"', '__version__ = "2.9.0"', 1)
init_path.write_text(init_text, encoding="utf-8")

# ---- README ----
readme_path = ROOT / "README.md"
readme = readme_path.read_text(encoding="utf-8")
readme = readme.replace("version-2.8.0-orange.svg", "version-2.9.0-orange.svg", 1)
readme = readme.replace(
    "| 🌐 **Web Page Sources** | Extract public stream URLs from channel pages with `--source-url` |",
    "| 🌐 **Web Page Sources** | Extract public streams from static or JavaScript-rendered channel pages |",
    1,
)
readme = readme.replace(
    "# Repeat --source-url to scan several pages\niptv-scraper --source-url \"https://example.com/channel-1\" --source-url \"https://example.com/channel-2\" -n 10\n",
    "# Repeat --source-url to scan several pages\niptv-scraper --source-url \"https://example.com/channel-1\" --source-url \"https://example.com/channel-2\" -n 10\n\n# JavaScript-rendered public player: use a real browser and wait normally\niptv-scraper --source-url \"https://example.com/live\" --browser --wait-player -n 5\n",
    1,
)
readme = readme.replace(
    "| `--source-url URL` | Scrape a public channel page; repeat the option for multiple pages |\n",
    "| `--source-url URL` | Scrape a public channel page; repeat the option for multiple pages |\n| `--browser` | Use Playwright for JavaScript-rendered public players |\n| `--wait-player` | With `--browser`, wait up to 12 seconds after each player option |\n",
    1,
)
readme = readme.replace(
    "### Quick Install\n\n```bash\npip install -e .\n```",
    "### Quick Install\n\n```bash\npip install -e .\n```\n\n### Browser mode (optional)\n\n```bash\npython3 -m pip install -e \".[browser]\"\npython3 -m playwright install chromium\n```",
    1,
)
readme = readme.replace("- art\n", "- art\n- playwright (optional, only for `--browser`)\n", 1)
readme_path.write_text(readme, encoding="utf-8")

# ---- CHANGELOG ----
changelog_path = ROOT / "CHANGELOG.md"
changelog = changelog_path.read_text(encoding="utf-8")
entry = '''## Version 2.9.0 (2026-09-08) - Dynamic Public Player Browser Mode 🌐\n\n- Added `--browser` and `--wait-player` for JavaScript-rendered public channel pages.\n- Added generic `data-src` player-option discovery (including button-driven iframe players).\n- Browser mode clicks normal player options and waits for the page/player to initialize naturally.\n- Observes direct public `.m3u8`, `.m3u`, `.mpd`, and `.ts` requests without collecting cookies or headers.\n- Detects signed/authenticated/DRM-style layers (`sig`, token/auth parameters, license endpoints) and skips protected downstream extraction.\n- New source-page/HLS requests use normal TLS certificate verification, avoiding the previous source-mode `InsecureRequestWarning`.\n- Playwright is optional via `pip install -e \".[browser]\"`; Chromium is installed separately with `python3 -m playwright install chromium`.\n\n---\n\n'''
changelog = changelog.replace("# IPTV Scraper - Complete Changelog\n\n", "# IPTV Scraper - Complete Changelog\n\n" + entry, 1)
changelog_path.write_text(changelog, encoding="utf-8")

# ---- tests ----
tests = ROOT / "tests"
tests.mkdir(exist_ok=True)
(tests / "test_source_url_v290.py").write_text(r'''import unittest

from iptv_scraper.cli import IPTVScraper


class SourceUrlV290Tests(unittest.TestCase):
    def setUp(self):
        self.scraper = IPTVScraper()

    def test_button_data_src_becomes_embed_candidate(self):
        html = '<button class="option" data-src="/live/core.php?canal=demo">Option 1</button>'
        streams, embeds = self.scraper._extract_public_stream_candidates(
            html, 'https://example.com/channel.html'
        )
        self.assertEqual(streams, [])
        self.assertIn('https://example.com/live/core.php?canal=demo', embeds)

    def test_signed_player_is_protected(self):
        self.assertTrue(self.scraper._is_protected_player_url(
            'https://player.example/stream.php?canal=demo&sig=abc123'
        ))

    def test_plain_public_hls_is_not_protected(self):
        url = 'https://cdn.example/live/channel.m3u8'
        self.assertFalse(self.scraper._is_protected_player_url(url))
        self.assertTrue(self.scraper._is_public_stream_candidate(url))


if __name__ == '__main__':
    unittest.main()
''', encoding="utf-8")

print("v2.9.0 patch applied")
