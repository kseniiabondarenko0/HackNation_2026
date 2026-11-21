"""Small production-readiness checks: robots.txt, favicon.ico, no leftover version badge, secret-key guard."""
import os
import subprocess
import sys
from pathlib import Path

from django.test import TestCase
from django.urls import reverse

ROOT = Path(__file__).resolve().parent.parent


class RuntimeExtrasTests(TestCase):
    def test_robots_txt_blocks_admin_only(self):
        r = self.client.get("/robots.txt")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Disallow: /admin/", r.content.decode())

    def test_favicon_ico_redirects_to_static_svg(self):
        r = self.client.get("/favicon.ico")
        self.assertEqual(r.status_code, 301)
        self.assertTrue(r["Location"].endswith("web/favicon.svg"))

    def test_no_prototype_badge(self):
        self.assertNotContains(self.client.get(reverse("overview")), "V0.2")


class SecretKeyGuardTests(TestCase):
    def _run(self, **env):
        e = {k: v for k, v in os.environ.items() if k != "DJANGO_SECRET_KEY"}
        e.update(DJANGO_DEBUG="0", DB_PATH=":memory:", **env)
        return subprocess.run([sys.executable, "manage.py", "check"], cwd=ROOT, env=e, capture_output=True, text=True)

    def test_default_key_refused_when_debug_off(self):
        r = self._run()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", r.stderr)

    def test_custom_key_accepted_when_debug_off(self):
        self.assertEqual(self._run(DJANGO_SECRET_KEY="x" * 50, ALLOWED_HOSTS="localhost").returncode, 0)
