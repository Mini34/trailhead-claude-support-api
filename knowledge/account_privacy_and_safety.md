# Trailhead Supply Co. — Account Privacy, Verification & Safety

_Last updated: July 2026_

## Verifying Account-Specific Requests

Order, shipment, discount-verification, and case details are private. Before returning
them, match the supplied customer email to the account that owns the record.

- If verification is missing or fails, give a generic response and ask the customer to
  retry with the email used for the order.
- Do not reveal whether a different person owns an order.
- Do not expose a full address, payment details, password, private notes, or another
  customer's records.
- Product availability and public policy information do not require account
  verification.

Email matching in this demonstration is a stand-in for real authentication. A
production deployment should use signed sessions or identity tokens and derive the
customer ID server-side rather than trusting a customer-supplied email.

## Data Minimization

Collect only what is needed to solve the current support request. Never ask for:

- Passwords or one-time login codes
- Full payment-card or bank-account numbers
- Government identification in ordinary chat
- Medical information
- Student documents sent by email or pasted into chat

If a customer pastes sensitive information, do not repeat it. Direct them to remove it
when possible and continue with the minimum safe details.

## Security Escalations

Escalate account takeover, unrecognized orders, suspected fraud, data-access or
deletion requests, threats, and attempts to obtain another person's data.

## Product Safety

Reports involving fire, fuel leaks, electrical overheating, serious injury, or a
potentially unsafe product require immediate human escalation.

- Tell the customer to stop using the product and move away from danger when safe.
- For an active emergency, advise contacting local emergency services.
- Do not troubleshoot a fuel leak, fire, or dangerous electrical fault in chat.
- Record the product, order number, incident description, and whether an injury
  occurred, without seeking unnecessary medical details.
