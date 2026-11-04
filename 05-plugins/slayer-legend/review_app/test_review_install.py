"""Exercise the real refresh installer in a private tree with fake systemctl."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class ReviewReleaseSync(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plugin = self.root / 'plugin'
        self.source = self.plugin / 'review_app'
        self.source.mkdir(parents=True)
        shutil.copy2(HERE / 'refresh-installed.sh', self.source / 'refresh-installed.sh')
        for name in ('review_server.py', 'index.html', 'style.css', 'app.js', 'model.js'):
            (self.source / name).write_text('new ' + name)
        for name in ('evidence_review.py', 'zone_feedback.py', 'oral_feedback.py', 'page_zone_style.js',
                     'page_oral_feedback.js', 'screens.py', 'navigation.json', 'screen_registry.json'):
            (self.plugin / name).write_text('new ' + name)
        (self.plugin / 'fixtures').mkdir()
        (self.plugin / 'fixtures' / 'reviewed.txt').write_text('new reviewed fixture')
        # Runtime evidence is never a source artifact of the staged snapshot.
        (self.plugin / 'runtime.png').write_bytes(b'private capture')
        self.destination = self.root / 'installed'
        self.destination.mkdir()
        (self.destination / 'old-version').write_text('old code')
        self.unit = self.root / 'review.service'
        self.unit.write_text('private configuration, disabled flag preserved')
        self.feedback = self.root / 'feedback.json'
        self.feedback.write_text('private feedback')
        fake = self.root / 'bin'
        fake.mkdir()
        for name, content in {
            'id': '#!/bin/sh\necho 0\n',
            'systemctl': '''#!/bin/sh
printf '%s\n' "$*" >>"$TEST_LOG"
case "$1" in
  is-active) test "$TEST_ACTIVE" = yes ;;
  start) if test -f "$TEST_FAIL_START"; then rm "$TEST_FAIL_START"; exit 1; fi ;;
esac
''',
        }.items():
            (fake / name).write_text(content)
            (fake / name).chmod(0o755)
        self.log = self.root / 'systemctl.log'
        self.env = dict(os.environ, PATH=str(fake) + os.pathsep + os.environ['PATH'],
                        CLOUDPHONE_REVIEW_DESTINATION=str(self.destination), CLOUDPHONE_REVIEW_UNIT_FILE=str(self.unit),
                        TEST_LOG=str(self.log), TEST_ACTIVE='yes', TEST_FAIL_START=str(self.root / 'fail-start'))

    def refresh(self):
        return subprocess.run(['bash', str(self.source / 'refresh-installed.sh')], env=self.env,
                              text=True, capture_output=True)

    def assert_synced(self):
        manifest = json.loads((self.destination / 'source-manifest.json').read_text())
        for path, digest in manifest['files'].items():
            self.assertEqual(hashlib.sha256((self.destination / path).read_bytes()).hexdigest(), digest)
        self.assertEqual((self.destination / 'readers/navigation.json').read_bytes(),
                         (self.plugin / 'navigation.json').read_bytes())
        self.assertEqual((self.destination / 'readers/screens.py').read_bytes(), (self.plugin / 'screens.py').read_bytes())
        self.assertTrue((self.destination / 'readers/fixtures/reviewed.txt').is_file())
        self.assertFalse((self.destination / 'readers/runtime.png').exists())
        self.assertEqual(self.feedback.read_text(), 'private feedback')
        self.assertEqual(self.unit.read_text(), 'private configuration, disabled flag preserved')

    def test_absent_optional_service_is_never_created(self):
        self.unit.unlink()
        self.assertEqual(self.refresh().returncode, 0)
        self.assertTrue((self.destination / 'old-version').exists())
        self.assertFalse(self.log.exists())

    def test_active_refresh_copies_same_release_and_only_restarts_review(self):
        self.assertEqual(self.refresh().returncode, 0)
        self.assert_synced()
        self.assertEqual(self.log.read_text().splitlines(), ['is-active --quiet cloudphone-review.service',
                         'stop cloudphone-review.service', 'start cloudphone-review.service'])
        # A second run is idempotent and contains no stale files.
        self.assertEqual(self.refresh().returncode, 0)
        self.assert_synced()
        self.assertFalse(Path(str(self.destination) + '.old').exists())

    def test_inactive_installed_service_stays_inactive_and_unmodified(self):
        self.env['TEST_ACTIVE'] = 'no'
        self.assertEqual(self.refresh().returncode, 0)
        self.assert_synced()
        self.assertEqual(self.log.read_text().splitlines(), ['is-active --quiet cloudphone-review.service'])

    def test_failed_start_restores_previous_code_and_reports_failure(self):
        Path(self.env['TEST_FAIL_START']).touch()
        self.assertNotEqual(self.refresh().returncode, 0)
        self.assertEqual((self.destination / 'old-version').read_text(), 'old code')
        self.assertEqual(self.feedback.read_text(), 'private feedback')
        self.assertEqual(self.log.read_text().splitlines()[-2:],
                         ['start cloudphone-review.service', 'start cloudphone-review.service'])


if __name__ == '__main__':
    unittest.main()
