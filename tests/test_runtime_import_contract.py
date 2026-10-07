from pathlib import Path
import tempfile
import unittest

from scripts.verify_runtime_contracts import audit_runtime


class RuntimeImportResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.package = Path(self.temporary.name) / "play_anything"
        self.package.mkdir()
        (self.package / "__init__.py").write_text("", encoding="utf-8")

    def write(self, relative, source=""):
        path = self.package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return path

    def test_missing_explicit_relative_module_is_reported(self):
        self.write("module.py", "from .missing import thing\n")

        report = audit_runtime(self.package)

        self.assertFalse(report["passed"])
        self.assertTrue(any(item.get("kind") == "missing_internal_import"
                            and item.get("module") == "play_anything.missing"
                            for item in report["violations"]))

    def test_missing_explicit_absolute_submodule_is_reported(self):
        self.write("module.py", "import play_anything.missing\n")

        report = audit_runtime(self.package)

        self.assertFalse(report["passed"])
        self.assertTrue(any(item.get("kind") == "missing_internal_import"
                            and item.get("module") == "play_anything.missing"
                            for item in report["violations"]))

    def test_relative_import_beyond_package_root_is_reported(self):
        self.write("module.py", "from ..outside import thing\n")

        report = audit_runtime(self.package)

        self.assertFalse(report["passed"])
        self.assertTrue(any(item.get("kind") == "relative_import_escape"
                            for item in report["violations"]))

    def test_nested_relative_targets_and_namespace_packages_are_supported(self):
        self.write("pkg/existing.py", "value = 1\n")
        self.write("pkg/sub/module.py", "from ..existing import value\nfrom .sibling import value\n")
        self.write("pkg/sub/sibling.py", "value = 2\n")
        self.write("namespace_user.py", "from .ns.child import value\nimport play_anything.ns\n")
        self.write("ns/child.py", "value = 3\n")

        report = audit_runtime(self.package)

        self.assertTrue(report["passed"], report["violations"])

    def test_imported_names_from_existing_packages_are_not_resolved_as_modules(self):
        self.write("module.py", "import play_anything\nfrom . import exported_name\n")

        report = audit_runtime(self.package)

        self.assertTrue(report["passed"], report["violations"])


if __name__ == "__main__":
    unittest.main()
