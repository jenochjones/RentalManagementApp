from datetime import date
from decimal import Decimal, ROUND_HALF_UP, getcontext


# Extra precision is important for 30-year mortgage calculations.
getcontext().prec = 40

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
ONE = Decimal("1")


def money(value):
    """Convert a value to a currency-safe Decimal."""
    return Decimal(str(value or 0)).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )


def month_start(value):
    if isinstance(value, str):
        value = date.fromisoformat(value)

    return value.replace(day=1)


def add_month(value):
    return date(
        value.year + (value.month == 12),
        1 if value.month == 12 else value.month + 1,
        1,
    )


def payment(principal, annual_rate, num_payments):
    """
    Return the full-precision monthly mortgage payment.

    annual_rate should be entered as a percentage:
    6.5 = 6.5%

    Do not round here. Rounding the payment before using it in the
    amortization calculation can accumulate several dollars of error.
    """
    principal = Decimal(str(principal))
    annual_rate = Decimal(str(annual_rate))
    num_payments = int(num_payments)

    if num_payments <= 0:
        raise ValueError(
            "Number of payments must be greater than zero."
        )

    monthly_rate = annual_rate / Decimal("1200")

    if monthly_rate == 0:
        return principal / Decimal(num_payments)

    factor = (ONE + monthly_rate) ** num_payments

    return (
        principal
        * monthly_rate
        * factor
        / (factor - ONE)
    )


def amortize(prop, db):
    # Convert sqlite3.Row to dict so .get() works.
    prop = dict(prop)

    principal = money(prop["original_loan"])
    rate = Decimal(str(prop["interest_rate"] or 0))
    extra = money(prop.get("extra_payment") or 0)

    term_months = int(prop["term_years"]) * 12

    if principal <= ZERO:
        return []

    # Keep the calculated payment at full precision.
    regular_payment_exact = payment(
        principal,
        rate,
        term_months,
    )

    when = month_start(prop["loan_start_date"])

    #
    # IMPORTANT:
    # Replace "mortgage_id" and prop["id"] if your actual column
    # names are different. Without this WHERE clause, changes for
    # other mortgages can affect this schedule.
    #
    changes = db.execute(
        """
        SELECT *
        FROM mortgage_change
        ORDER BY effective_date, id
        """
    ).fetchall()

    change_index = 0
    schedule = []

    for payment_number in range(1, term_months + 1):
        rate_changed = False

        #
        # Apply changes effective during this month.
        #
        while (
            change_index < len(changes)
            and month_start(
                changes[change_index]["effective_date"]
            ) <= when
        ):
            change = changes[change_index]

            if change["interest_rate"] is not None:
                new_rate = Decimal(
                    str(change["interest_rate"])
                )

                if new_rate != rate:
                    rate = new_rate
                    rate_changed = True

            if change["extra_payment"] is not None:
                extra = money(change["extra_payment"])

            change_index += 1

        #
        # Re-amortize the current balance when the rate changes.
        #
        if rate_changed:
            remaining_months = (
                term_months - payment_number + 1
            )

            regular_payment_exact = payment(
                principal,
                rate,
                remaining_months,
            )

        monthly_rate = rate / Decimal("1200")

        #
        # Mortgage interest is posted in cents each month.
        #
        interest = money(
            principal * monthly_rate
        )

        #
        # Round the customer-facing regular payment only when the
        # payment is actually made.
        #
        regular_payment = money(
            regular_payment_exact
        )

        scheduled_payment = money(
            regular_payment + extra
        )

        payoff_amount = money(
            principal + interest
        )

        is_last_scheduled_payment = (
            payment_number == term_months
        )

        #
        # The final scheduled payment must equal the exact payoff
        # amount. This clears any cumulative cent-rounding remainder.
        #
        if is_last_scheduled_payment:
            actual_payment = payoff_amount
        else:
            actual_payment = min(
                scheduled_payment,
                payoff_amount,
            )

        actual_payment = money(actual_payment)

        principal_paid = money(
            actual_payment - interest
        )

        if principal_paid <= ZERO:
            raise ValueError(
                "Payment does not cover accrued interest."
            )

        #
        # Never pay more principal than remains outstanding.
        #
        principal_paid = min(
            principal_paid,
            principal,
        )

        principal_paid = money(principal_paid)
        ending_balance = money(
            principal - principal_paid
        )

        #
        # Reconcile a sub-cent residue caused by Decimal operations.
        #
        if abs(ending_balance) < CENT:
            principal_paid = money(
                principal_paid + ending_balance
            )
            actual_payment = money(
                interest + principal_paid
            )
            ending_balance = ZERO

        regular_component = min(
            regular_payment,
            actual_payment,
        )

        actual_extra = money(
            max(
                ZERO,
                actual_payment - regular_component,
            )
        )

        schedule.append(
            {
                "number": payment_number,
                "date": when,
                "rate": float(rate),
                "payment": float(actual_payment),
                "regular_payment": float(
                    money(regular_component)
                ),
                "extra": float(actual_extra),
                "principal": float(principal_paid),
                "interest": float(interest),
                "balance": float(ending_balance),
            }
        )

        principal = ending_balance

        if principal == ZERO:
            break

        when = add_month(when)

    return schedule