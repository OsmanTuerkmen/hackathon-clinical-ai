"""Small-cell rule and exact half-up rounding."""
import unittest
from decimal import Decimal
from fractions import Fraction

from desk import disclosure as D


class RoundingTest(unittest.TestCase):
    def test_half_up_not_bankers(self):
        cases = {"0.05": "0.1", "0.15": "0.2", "0.25": "0.3", "2.25": "2.3", "37.25": "37.3", "1.45": "1.5",
                 "2.675": "2.7", "8.04999": "8.0", "8.05": "8.1", "99.95": "100.0", "0": "0.0"}
        for raw, expected in cases.items():
            self.assertEqual(D.round_half_up(raw), Decimal(expected), raw)

    def test_python_round_would_be_wrong(self):
        # documents why exact arithmetic is needed: binary floats / banker's rounding disagree
        self.assertEqual(round(37.25, 1), 37.2)
        self.assertEqual(round(1.45, 1), 1.4)
        self.assertEqual(D.round_half_up("37.25"), Decimal("37.3"))
        self.assertEqual(D.round_half_up("1.45"), Decimal("1.5"))

    def test_exact_fractions(self):
        self.assertEqual(D.round_half_up(Fraction(149 * 100, 400)), Decimal("37.3"))  # 37.25
        self.assertEqual(D.round_half_up(Fraction(1, 8) * 100), Decimal("12.5"))
        self.assertEqual(D.round_half_up(Fraction(2, 3) * 100), Decimal("66.7"))
        self.assertEqual(D.round_half_up(Fraction(-9, 4)), Decimal("-2.3"))  # ties away from zero

    def test_floats_are_refused(self):
        with self.assertRaises(TypeError):
            D.round_half_up(37.25)


class SmallCellTest(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(D.count_cell(0), "<10")
        self.assertEqual(D.count_cell(9), "<10")
        self.assertEqual(D.count_cell(10), 10)
        self.assertEqual(D.count_cell(1152), 1152)

    def test_percentages(self):
        self.assertEqual(D.percent_cell(9, 100), "suppressed")    # numerator below 10
        self.assertEqual(D.percent_cell(10, 9), "suppressed")     # denominator below 10
        self.assertEqual(D.percent_cell(0, 0), "suppressed")      # empty group
        self.assertEqual(D.percent_cell(10, 10), Decimal("100.0"))
        self.assertEqual(D.percent_cell(149, 400), Decimal("37.3"))

    def test_means(self):
        nine = [Fraction(25)] * 9
        self.assertEqual(D.mean_cell(nine), "suppressed")
        self.assertEqual(D.mean_cell([]), "suppressed")
        ten = [Fraction("27.0")] * 5 + [Fraction("27.5")] * 5     # 27.25 -> 27.3
        self.assertEqual(D.mean_cell(ten), Decimal("27.3"))

    def test_median(self):
        self.assertEqual(D.median_cell([Fraction(x) for x in range(1, 10)]), "suppressed")
        self.assertEqual(D.median_cell([Fraction(x) for x in range(1, 11)]), Decimal("5.5"))


if __name__ == "__main__":
    unittest.main()
