import unittest

import app as app_module


class GraphsPageTests(unittest.TestCase):
    def setUp(self):
        self.app_ctx = app_module.app.app_context()
        self.app_ctx.push()
        app_module.init()
        self.client = app_module.app.test_client()

    def tearDown(self):
        if self.app_ctx is not None:
            self.app_ctx.pop()
            self.app_ctx = None

    def test_graphs_page_exists(self):
        response = self.client.get("/graphs")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Graphs", response.data)
        self.assertIn(b"amChart", response.data)


class MortgageChangeTests(unittest.TestCase):
    def setUp(self):
        self.app_ctx = app_module.app.app_context()
        self.app_ctx.push()
        app_module.init()

    def tearDown(self):
        if self.app_ctx is not None:
            self.app_ctx.pop()
            self.app_ctx = None

    def test_recurring_extra_payment_is_reapplied_each_month(self):
        app_module.db().execute("delete from mortgage_change")
        app_module.db().execute("delete from property where id=1")
        app_module.db().execute(
            """
            insert into property
            values(1, 'Test', '123 Main', 200000, 200000, 5.0, 30, '2024-01-01', 0)
            on conflict(id) do update set
                name=excluded.name,
                address=excluded.address,
                purchase_price=excluded.purchase_price,
                original_loan=excluded.original_loan,
                interest_rate=excluded.interest_rate,
                term_years=excluded.term_years,
                loan_start_date=excluded.loan_start_date,
                extra_payment=excluded.extra_payment
            """
        )
        app_module.db().execute(
            """
            insert into mortgage_change
            (effective_date, extra_payment, extra_payment_kind, note)
            values ('2024-02-01', 150, 'monthly', 'extra each month')
            """
        )
        app_module.db().commit()

        rows = app_module.amortize(app_module.prop(), app_module.db())
        feb = next(r for r in rows if r["date"].isoformat() == "2024-02-01")
        mar = next(r for r in rows if r["date"].isoformat() == "2024-03-01")

        self.assertEqual(feb["extra"], 150.0)
        self.assertEqual(mar["extra"], 150.0)

    def test_one_time_extra_payment_only_applies_in_effective_month(self):
        app_module.db().execute("delete from mortgage_change")
        app_module.db().execute("delete from property where id=1")
        app_module.db().execute(
            """
            insert into property
            values(1, 'Test', '123 Main', 200000, 200000, 5.0, 30, '2024-01-01', 0)
            on conflict(id) do update set
                name=excluded.name,
                address=excluded.address,
                purchase_price=excluded.purchase_price,
                original_loan=excluded.original_loan,
                interest_rate=excluded.interest_rate,
                term_years=excluded.term_years,
                loan_start_date=excluded.loan_start_date,
                extra_payment=excluded.extra_payment
            """
        )
        app_module.db().execute(
            """
            insert into mortgage_change
            (effective_date, extra_payment, extra_payment_kind, note)
            values ('2024-02-01', 500, 'one_time', 'single extra payment')
            """
        )
        app_module.db().commit()

        rows = app_module.amortize(app_module.prop(), app_module.db())
        feb = next(r for r in rows if r["date"].isoformat() == "2024-02-01")
        mar = next(r for r in rows if r["date"].isoformat() == "2024-03-01")

        self.assertEqual(feb["extra"], 500.0)
        self.assertEqual(mar["extra"], 0.0)


if __name__ == "__main__":
    unittest.main()
