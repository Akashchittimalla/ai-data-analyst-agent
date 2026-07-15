"""Dependency-light regression tests for core backend rules."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from chart_recommender import recommend_chart
from sql_safety import validate_read_sql


class ReadSqlValidationTests(unittest.TestCase):
    def test_allows_select_and_cte(self):
        self.assertEqual(validate_read_sql("SELECT * FROM sales;"), "SELECT * FROM sales")
        self.assertTrue(validate_read_sql("WITH x AS (SELECT 1) SELECT * FROM x").startswith("WITH"))

    def test_rejects_mutations_and_multiple_statements(self):
        for sql in ["DELETE FROM sales", "SELECT 1; DROP TABLE sales", "COPY sales TO 'x.csv'"]:
            with self.assertRaises(Exception):
                validate_read_sql(sql)


class ChartRecommendationTests(unittest.TestCase):
    def test_time_series_uses_line_chart(self):
        rows = [{"month": "2024-01", "revenue": 10}, {"month": "2024-02", "revenue": 15}]
        chart = recommend_chart("monthly revenue", rows, ["month", "revenue"])
        self.assertEqual(chart["type"], "line")
        self.assertEqual(chart["x_col"], "month")

    def test_distribution_uses_doughnut(self):
        rows = [{"category": "Home", "revenue": 10}, {"category": "Sports", "revenue": 15}]
        chart = recommend_chart("revenue share", rows, ["category", "revenue"])
        self.assertEqual(chart["type"], "doughnut")


if __name__ == "__main__":
    unittest.main()
