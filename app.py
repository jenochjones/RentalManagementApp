from datetime import date, timedelta
from pathlib import Path
import sqlite3

from flask import (
    Flask,
    g,
    redirect,
    render_template,
    request,
    url_for,
    jsonify,
)

from mortgage import amortize, month_start, add_month


ROOT = Path(__file__).parent
DB = ROOT / "rental_tracker.db"

app = Flask(__name__)
app.secret_key = "change-this-secret-key"


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close(_=None):
    x = g.pop("db", None)
    if x:
        x.close()


def init():
    db().executescript((ROOT / "schema.sql").read_text())
    db().commit()


def prop():
    return db().execute(
        "select * from property where id=1"
    ).fetchone()


def active(items, when):
    inc = 0
    exp = 0

    for x in items:
        if (
            date.fromisoformat(x["effective_start"]) <= when
            and (
                not x["effective_end"]
                or when <= date.fromisoformat(x["effective_end"])
            )
        ):
            if x["kind"] == "income":
                inc += x["monthly_amount"]
            else:
                exp += x["monthly_amount"]

    return inc, exp


def enrich(rows, items, costs):
    bymonth = {}

    for x in costs:
        m = month_start(x["cost_date"])
        bymonth[m] = bymonth.get(m, 0) + x["amount"]

    running = 0

    if rows:
        running -= sum(
            x["amount"]
            for x in costs
            if month_start(x["cost_date"]) < rows[0]["date"]
        )

    for r in rows:
        inc, exp = active(items, r["date"])
        one = bymonth.get(r["date"], 0)

        net = inc - exp - one - r["interest"]
        running += net

        r.update(
            income=inc,
            expense=exp,
            one_time=one,
            net=net,
            running=running,
        )

    return rows


def data():
    d = db()
    p = prop()

    items = d.execute(
        "select * from recurring_item order by effective_start"
    ).fetchall()

    costs = d.execute(
        "select * from one_time_cost order by cost_date"
    ).fetchall()

    rows = enrich(
        amortize(p, d) if p else [],
        items,
        costs,
    )

    return p, items, costs, rows


@app.route("/")
def home():
    p, items, costs, rows = data()

    now = date.today()

    inc, exp = active(items, now)

    future = [
        r for r in rows
        if r["date"] >= month_start(now)
    ]

    mortgage = future[0]["payment"] if future else 0

    payoff = rows[-1]["date"] if rows else None

    pi, pe = (
        active(items, payoff)
        if payoff
        else (inc, exp)
    )

    return render_template(
        "home.html",
        p=p,
        payoff=payoff,
        current_net=inc - exp - mortgage,
        payoff_monthly=pi - pe,
        total_payoff=rows[-1]["running"] if rows else 0,
        inc=inc,
        exp=exp,
        mortgage=mortgage,
        cost_total=sum(x["amount"] for x in costs),
        rows=future[:12],
    )


@app.route("/property", methods=["GET", "POST"])
def property_page():
    p = prop()

    if request.method == "POST":
        v = (
            request.form["name"],
            request.form["address"],
            float(request.form["purchase_price"]),
            float(request.form["original_loan"]),
            float(request.form["interest_rate"]),
            int(request.form["term_years"]),
            request.form["loan_start_date"],
            float(request.form.get("extra_payment") or 0),
        )

        db().execute(
            """
            insert into property
            values(1,?,?,?,?,?,?,?,?)
            on conflict(id) do update set
                name=?,
                address=?,
                purchase_price=?,
                original_loan=?,
                interest_rate=?,
                term_years=?,
                loan_start_date=?,
                extra_payment=?
            """,
            v + v,
        )

        db().commit()
        return redirect(url_for("home"))

    return render_template("property.html", p=p)


@app.route("/one-time", methods=["GET", "POST"])
def one_time():
    if request.method == "POST":
        db().execute(
            """
            insert into one_time_cost
            (category, description, amount, cost_date)
            values (?, ?, ?, ?)
            """,
            (
                request.form["category"],
                request.form["description"],
                float(request.form["amount"]),
                request.form["cost_date"],
            ),
        )

        db().commit()
        return redirect(url_for("one_time"))

    return render_template(
        "one_time.html",
        rows=db().execute(
            "select * from one_time_cost order by cost_date desc"
        ).fetchall(),
    )


@app.post("/one-time/<int:i>/delete")
def del_one(i):
    db().execute(
        "delete from one_time_cost where id=?",
        (i,),
    )
    db().commit()
    return redirect(url_for("one_time"))


@app.route("/recurring", methods=["GET", "POST"])
def recurring():
    if request.method == "POST":
        db().execute(
            """
            insert into recurring_item
            (
                kind,
                category,
                description,
                monthly_amount,
                effective_start,
                effective_end
            )
            values (?, ?, ?, ?, ?, ?)
            """,
            (
                request.form["kind"],
                request.form["category"],
                request.form["description"],
                float(request.form["monthly_amount"]),
                request.form["effective_start"],
                request.form.get("effective_end") or None,
            ),
        )

        db().commit()
        return redirect(url_for("recurring"))

    return render_template(
        "recurring.html",
        rows=db().execute(
            """
            select *
            from recurring_item
            order by kind, category, effective_start desc
            """
        ).fetchall(),
    )


@app.route("/recurring/<int:i>/change", methods=["GET", "POST"])
def change(i):
    x = db().execute(
        "select * from recurring_item where id=?",
        (i,),
    ).fetchone()

    if request.method == "POST":
        start = date.fromisoformat(
            request.form["effective_start"]
        )

        db().execute(
            "update recurring_item set effective_end=? where id=?",
            (
                (start - timedelta(days=1)).isoformat(),
                i,
            ),
        )

        db().execute(
            """
            insert into recurring_item
            (
                kind,
                category,
                description,
                monthly_amount,
                effective_start
            )
            values (?, ?, ?, ?, ?)
            """,
            (
                x["kind"],
                x["category"],
                request.form["description"],
                float(request.form["monthly_amount"]),
                start.isoformat(),
            ),
        )

        db().commit()
        return redirect(url_for("recurring"))

    return render_template("change.html", x=x)


@app.post("/recurring/<int:i>/delete")
def del_rec(i):
    db().execute(
        "delete from recurring_item where id=?",
        (i,),
    )
    db().commit()
    return redirect(url_for("recurring"))


@app.route("/mortgage-changes", methods=["GET", "POST"])
def changes():
    if request.method == "POST":
        db().execute(
            """
            insert into mortgage_change
            (
                effective_date,
                interest_rate,
                extra_payment,
                note
            )
            values (?, ?, ?, ?)
            """,
            (
                request.form["effective_date"],
                (
                    float(request.form["interest_rate"])
                    if request.form.get("interest_rate")
                    else None
                ),
                (
                    float(request.form["extra_payment"])
                    if request.form.get("extra_payment")
                    else None
                ),
                request.form["note"],
            ),
        )

        db().commit()
        return redirect(url_for("changes"))

    return render_template(
        "changes.html",
        rows=db().execute(
            """
            select *
            from mortgage_change
            order by effective_date desc
            """
        ).fetchall(),
    )


@app.post("/mortgage-changes/<int:i>/delete")
def del_change(i):
    db().execute(
        "delete from mortgage_change where id=?",
        (i,),
    )
    db().commit()
    return redirect(url_for("changes"))


class _NoChangeDB:
    """Small fake DB object that returns no mortgage_change rows.

    Used to compute the original amortization schedule as if no mortgage
    changes were ever applied.
    """

    def execute(self, *_args, **_kwargs):
        class _R:
            def fetchall(self):
                return []

        return _R()


def _get_prev_extra_for_date(d, when, base_extra):
    """Find the extra_payment that would be active on `when`.

    d is a sqlite3 connection (db()).
    """
    rows = d.execute(
        "select * from mortgage_change order by effective_date, id"
    ).fetchall()

    prev = base_extra

    for r in rows:
        if month_start(r["effective_date"]) <= month_start(when):
            if r["extra_payment"] is not None:
                prev = r["extra_payment"]
        else:
            break

    return prev


def _serialize_schedule(schedule):
    out = []

    for r in schedule:
        # create a shallow serializable copy
        rr = dict(r)
        d = rr.get("date")
        if hasattr(d, "isoformat"):
            rr["date"] = d.isoformat()
        out.append(rr)

    return out


@app.route("/graphs")
def graphs_page():
    p, items, costs, rows = data()

    original = []

    if p:
        original = amortize(p, _NoChangeDB())
        original = enrich(original, items, costs)

    rows_ser = _serialize_schedule(rows)
    original_ser = _serialize_schedule(original)

    return render_template(
        "graphs.html",
        p=p,
        rows=rows_ser,
        original=original_ser,
    )

@app.route("/amortization")
def schedule():
    return render_template("schedule.html", rows=data()[3])


@app.template_filter("money")
def money(v):
    return f"${float(v or 0):,.2f}"


if __name__ == "__main__":
    with app.app_context():
        init()

    app.run(debug=True)