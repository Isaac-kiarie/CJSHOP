import re

from django.conf import settings
from django.test import SimpleTestCase

DEPLOY = settings.BASE_DIR / "deploy"
PLACEHOLDERS = ("", "change-me", "your-")


def read(name):
    return (DEPLOY / name).read_text(encoding="utf-8")


def block(text, marker):
    return text.split(marker, 1)[1].split("}", 1)[0]


class NginxTests(SimpleTestCase):
    def test_the_forwarded_for_header_is_overwritten_not_appended(self):
        everything = read("nginx-proxy.conf") + read("nginx-site.conf")
        self.assertIn("proxy_set_header X-Forwarded-For $remote_addr;", everything)
        self.assertNotIn("$proxy_add_x_forwarded_for", everything)

    def test_the_proxy_tells_django_the_scheme_and_host(self):
        proxy = read("nginx-proxy.conf")
        self.assertIn("proxy_set_header X-Forwarded-Proto $scheme;", proxy)
        self.assertIn("proxy_set_header Host $host;", proxy)

    def test_version_hidden_and_uploads_limited(self):
        site = read("nginx-site.conf")
        self.assertIn("server_tokens off;", site)
        self.assertRegex(site, r"client_max_body_size \d+m;")

    def test_credential_pages_are_throttled_but_the_callback_is_not(self):
        site = read("nginx-site.conf")
        for marker in ("location = /accounts/login/", "location = /accounts/register/", "location /__ADMIN__/"):
            self.assertIn("limit_req", block(site, marker), marker)
        self.assertNotIn("limit_req", block(site, "location /payments/callback/"))

    def test_static_and_media_are_served_with_nosniff(self):
        site = read("nginx-site.conf")
        for marker in ("location /static/", "location /media/"):
            self.assertIn("nosniff", block(site, marker))

    def test_every_included_snippet_exists_in_the_repo(self):
        self.assertTrue((DEPLOY / "nginx-proxy.conf").exists())
        self.assertIn("cjshop-proxy.conf", read("nginx-site.conf"))


class GunicornAndSystemdTests(SimpleTestCase):
    def test_gunicorn_uses_a_private_socket_not_a_public_port(self):
        conf = read("gunicorn.conf.py")
        self.assertIn('bind = "unix:', conf)
        self.assertNotIn("0.0.0.0", conf)

    def test_the_gunicorn_timeout_exceeds_the_worst_case_daraja_wait(self):
        timeout = int(re.search(r"^timeout = (\d+)", read("gunicorn.conf.py"), re.M).group(1))
        self.assertGreater(timeout, 2 * settings.MPESA_TIMEOUT)

    def test_the_app_runs_unprivileged_with_a_private_socket_directory(self):
        unit = read("cjshop.service")
        for line in ("User=deploy", "RuntimeDirectory=cjshop", "NoNewPrivileges=true", "Restart=on-failure"):
            self.assertIn(line, unit)
        self.assertNotIn("User=root", unit)

    def test_the_socket_path_is_the_same_everywhere(self):
        for name in ("gunicorn.conf.py", "nginx-site.conf", "deploy.sh"):
            self.assertIn("/run/cjshop/gunicorn.sock", read(name), name)

    def test_the_reconcile_timer_runs_every_minute(self):
        self.assertIn("OnUnitActiveSec=1min", read("cjshop-reconcile.timer"))
        self.assertIn("reconcile_payments", read("cjshop-reconcile.service"))


class ScriptTests(SimpleTestCase):
    def test_scripts_use_bash_in_strict_mode(self):
        for name in ("deploy.sh", "backup.sh", "smoke_test.sh"):
            text = read(name)
            self.assertTrue(text.startswith("#!/usr/bin/env bash"), name)
            self.assertRegex(text, r"(?m)^set -", name)

    def test_backup_never_puts_a_password_on_the_command_line(self):
        script = read("backup.sh")
        self.assertIn("--defaults-file", script)
        self.assertNotRegex(script, r"--password|\s-p[A-Za-z0-9]")
        self.assertIn("pipefail", script)

    def test_a_backup_is_checked_before_it_is_trusted(self):
        script = read("backup.sh")
        self.assertIn("gzip -t", script)
        self.assertIn(".part", script)

    def test_deploy_backs_up_before_it_migrates(self):
        script = read("deploy.sh")
        self.assertLess(script.index("backup.sh"), script.index("migrate"))
        self.assertLess(script.index("check --deploy"), script.index("migrate"))

    def test_the_smoke_test_covers_the_essentials(self):
        script = read("smoke_test.sh")
        for needle in ("healthz", "payments/callback/WRONG", "strict-transport-security", "s_client", ".env"):
            self.assertIn(needle, script)


class SecretHygieneTests(SimpleTestCase):
    NAMES = ("SECRET_KEY", "DB_PASSWORD", "MPESA_CONSUMER_KEY", "MPESA_CONSUMER_SECRET",
             "MPESA_PASSKEY", "MPESA_CALLBACK_TOKEN")

    def test_no_real_secret_values_are_in_the_deploy_folder(self):
        for path in DEPLOY.iterdir():
            text = path.read_text(encoding="utf-8")
            for name in self.NAMES:
                for value in re.findall(rf"(?m)^{name}=(\S*)", text):
                    self.assertTrue(value.startswith(PLACEHOLDERS), f"{path.name} has a value for {name}")

    def test_the_production_example_lists_every_safety_switch(self):
        text = read("env.production.example")
        for line in ("PRODUCTION=True", "BEHIND_PROXY=True", "DEBUG=False"):
            self.assertIn(line, text)
        self.assertIn("MPESA_ENV=sandbox", text)