# Revenue and margin definitions
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
