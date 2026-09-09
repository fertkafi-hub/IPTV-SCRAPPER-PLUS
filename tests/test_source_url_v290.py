import unittest

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
