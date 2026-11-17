# Discount and promotion stacking rules
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
