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
    def test_version_exceeds_existing_install_and_previous_publication(self):
        for floor, previous, expected in [(2, {}, 3), (2, {"version_code": 12}, 13),
                                           (20, {"version_code": 12}, 21)]:
            with self.subTest(floor=floor, previous=previous):
                self.assertEqual(publisher.next_version({"version_floor": floor}, previous), expected)

    def test_version_limit(self):
        with self.assertRaises(ValueError):
            publisher.next_version({"version_floor": 2100000000}, {})

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
