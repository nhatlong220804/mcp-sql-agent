"""Build a demo database and index a small document set.

    python scripts/seed_demo.py --db demo.db --docs docs/

Creates four tables with deterministic fake data and writes eight policy documents
into `docs/`, then chunks and indexes them into the same SQLite file.
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_sql_agent.rag import store  # noqa: E402

SCHEMA = """
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id  INTEGER PRIMARY KEY,
    full_name    TEXT NOT NULL,
    email        TEXT NOT NULL UNIQUE,
    city         TEXT NOT NULL,
    tier         TEXT NOT NULL CHECK (tier IN ('standard','silver','gold')),
    created_at   TEXT NOT NULL
);

CREATE TABLE products (
    product_id   INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT NOT NULL,
    list_price   REAL NOT NULL,
    unit_cost    REAL NOT NULL
);

CREATE TABLE orders (
    order_id     INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date   TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('delivered','shipped','cancelled','returned')),
    channel      TEXT NOT NULL CHECK (channel IN ('web','store','phone'))
);

CREATE TABLE order_items (
    order_id     INTEGER NOT NULL REFERENCES orders(order_id),
    product_id   INTEGER NOT NULL REFERENCES products(product_id),
    quantity     INTEGER NOT NULL,
    unit_price   REAL NOT NULL,
    discount_pct REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (order_id, product_id)
);

CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_items_product ON order_items(product_id);
"""

CITIES = ["Ho Chi Minh", "Ha Noi", "Da Nang", "Can Tho", "Hai Phong", "Hue"]
CATEGORIES = ["outerwear", "shirts", "trousers", "footwear", "accessories"]
TIERS = ["standard", "standard", "standard", "silver", "silver", "gold"]
FIRST = ["An", "Binh", "Chi", "Dung", "Giang", "Hoa", "Hung", "Lan", "Linh", "Minh",
         "Nam", "Nga", "Phuc", "Quang", "Son", "Thao", "Trang", "Tuan", "Vy", "Yen"]
LAST = ["Nguyen", "Tran", "Le", "Pham", "Hoang", "Vu", "Dang", "Bui", "Do", "Ho"]


def build_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    rng = random.Random(20261117)

    customers = []
    for cid in range(1, 501):
        name = f"{rng.choice(LAST)} {rng.choice(FIRST)}"
        email = f"user{cid}@example.com"
        city = rng.choice(CITIES)
        tier = rng.choice(TIERS)
        created = date(2024, 1, 1) + timedelta(days=rng.randint(0, 900))
        customers.append((cid, name, email, city, tier, created.isoformat()))
    conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?)", customers)

    products = []
    for pid in range(1, 121):
        category = rng.choice(CATEGORIES)
        price = round(rng.uniform(180_000, 2_400_000), -3)
        cost = round(price * rng.uniform(0.45, 0.72), -3)
        products.append((pid, f"{category[:-1].title()} model {pid:03d}", category, price, cost))
    conn.executemany("INSERT INTO products VALUES (?,?,?,?,?)", products)

    orders, items = [], []
    for oid in range(1, 3001):
        customer = rng.randint(1, 500)
        placed = date(2025, 1, 1) + timedelta(days=rng.randint(0, 660))
        status = rng.choices(
            ["delivered", "shipped", "cancelled", "returned"],
            weights=[78, 9, 7, 6],
        )[0]
        channel = rng.choices(["web", "store", "phone"], weights=[62, 31, 7])[0]
        orders.append((oid, customer, placed.isoformat(), status, channel))

        for pid in rng.sample(range(1, 121), rng.randint(1, 4)):
            qty = rng.randint(1, 3)
            price = next(p[3] for p in products if p[0] == pid)
            discount = rng.choice([0, 0, 0, 5, 10, 15])
            items.append((oid, pid, qty, price, discount))
    conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", orders)
    conn.executemany("INSERT INTO order_items VALUES (?,?,?,?,?)", items)
    conn.commit()
    print(f"customers={len(customers)} products={len(products)} "
          f"orders={len(orders)} items={len(items)}")


DOCS = {
    "return-policy": (
        "Return and refund policy",
        """
Customers may return unused items within 30 days of delivery. The clock starts on
the delivery timestamp recorded by the courier, not on the order date, so an order
that sits in transit for a week still gets the full 30 days.

Items must be in original packaging with tags attached. Footwear must be tried
indoors only. Scuffed soles, creased uppers or missing shoeboxes make the item
non-resellable and the return will be rejected at inspection. Rejection is not
automatic at the counter; the store logs the condition and a specialist decides
within two business days.

Refunds are issued to the original payment method. Card refunds settle in three to
five business days depending on the issuing bank. Cash refunds at store are
immediate. Bank transfer refunds require the account number to match the name on the
order, and finance verifies this before releasing.

A returned order carries a 20,000 VND handling fee unless the return is caused by a
defect, a wrong item, or a courier error. Defective returns are always free and are
flagged so the buying team sees the failure rate per supplier.

Items bought during a clearance event are final sale. Clearance orders show a red
banner on the confirmation page and the order status reads clearance. They cannot be
returned for a refund but can be exchanged for size within seven days, once.

Exchange for size is allowed once per order and does not incur the handling fee if
the customer brings the item to a store. Exchange by post does incur the fee because
the return leg costs the same as a fresh shipment.

Orders paid partly with a voucher refund the cash portion first and reissue the
voucher with the original expiry date. Vouchers are never extended, including when
the return was our fault, and support is expected to offer a goodwill voucher
instead of arguing about the expiry.

Partial returns recalculate the order total. If the discount that applied to the
original basket no longer qualifies after the partial return, the refund is reduced
by the difference. This surprises customers, so the refund confirmation screen spells
out the calculation line by line.
""",
    ),
    "shipping-sla": (
        "Shipping and delivery service levels",
        """
Standard delivery inside Ho Chi Minh City takes one to two business days. Other
provinces take three to five business days. Orders placed after 16:00 are processed
the next business day, and orders placed on Saturday are processed on Monday.

Express delivery is available in Ho Chi Minh and Ha Noi only, with a same-day cutoff
at 11:00. The express surcharge is 45,000 VND flat regardless of basket size. Express
is not available for oversized items, which are flagged with a shipping class on the
product record.

Free standard shipping applies to orders above 500,000 VND after discount. Orders
below that threshold carry a 30,000 VND shipping fee. Because the threshold is
checked after discount, a 10 percent code on a 520,000 VND basket drops it under the
line and adds the fee back. The cart recalculates and shows the warning before the
customer pays.

Orders that miss the promised delivery date by more than 48 hours are eligible for a
shipping refund on request. The customer must contact support within seven days of
the delivery window ending. The refund is issued as credit, not cash, unless the
order was prepaid by card, in which case it goes back to the card.

Delivery partners are GHTK for the north and GHN for the south. Both hand over
tracking numbers at pickup, and tracking events are pushed to the order page within
15 minutes of the scan. A tracking number with no movement for 72 hours triggers an
automatic investigation ticket with the carrier.

Failed delivery attempts are retried twice. After the second failure the parcel
returns to the warehouse and the order is marked return-to-sender. The customer is
refunded minus the outbound shipping cost, and the item goes back to sellable stock
only after inspection.

Address changes are accepted until the parcel is picked up. After pickup the customer
must work with the courier directly, and support only confirms the order details on
request.

Bulk orders above 20 items ship on a pallet through a freight partner and follow a
separate schedule quoted at order confirmation. These are excluded from the standard
SLA and from the shipping refund policy.
""",
    ),
    "discount-rules": (
        "Discount and promotion stacking rules",
        """
Only one percentage discount code may be applied per order. A percentage code and a
fixed-amount voucher cannot be combined. The cart rejects the second code with a
message naming the first one, rather than silently dropping it.

Tier discounts are applied automatically and do not stack with promotional codes.
Gold members receive 10 percent off, silver members 5 percent. When a promotional
code gives more than the tier discount, the promotional code wins and the tier
discount is suppressed for that order. When the code gives less, the tier discount
applies and the code is returned to the customer's wallet.

Discounts apply to the item subtotal, never to shipping fees. Shipping is calculated
after the discount is applied, so a deep discount can push an order back under the
free shipping threshold. This interaction causes more support tickets than any other
pricing rule and the cart warns about it explicitly.

Staff purchases are limited to 3 items per month at 25 percent off and are excluded
from all other promotions. Staff accounts are flagged in the customer table and the
limit resets on the first of the month. Exceeding the limit requires a manager
override recorded against the order.

Promotional codes expire at 23:59 on the stated date in Vietnam time. Expired codes
are rejected without exception. There is no grace period, and support cannot extend
an expiry even for a customer whose checkout failed, because the code table is
read-only to support staff.

Codes are single use per customer account. A cancelled order returns the code to the
wallet within one hour. A fully returned order does not, and the code stays spent.
This asymmetry is intentional and documented so support stops promising otherwise.

Percentage codes cap at 50 percent. A code configured above that is rejected at
creation time by the promotion admin screen.

Stacking with loyalty points is allowed. Points redeem at a fixed 1 point equals
1,000 VND and apply after all other discounts, which means points can absorb part of
the shipping fee when the item subtotal drops to zero.
""",
    ),
    "customer-tiers": (
        "Customer tier definitions",
        """
Tier is recalculated on the first day of each month from rolling twelve month spend.
The job runs at 02:00 and finishes before the first marketing email of the day, so a
customer who drops a tier does not receive a gold offer by mistake.

Standard covers customers below 5,000,000 VND of net spend. Silver covers 5,000,000
to 20,000,000 VND. Gold is above 20,000,000 VND. Net spend means the sum of order
totals after discount, excluding cancelled and fully returned orders. Partially
returned orders count at their recalculated value.

Returned items reduce net spend in the month the refund is processed, which can drop
a customer back a tier. Tier changes are not applied retroactively. A customer who
was gold at the time of an order keeps the discount they already received.

Gold members get 10 percent automatic discount, free express shipping upgrade, and
early access to seasonal drops 48 hours before public release. Early access applies
to web only; stores release stock on the public date regardless of tier.

Silver members get 5 percent automatic discount and free standard shipping at any
basket size. The free shipping benefit does not upgrade to express.

New customers start at standard regardless of their first order value. A single large
first order does promote the account at the next monthly run, which is why some
customers see a tier jump in their second month.

Tier is per person, not per household. Shared phone numbers and duplicate accounts
are merged by the support team on request, and the merge keeps the higher tier until
the next recalculation.

Wholesale accounts are excluded from the retail tier programme entirely. Their
discounts come from the wholesale agreement and appear in a separate field on the
invoice so reporting does not double count them.

Accounts with a chargeback in the last six months are held at standard while the
dispute is open. Once resolved in the customer's favour the tier is restored on the
next run.
""",
    ),
    "data-dictionary": (
        "Revenue and margin definitions",
        """
Gross revenue is the sum of quantity multiplied by unit price before discount, for
orders whose status is delivered, shipped or returned. Cancelled orders are excluded
entirely and do not appear in any revenue figure.

Net revenue subtracts the discount amount from gross revenue. This is the figure used
in dashboards and in tier calculation. When someone says revenue without qualifying
it, they mean net revenue.

Realised revenue counts only orders with status delivered. Use this when reporting
cash actually collected. The gap between net and realised revenue is the value of
orders still in transit, which is usually three to five days of sales.

Gross margin is realised revenue minus cost of goods sold, divided by realised
revenue. Cost of goods comes from products.unit_cost at the time of sale and does not
change retroactively. A later cost update does not rewrite historical margin, which
is why the buying team cannot fix a mis-entered cost after the month closes.

A returned order keeps its item rows but is excluded from realised revenue. It still
appears in gross revenue so the return rate stays visible. The standard return rate
report divides returned orders by delivered orders in the same period, not by all
orders, because cancelled orders never had a chance to be returned.

Average order value divides net revenue by delivered order count. Partially returned
orders count once at their recalculated value, so AOV moves slightly when a partial
return lands even though no new order was placed.

Customer counts are distinct customer_id values in the period. Repeat rate is the
share of those customers with a prior delivered order in the preceding twelve months.

Attribution uses the channel field on the order, not the marketing source. A web
order picked up in store is still a web order. Marketing attribution lives in a
separate table and is joined only in campaign reporting.
""",
    ),
    "warranty": (
        "Product warranty coverage",
        """
All footwear carries a 90 day warranty against sole separation and stitching failure.
Normal wear is not covered, and the intake team uses a photo checklist to separate the
two. Heel wear from walking is normal wear. A sole detaching from the upper at the
toe is a defect.

Outerwear carries a 180 day warranty on zips and buttons. Leather goods are excluded
from warranty once exposed to water damage, which is visible as stiffening and colour
shift along the seams. The exclusion is stated on the care card that ships with every
leather item.

Warranty claims require the original order number and photos of the fault. Claims
without photos are held until the customer provides them. Support should not open a
claim on a verbal description alone, because the repair partner rejects those and the
customer ends up waiting twice.

Approved claims are repaired first, replaced second, refunded third. Repair turnaround
is ten to fifteen business days including shipping both ways. If the repair partner
quotes longer than twenty days, the claim converts to a replacement automatically.

Warranty does not cover items bought from third-party resellers. Resale purchases are
identified by the absence of an order record and are refused at intake. Staff should
explain that the item may still be genuine but that warranty follows the original
sale, not the item.

Warranty is tied to the order, not the customer. A gifted item keeps its warranty when
the recipient brings it in, as long as they can name the order or the buyer's phone
number.

Cosmetic damage from a single incident, such as a tear from catching a zip on a door,
is not covered. Repair is offered at cost in those cases and the price is quoted
before any work starts.

Warranty replacements reset the clock. The replacement item carries a fresh 90 or 180
day period from the replacement date, recorded on the original order as a linked
order row.
""",
    ),
    "b2b-payment-terms": (
        "Wholesale and B2B payment terms",
        """
Wholesale accounts require a signed agreement and a minimum opening order of
50,000,000 VND. The agreement covers pricing bands, return limits and the dispute
process. No wholesale order is accepted before the agreement is countersigned by
finance.

Payment terms are net 30 from invoice date for accounts with six months of clean
history. New accounts start on prepayment or net 7 at the discretion of finance.
Clean history means no invoice more than five days late in the trailing six months.

Overdue balances above 10,000,000 VND freeze new orders automatically. A first
reminder goes out at day 35, a second at day 45, and the account moves to collections
at day 60. The freeze lifts automatically once the balance clears, without waiting for
a manual unlock.

Wholesale pricing carries a 35 to 45 percent discount off list depending on volume
band. Bands are set quarterly from the previous quarter's volume, so a strong quarter
lowers prices for the next one rather than the current one. Wholesale orders are
excluded from retail promotions and tier discounts.

Returns on wholesale are accepted only for manufacturing defects and only above a
2 percent defect rate on the shipped batch. Below that threshold the retailer absorbs
the loss. This is the clause that gets argued about most, so the agreement spells out
how a batch is defined: one shipment, one invoice.

Partial shipments are invoiced separately and each invoice runs its own net 30 clock.
A delayed line does not hold up payment on the lines already delivered.

Price protection runs 30 days. If list price drops within 30 days of an invoice,
finance issues a credit note for the difference on unsold units, verified by the
retailer's stock report.

Settlement currency is VND. Foreign accounts settle in USD at the State Bank rate on
the invoice date, and the rate is printed on the invoice so there is no argument at
payment time.
""",
    ),
    "complaint-escalation": (
        "Complaint handling and escalation",
        """
First response to any complaint is within four business hours during weekdays. On
weekends the target is twelve hours. The clock starts when the message lands in the
support inbox, not when an agent opens it.

A complaint escalates to a team lead when the customer mentions a refund above
2,000,000 VND, a legal threat, or a repeat contact on the same issue. Repeat means the
same order and the same underlying problem, not a new question about the same order.

Escalation to the customer experience manager happens when the complaint involves a
delivery failure that has already been re-escalated once, or when the customer has
contacted support three or more times on the same order. Agents should escalate on the
third contact even if they believe they can resolve it, because the pattern itself is
the signal.

Every escalation requires a written summary in the ticket: order id, what was
promised, what happened, and what the customer is asking for. Summaries without those
four fields are sent back by the manager, which wastes a day.

Compensation authority sits with the team lead up to 500,000 VND in vouchers, and
with the manager above that. Refunds above 5,000,000 VND need finance sign-off
regardless of who approves the customer relationship. Cash refunds above 500,000 VND
are always issued to the original payment method, never as cash at the counter.

Agents should not promise a resolution timeline they cannot control. If the courier is
investigating, say that and give the investigation window, rather than a resolution
date.

Social media complaints follow the same ladder but with a two hour first response
target. The social team owns the public reply and support owns the resolution, and
they coordinate in the ticket so the public thread does not contradict the private
resolution.

Complaints involving a data or privacy concern go straight to the manager and the
legal team, bypassing the normal ladder entirely. This is the only category with no
agent discretion.
""",
    ),
}


def write_docs(docs_dir: Path) -> dict[str, Path]:
    docs_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for doc_id, (title, body) in DOCS.items():
        path = docs_dir / f"{doc_id}.md"
        path.write_text(f"# {title}\n{body.strip()}\n", encoding="utf-8")
        written[doc_id] = path
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="demo.db")
    parser.add_argument("--docs", default="docs")
    parser.add_argument("--chunk-size", type=int, default=512)
    parser.add_argument("--overlap", type=int, default=64)
    args = parser.parse_args()

    db_path = Path(args.db)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    build_tables(conn)

    paths = write_docs(Path(args.docs))
    total_chunks = 0
    for doc_id, path in sorted(paths.items()):
        text = path.read_text(encoding="utf-8")
        title = DOCS[doc_id][0]
        n = store.add_document(
            conn,
            doc_id=doc_id,
            title=title,
            text=text,
            source=str(path),
            chunk_size=args.chunk_size,
            overlap=args.overlap,
        )
        total_chunks += n
        print(f"indexed {doc_id}: {n} chunks")

    conn.close()
    print(f"\ndatabase: {db_path.resolve()}")
    print(f"documents: {len(paths)}  chunks: {total_chunks}")


if __name__ == "__main__":
    main()
