# Online Order System — Requirements

Customers browse a product catalog and place orders through a web storefront.
When a customer submits an order, the system must validate stock levels before
accepting it. Accepted orders are persisted, and a confirmation email is sent
to the customer asynchronously.

Payment is processed through the external Stripe gateway; the system itself
must never store card numbers. Order history must be retrievable by the
customer at any time.

The catalog and order data must be stored in PostgreSQL. Email delivery must
not block order acceptance: use a message queue between order acceptance and
notification. The storefront must respond to catalog searches within 500 ms
at the 95th percentile.
