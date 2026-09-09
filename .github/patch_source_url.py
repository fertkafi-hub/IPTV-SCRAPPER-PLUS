from pathlib import Path

path = Path("iptv_scraper/cli.py")
text = path.read_text(encoding="utf-8")

old_validation = '''            if not self.test_iptv_link(stream_url, show_progress=False):
                print(colored("✗", "red"))
                continue

            path_only = stream_url.lower().split('?', 1)[0]
            if path_only.endswith('.m3u8'):
                if not self._validate_hls_segment_delivery(stream_url):
                    print(colored("✗ manifest reachable, but no media segment", "red"))
                    continue
'''

new_validation = '''            path_only = stream_url.lower().split('?', 1)[0]
            if path_only.endswith('.m3u8'):
                # HLS manifests can be very small. Validate the manifest and
                # require actual media-segment bytes instead of applying the
                # legacy minimum Content-Length check first.
                if not self._validate_hls_segment_delivery(stream_url):
                    print(colored("✗ manifest reachable, but no media segment", "red"))
                    continue
            elif not self.test_iptv_link(stream_url, show_progress=False):
                print(colored("✗", "red"))
                continue
'''

if old_validation in text:
    text = text.replace(old_validation, new_validation, 1)
elif new_validation not in text:
    raise SystemExit("Expected HLS validation block not found")

old_arg = '''    parser.add_argument(
    '--source-url',
    action='append',
    default=[],
    metavar='URL',
    help='Scrape direct public stream URLs from a channel web page (repeatable)'
)
'''

new_arg = '''    parser.add_argument(
        '--source-url',
        action='append',
        default=[],
        metavar='URL',
        help='Scrape direct public stream URLs from a channel web page (repeatable)'
    )
'''

if old_arg in text:
    text = text.replace(old_arg, new_arg, 1)

path.write_text(text, encoding="utf-8")
print("PATCH_OK")
