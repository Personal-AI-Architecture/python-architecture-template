import unittest

from tests import bootstrap  # noqa: F401
from scripts.check_contracts import check_contracts


class ContractTests(unittest.TestCase):
    def test_contract_mirror_matches_paa_baseline(self):
        self.assertEqual(check_contracts(), [])


if __name__ == "__main__":
    unittest.main()
