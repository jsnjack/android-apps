import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


publisher = module("publish")
restorer = module("restore")


class PublisherTests(unittest.TestCase):
    def test_release_target_requires_known_app_and_exact_commit(self):
        config = {"apps": [{"source": "owner/wahoo-share"}, {"source": "owner/weather"}]}
        publisher.publication_target(config, "weather", "a" * 40)
        publisher.publication_target(config, None, None)
        for app, revision in [("unknown", None), (None, "a" * 40),
                              ("weather", "master"), ("weather", "a" * 7)]:
            with self.subTest(app=app, revision=revision), self.assertRaises(ValueError):
                publisher.publication_target(config, app, revision)

    def test_release_checks_out_exact_requested_commit(self):
        app = {"id": "example.app", "source": "owner/weather", "branch": "master",
               "private": False, "directory": "android"}
        revision = "a" * 40
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(publisher, "run", side_effect=[None, None, None, revision]) as run:
                _, actual = publisher.source_revision(app, Path(folder), False, revision)
                self.assertEqual(actual, revision)
                self.assertEqual(run.call_args_list[1].args[0],
                                 ["git", "fetch", "--depth", "1", "origin", revision])
            with patch.object(publisher, "run", side_effect=[None, None, None, "b" * 40]):
                with self.assertRaises(ValueError):
                    publisher.source_revision(app, Path(folder), False, revision)

    def test_unselected_app_keeps_its_published_revision_and_versions(self):
        old = {"revision": "published", "version_code": 12,
               "versions": [{"version_code": 12, "file": "app_12.apk"}]}
        with patch.object(publisher, "restore_versions", return_value=old["versions"]):
            result = publisher.preserved_app({"id": "app"}, old, Path("previous"),
                                             Path("repo"), Path("tools"), 3)
        self.assertEqual(result, old)
        with self.assertRaises(ValueError):
            publisher.preserved_app({"id": "app"}, {}, Path("previous"),
                                    Path("repo"), Path("tools"), 3)

    def test_version_exceeds_existing_install_and_previous_publication(self):
        for floor, previous, expected in [(2, {}, 3), (2, {"version_code": 12}, 13),
                                           (20, {"version_code": 12}, 21)]:
            with self.subTest(floor=floor, previous=previous):
                self.assertEqual(publisher.next_version({"version_floor": floor}, previous), expected)

    def test_version_limit(self):
        with self.assertRaises(ValueError):
            publisher.next_version({"version_floor": 2100000000}, {})

    def test_release_version_matches_make_release_without_downgrading(self):
        app = {"version_floor": 2}
        for version, old, expected in [("0.39.0", 12, 39000), ("1.2.3", 12, 1002003),
                                       ("0.1.0", 1200, 1201)]:
            with self.subTest(version=version, old=old):
                self.assertEqual(publisher.next_version(app, {"version_code": old}, version), expected)
        for version in ["1.1000.0", "1.0.1000", "2101.0.0"]:
            with self.subTest(version=version), self.assertRaises(ValueError):
                publisher.next_version(app, {}, version)
        for app_name, version in [(None, "1.2.3"), ("weather", "v1.2.3"), ("weather", "1.2")]:
            with self.subTest(app=app_name, version=version), self.assertRaises(ValueError):
                publisher.publication_target({"apps": [{"source": "owner/weather"}]},
                                             app_name, None, version)

    def test_rejects_wrong_signer_package_version_and_debuggable_build(self):
        app = {"id": "example.app", "signer": "abc"}
        good_cert = "Signer #1 certificate SHA-256 digest: abc"
        good_package = "package: name='example.app' versionCode='3'"
        for cert, package in [("certificate SHA-256 digest: def", good_package),
                              (good_cert, "package: name='wrong.app' versionCode='3'"),
                              (good_cert, "package: name='example.app' versionCode='2'"),
                              (good_cert, good_package + "\napplication-debuggable")]:
            with self.subTest(cert=cert, package=package):
                with patch.object(publisher, "run", side_effect=[cert, package]):
                    with self.assertRaises(ValueError):
                        publisher.verify_apk(Path("app.apk"), app, 3, Path("tools"))

    SITE_CONFIG = {
        "name": "Owner's apps", "url": "https://example.org/fdroid/repo",
        "apps": [{"id": "one.app", "name": "Rain & Sun", "summary": "Forecasts <today>",
                  "source": "owner/weather", "private": False},
                 {"id": "two.app", "name": "Secret", "summary": "Private one",
                  "source": "owner/secret", "private": True}],
    }
    SITE_STATE = {"apps": {
        "one.app": {"version_name": "1.2.3", "versions": [{"file": "one.app_3.apk"}]},
        "two.app": {"version_name": "0.1.0", "versions": [{"file": "two.app_1.apk"}]},
    }}

    def test_install_page_lists_each_app_with_download_and_escaped_text(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "one.app_3.apk").write_bytes(b"x" * 2_500_000)
            page = publisher.site_page(self.SITE_CONFIG, self.SITE_STATE, "ABC123", Path(folder))
        self.assertIn("Rain &amp; Sun", page)
        self.assertIn("Forecasts &lt;today&gt;", page)
        self.assertIn(">RS</div>", page)
        self.assertIn("Version 1.2.3 · 2.5 MB", page)
        self.assertIn("Version 0.1.0</p>", page)
        self.assertIn('href="fdroid/repo/one.app_3.apk"', page)
        self.assertIn('href="fdroid/repo/two.app_1.apk"', page)
        self.assertIn('href="https://example.org/fdroid/repo?fingerprint=ABC123"', page)
        self.assertIn("<code>ABC123</code>", page)
        self.assertIn("https://github.com/owner/weather", page)
        self.assertNotIn("owner/secret", page)

    def test_restore_rejects_zip_path_traversal(self):
        for filename in ["../private/key", "/tmp/key", "folder/../../key", "folder\\key"]:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as folder:
                archive = Path(folder) / "snapshot.zip"
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr(filename, "secret")
                with self.assertRaises(ValueError):
                    restorer.restore(archive, Path(folder) / "output")

    def test_restore_preserves_both_app_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "snapshot.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("fdroid/repo/one.apk", "one")
                bundle.writestr("fdroid/repo/two.apk", "two")
                bundle.writestr("state.json", "{}")
            output = Path(folder) / "output"
            restorer.restore(archive, output)
            self.assertEqual((output / "fdroid/repo/one.apk").read_text(), "one")
            self.assertEqual((output / "fdroid/repo/two.apk").read_text(), "two")


if __name__ == "__main__":
    unittest.main()
