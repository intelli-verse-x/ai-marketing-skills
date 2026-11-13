import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('build_states', Path(__file__).resolve().parents[1] / 'references/sieve-domain-template/build_states.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class BuilderSafetyTests(unittest.TestCase):
    def test_safe_usernames_are_normalized(self):
        self.assertEqual('alice.example_1', module.safe_username('Alice.Example_1'))
        self.assertEqual('', module.safe_username(None))

    def test_export_paths_cannot_escape_image_directory(self):
        for name in ['../escape', '/tmp/escape', 'two/name', r'bad\name', '.', '..']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                module.safe_username(name)

    def test_unsafe_profile_stops_before_any_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'profiles.json'
            source.write_text(json.dumps([{'username': '../escape', 'profilePicUrl': 'https://example.test/photo.jpg'}]))
            args = ['build_states.py', '--workdir', str(root / 'work'), '--profiles-apify', str(source)]
            with mock.patch('sys.argv', args), mock.patch.object(module, 'download_image') as download, self.assertRaises(ValueError):
                module.main()
            download.assert_not_called()
            self.assertFalse((root / 'escape.jpg').exists())

    def test_non_https_and_credential_urls_never_reach_network(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / 'profile.jpg'
            for url in ['file:///etc/passwd', 'http://example.test/photo.jpg', 'https://user:pass@example.test/photo.jpg', 'https:///photo.jpg']:
                with self.subTest(url=url), mock.patch.object(module.urllib.request, 'urlopen') as request:
                    self.assertFalse(module.download_image(url, dest))
                    request.assert_not_called()
            self.assertFalse(dest.exists())

    def test_failed_download_does_not_log_signed_url_or_exception_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with mock.patch.object(module.urllib.request, 'urlopen', side_effect=RuntimeError('sensitive-token')), contextlib.redirect_stderr(output):
                self.assertFalse(module.download_image('https://example.test/photo.jpg?token=sensitive-token', Path(directory) / 'profile.jpg'))
            self.assertNotIn('sensitive-token', output.getvalue())
            self.assertIn('RuntimeError', output.getvalue())


if __name__ == '__main__':
    unittest.main()
