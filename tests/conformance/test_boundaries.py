import unittest

from tests import bootstrap  # noqa: F401
from scripts.check_imports import check_imports
from scripts.check_lockin import check_lockin


class BoundaryTests(unittest.TestCase):
    def test_import_boundaries_hold(self):
        self.assertEqual(check_imports(), [])

    def test_provider_lockin_checks_hold(self):
        self.assertEqual(check_lockin(), [])


if __name__ == "__main__":
    unittest.main()
