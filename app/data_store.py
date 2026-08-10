from __future__ import annotations

import csv
import re
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path
from typing import Any

TOKEN_RE = re.compile(r"[a-z0-9]+")


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Required data file not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _as_bool(value: str | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _as_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _money(value: float) -> float:
    return round(value + 1e-9, 2)


class DataStore:
    """Read-only business-data access with account ownership checks."""

    REQUIRED_TABLES = (
        "customers",
        "products",
        "orders",
        "order_items",
        "inventory",
        "shipments",
        "discount_programs",
        "customer_eligibility",
        "order_adjustments",
        "support_cases",
    )

    def __init__(self, directory: Path, today: date | None = None):
        self.directory = Path(directory)
        self.today = today or date.today()
        tables = {
            name: _read_csv(self.directory / f"{name}.csv")
            for name in self.REQUIRED_TABLES
        }
        self.customers = tables["customers"]
        self.products = tables["products"]
        self.orders = tables["orders"]
        self.order_items = tables["order_items"]
        self.inventory = tables["inventory"]
        self.shipments = tables["shipments"]
        self.discount_programs = tables["discount_programs"]
        self.customer_eligibility = tables["customer_eligibility"]
        self.order_adjustments = tables["order_adjustments"]
        self.support_cases = tables["support_cases"]

        self._customers_by_email = {
            row["email"].strip().lower(): row for row in self.customers
        }
        self._products_by_id = {row["product_id"]: row for row in self.products}
        self._orders_by_id = {row["order_id"]: row for row in self.orders}
        self._shipments_by_order = {row["order_id"]: row for row in self.shipments}
        self._inventory_by_product = {row["product_id"]: row for row in self.inventory}
        self._programs_by_code = {
            row["program_code"].upper(): row for row in self.discount_programs
        }
        self._validate_references()

    def _validate_references(self) -> None:
        customer_ids = {row["customer_id"] for row in self.customers}
        product_ids = {row["product_id"] for row in self.products}
        order_ids = {row["order_id"] for row in self.orders}
        shipment_order_ids = {row["order_id"] for row in self.shipments}

        errors: list[str] = []
        if len(customer_ids) != len(self.customers):
            errors.append("customers.csv contains duplicate customer_id values")
        if len(product_ids) != len(self.products):
            errors.append("products.csv contains duplicate product_id values")
        if len(order_ids) != len(self.orders):
            errors.append("orders.csv contains duplicate order_id values")
        if shipment_order_ids != order_ids:
            errors.append("shipments.csv must contain exactly one row for every order")
        if {row["product_id"] for row in self.inventory} != product_ids:
            errors.append("inventory.csv must contain every product")

        for order in self.orders:
            if order["customer_id"] not in customer_ids:
                errors.append(
                    f"order {order['order_id']} references an unknown customer"
                )
        for item in self.order_items:
            if item["order_id"] not in order_ids:
                errors.append(f"order item references unknown order {item['order_id']}")
            if item["product_id"] not in product_ids:
                errors.append(
                    f"order item references unknown product {item['product_id']}"
                )
        for row in self.customer_eligibility:
            if row["customer_id"] not in customer_ids:
                errors.append(
                    f"eligibility row references unknown customer {row['customer_id']}"
                )
            if row["program_code"].upper() not in self._programs_by_code:
                errors.append(
                    f"eligibility row references unknown program {row['program_code']}"
                )
        for row in self.order_adjustments:
            if row["order_id"] not in order_ids:
                errors.append(f"adjustment references unknown order {row['order_id']}")
        for row in self.support_cases:
            if row["customer_id"] not in customer_ids:
                errors.append(f"case {row['case_id']} references an unknown customer")
            if row["order_id"] and row["order_id"] not in order_ids:
                errors.append(
                    f"case {row['case_id']} references unknown order {row['order_id']}"
                )

        if errors:
            raise ValueError("Invalid business data: " + "; ".join(errors[:10]))

    @property
    def stats(self) -> dict[str, int]:
        return {
            "customers": len(self.customers),
            "products": len(self.products),
            "orders": len(self.orders),
            "shipments": len(self.shipments),
            "support_cases": len(self.support_cases),
            "discount_programs": len(self.discount_programs),
        }

    def _verified_customer(self, customer_email: str | None) -> dict | None:
        if not customer_email:
            return None
        return self._customers_by_email.get(customer_email.strip().lower())

    @staticmethod
    def _verification_error() -> dict:
        return {
            "status": "verification_required",
            "message": (
                "The account and order could not be verified. Ask for the email used "
                "on the order, without revealing whether another account owns it."
            ),
        }

    def lookup_order(self, order_id: str | int, customer_email: str | None) -> dict:
        customer = self._verified_customer(customer_email)
        order = self._orders_by_id.get(str(order_id).strip())
        if not customer or not order or order["customer_id"] != customer["customer_id"]:
            return self._verification_error()

        items: list[dict[str, Any]] = []
        for row in self.order_items:
            if row["order_id"] != order["order_id"]:
                continue
            product = self._products_by_id.get(row["product_id"], {})
            items.append(
                {
                    "product_id": row["product_id"],
                    "name": product.get("name"),
                    "category": product.get("category"),
                    "quantity": int(row["quantity"]),
                    "unit_price": float(row["unit_price"]),
                    "is_final_sale": _as_bool(product.get("is_final_sale")),
                    "return_window_days": int(product.get("return_window_days") or 0),
                    "warranty_months": int(product.get("warranty_months") or 0),
                }
            )

        adjustments = [
            {
                "type": row["adjustment_type"],
                "program_code": row["program_code"] or None,
                "amount": float(row["amount"]),
                "description": row["description"],
            }
            for row in self.order_adjustments
            if row["order_id"] == order["order_id"]
        ]
        shipment = self._shipments_by_order.get(order["order_id"])
        return {
            "status": "verified",
            "customer": {
                "first_name": customer["name"].split()[0],
                "trail_club_member": _as_bool(customer["trail_club_member"]),
            },
            "order": {
                "order_id": order["order_id"],
                "order_date": order["order_date"],
                "status": order["status"],
                "shipping_method": order["shipping_method"],
                "subtotal": float(order["subtotal"]),
                "shipping_cost": float(order["shipping_cost"]),
                "total": float(order["total"]),
                "items": items,
                "adjustments": adjustments,
            },
            "shipment": (
                {
                    "shipment_id": shipment["shipment_id"],
                    "carrier": shipment["carrier"] or None,
                    "tracking_number": shipment["tracking_number"] or None,
                    "status": shipment["status"],
                    "shipped_date": shipment["shipped_date"] or None,
                    "estimated_delivery": shipment["estimated_delivery"] or None,
                    "delivered_date": shipment["delivered_date"] or None,
                }
                if shipment
                else None
            ),
        }

    def list_customer_orders(self, customer_email: str | None, limit: int = 5) -> dict:
        customer = self._verified_customer(customer_email)
        if not customer:
            return self._verification_error()
        rows = [
            row for row in self.orders if row["customer_id"] == customer["customer_id"]
        ]
        rows.sort(
            key=lambda row: (row["order_date"], int(row["order_id"])), reverse=True
        )
        return {
            "status": "verified",
            "orders": [
                {
                    "order_id": row["order_id"],
                    "order_date": row["order_date"],
                    "status": row["status"],
                    "total": float(row["total"]),
                }
                for row in rows[: max(1, min(limit, 10))]
            ],
        }

    @staticmethod
    def _business_days_between(start: date, end: date) -> int:
        if end <= start:
            return 0
        return sum(
            1
            for offset in range(1, (end - start).days + 1)
            if (start + timedelta(days=offset)).weekday() < 5
        )

    def get_delivery_estimate(
        self, order_id: str | int, customer_email: str | None
    ) -> dict:
        order_result = self.lookup_order(order_id, customer_email)
        if order_result.get("status") != "verified":
            return order_result

        order = order_result["order"]
        shipment = order_result.get("shipment") or {}
        estimated = _as_date(shipment.get("estimated_delivery"))
        delivered = _as_date(shipment.get("delivered_date"))
        shipment_status = shipment.get("status") or order["status"]
        response: dict[str, Any] = {
            "status": "verified",
            "order_id": order["order_id"],
            "order_status": order["status"],
            "shipment_status": shipment_status,
            "shipping_method": order["shipping_method"],
            "carrier": shipment.get("carrier"),
            "tracking_number": shipment.get("tracking_number"),
            "estimated_delivery": estimated.isoformat() if estimated else None,
            "delivered_date": delivered.isoformat() if delivered else None,
            "calculated_on": self.today.isoformat(),
        }

        if delivered:
            days_ago = max((self.today - delivered).days, 0)
            response.update(
                {
                    "timing": "delivered",
                    "days_since_delivery": days_ago,
                    "summary": (
                        f"Carrier records show delivery on {delivered.isoformat()}."
                    ),
                    "recommended_next_step": (
                        "If the package is missing, check the delivery location and "
                        "household members, then request a carrier investigation."
                    ),
                }
            )
            return response

        if estimated:
            calendar_days = (estimated - self.today).days
            response["calendar_days_until_estimate"] = calendar_days
            if calendar_days > 1:
                response["timing"] = "estimated_in_days"
                response["summary"] = (
                    f"Estimated delivery is in {calendar_days} calendar days, "
                    f"on {estimated.isoformat()}."
                )
            elif calendar_days == 1:
                response["timing"] = "estimated_tomorrow"
                response["summary"] = (
                    f"Estimated delivery is tomorrow, {estimated.isoformat()}."
                )
            elif calendar_days == 0:
                response["timing"] = "estimated_today"
                response["summary"] = "Estimated delivery is today."
            else:
                response["timing"] = "past_estimate"
                response["calendar_days_past_estimate"] = abs(calendar_days)
                response["business_days_past_estimate"] = self._business_days_between(
                    estimated, self.today
                )
                response["summary"] = (
                    f"The estimate of {estimated.isoformat()} has passed by "
                    f"{abs(calendar_days)} calendar days."
                )
        else:
            response["timing"] = "estimate_unavailable"
            response["summary"] = "No delivery estimate is available yet."

        shipped = _as_date(shipment.get("shipped_date"))
        if shipped:
            response["business_days_since_shipped"] = self._business_days_between(
                shipped, self.today
            )

        if shipment_status == "Processing":
            response["what_status_means"] = (
                "The order is being packed and does not have active tracking yet."
            )
            response["recommended_next_step"] = (
                "Wait for the shipping-confirmation email. A cancellation or address "
                "change can only be requested while the order remains Processing."
            )
        elif shipment_status == "Delayed":
            response["what_status_means"] = (
                "The carrier has reported an exception such as weather or an address issue."
            )
            response["recommended_next_step"] = (
                "Review tracking for the latest carrier scan. If there has been no "
                "movement for more than 5 business days, request a carrier investigation."
            )
        elif shipment_status == "Out for Delivery":
            response["what_status_means"] = (
                "The carrier says the package is on the vehicle for delivery today."
            )
            response["recommended_next_step"] = (
                "Monitor tracking through the end of the carrier's delivery day."
            )
        else:
            response["what_status_means"] = (
                "The package has left the warehouse and is moving through the carrier network."
            )
            response["recommended_next_step"] = (
                "Use the verified tracking number for the latest carrier scan."
            )
        return response

    def list_customer_cases(
        self, customer_email: str | None, include_resolved: bool = False
    ) -> dict:
        customer = self._verified_customer(customer_email)
        if not customer:
            return self._verification_error()
        rows = [
            row
            for row in self.support_cases
            if row["customer_id"] == customer["customer_id"]
            and (include_resolved or row["status"] != "resolved")
        ]
        rows.sort(key=lambda row: row["created_at"], reverse=True)
        return {
            "status": "verified",
            "cases": [
                {
                    "case_id": row["case_id"],
                    "order_id": row["order_id"] or None,
                    "category": row["category"],
                    "priority": row["priority"],
                    "status": row["status"],
                    "summary": row["summary"],
                    "resolution": row["resolution"] or None,
                    "created_at": row["created_at"],
                }
                for row in rows[:10]
            ],
        }

    def search_products(
        self, query: str, in_stock_only: bool = False, limit: int = 5
    ) -> dict:
        query_tokens = set(TOKEN_RE.findall(query.lower()))
        ranked: list[tuple[int, dict]] = []
        for product in self.products:
            inventory = self._inventory_by_product.get(product["product_id"], {})
            stock = int(inventory.get("units_in_stock") or 0)
            if in_stock_only and stock <= 0:
                continue
            haystack = " ".join(
                [product["product_id"], product["name"], product["category"]]
            ).lower()
            score = sum(1 for token in query_tokens if token in haystack)
            if query_tokens and score == 0:
                continue
            ranked.append((score, product))
        ranked.sort(key=lambda item: (-item[0], item[1]["name"]))
        return {
            "products": [
                {
                    "product_id": product["product_id"],
                    "name": product["name"],
                    "category": product["category"],
                    "price": float(product["price"]),
                    "units_in_stock": int(
                        self._inventory_by_product[product["product_id"]][
                            "units_in_stock"
                        ]
                    ),
                    "is_final_sale": _as_bool(product["is_final_sale"]),
                    "return_window_days": int(product["return_window_days"]),
                    "warranty_months": int(product["warranty_months"]),
                }
                for _, product in ranked[: max(1, min(limit, 10))]
            ]
        }

    def check_discount_eligibility(
        self,
        program_code: str,
        customer_email: str | None,
        items: list[dict] | None = None,
    ) -> dict:
        code = program_code.strip().upper()
        program = self._programs_by_code.get(code)
        if not program:
            return {
                "status": "unknown_program",
                "message": "No discount program with that code was found.",
            }

        rules = {
            "program_code": code,
            "name": program["name"],
            "percent_off": float(program["percent_off"]),
            "cooldown_days": int(program["cooldown_days"]),
            "exclude_final_sale": _as_bool(program["exclude_final_sale"]),
            "stackable_with_promos": _as_bool(program["stackable_with_promos"]),
            "stackable_with_free_shipping": _as_bool(
                program["stackable_with_free_shipping"]
            ),
            "notes": program["notes"],
        }
        customer = self._verified_customer(customer_email)
        if not customer:
            return {
                "status": "verification_required",
                "program": rules,
                "message": "Verify the customer's account before checking eligibility.",
            }

        eligibility = next(
            (
                row
                for row in self.customer_eligibility
                if row["customer_id"] == customer["customer_id"]
                and row["program_code"].upper() == code
            ),
            None,
        )
        if not eligibility or eligibility["verification_status"] != "verified":
            return {
                "status": "verification_required",
                "program": rules,
                "verification_status": (
                    eligibility["verification_status"] if eligibility else "unverified"
                ),
                "message": "The customer must complete or renew verification.",
            }

        expires = _as_date(eligibility["verification_expires"])
        if not expires or expires < self.today:
            return {
                "status": "verification_required",
                "program": rules,
                "verification_status": "expired",
                "verification_expires": expires.isoformat() if expires else None,
                "message": "The customer's verification has expired.",
            }

        last_used = _as_date(eligibility["last_used_date"])
        cooldown_days = int(program["cooldown_days"])
        next_eligible = last_used + timedelta(days=cooldown_days) if last_used else None
        if next_eligible and self.today < next_eligible:
            return {
                "status": "cooldown",
                "program": rules,
                "verification_status": "verified",
                "verification_expires": expires.isoformat(),
                "last_used_date": last_used.isoformat(),
                "next_eligible_date": next_eligible.isoformat(),
                "message": "Verification is valid, but the program is still in cooldown.",
            }

        result: dict[str, Any] = {
            "status": "eligible",
            "program": rules,
            "verification_status": "verified",
            "verification_expires": expires.isoformat(),
        }
        if not items:
            return result

        eligible_items: list[dict] = []
        excluded_items: list[dict] = []
        eligible_subtotal = 0.0
        for requested in items[:20]:
            product_id = str(requested.get("product_id", "")).strip().upper()
            try:
                quantity = max(1, min(int(requested.get("quantity", 1)), 20))
            except (TypeError, ValueError):
                quantity = 1
            product = self._products_by_id.get(product_id)
            if not product:
                excluded_items.append(
                    {"product_id": product_id, "reason": "product_not_found"}
                )
                continue
            line_total = float(product["price"]) * quantity
            if _as_bool(program["exclude_final_sale"]) and _as_bool(
                product["is_final_sale"]
            ):
                excluded_items.append(
                    {
                        "product_id": product_id,
                        "name": product["name"],
                        "reason": "final_sale_or_clearance",
                    }
                )
                continue
            eligible_subtotal += line_total
            eligible_items.append(
                {
                    "product_id": product_id,
                    "name": product["name"],
                    "quantity": quantity,
                    "line_price": _money(line_total),
                }
            )

        percent = float(program["percent_off"]) / 100
        discount = _money(eligible_subtotal * percent)
        result.update(
            {
                "status": (
                    "eligible_with_exclusions"
                    if eligible_items and excluded_items
                    else "eligible"
                    if eligible_items
                    else "no_eligible_items"
                ),
                "eligible_items": eligible_items,
                "excluded_items": excluded_items,
                "eligible_subtotal": _money(eligible_subtotal),
                "estimated_discount": discount,
                "estimated_discounted_subtotal": _money(eligible_subtotal - discount),
            }
        )
        return result

    def check_return_eligibility(
        self,
        order_id: str | int,
        product_id: str,
        customer_email: str | None,
        item_condition: str = "unknown",
        issue_type: str = "preference_return",
    ) -> dict:
        order_result = self.lookup_order(order_id, customer_email)
        if order_result.get("status") != "verified":
            return order_result

        item = next(
            (
                row
                for row in order_result["order"]["items"]
                if row["product_id"] == product_id.strip().upper()
            ),
            None,
        )
        if not item:
            return {
                "status": "item_not_found",
                "message": "That product was not found on the verified order.",
            }

        shipment = order_result.get("shipment") or {}
        delivered = _as_date(shipment.get("delivered_date"))
        if not delivered:
            return {
                "status": "not_delivered",
                "order_status": order_result["order"]["status"],
                "message": "A return window cannot start until the order is delivered.",
            }

        days_since_delivery = (self.today - delivered).days
        product = self._products_by_id[item["product_id"]]
        issue = issue_type.strip().lower()
        condition = item_condition.strip().lower()

        if issue in {"defect", "damaged", "manufacturing_defect", "damaged_on_arrival"}:
            warranty_deadline = _add_months(delivered, int(item["warranty_months"]))
            covered_period = self.today <= warranty_deadline
            return {
                "status": (
                    "warranty_review" if covered_period else "warranty_period_ended"
                ),
                "route": "warranty",
                "human_review": True,
                "product_id": item["product_id"],
                "product_name": item["name"],
                "is_final_sale": item["is_final_sale"],
                "delivered_date": delivered.isoformat(),
                "warranty_months": item["warranty_months"],
                "warranty_deadline": warranty_deadline.isoformat(),
                "message": (
                    "Final Sale does not remove manufacturing-defect warranty coverage."
                    if item["is_final_sale"]
                    else "Manufacturing defects are handled under the warranty."
                ),
            }

        if item["is_final_sale"]:
            return {
                "status": "not_eligible",
                "route": "return",
                "reason": "final_sale",
                "message": "Final Sale items are not returnable for preference.",
            }

        member = order_result["customer"]["trail_club_member"]
        return_days = 60 if member else int(product["return_window_days"])
        deadline = delivered + timedelta(days=return_days)
        if self.today > deadline:
            return {
                "status": "not_eligible",
                "route": "return",
                "reason": "return_window_ended",
                "delivered_date": delivered.isoformat(),
                "days_since_delivery": days_since_delivery,
                "return_window_days": return_days,
                "return_deadline": deadline.isoformat(),
                "message": "Ask whether the issue is a defect before closing the case.",
            }

        if condition in {
            "used",
            "worn_outdoors",
            "missing_tags",
            "damaged_by_customer",
        }:
            return {
                "status": "not_eligible",
                "route": "return",
                "reason": "item_condition",
                "return_deadline": deadline.isoformat(),
                "message": "The stated item condition does not meet the return policy.",
            }
        if condition == "unknown":
            return {
                "status": "more_information_needed",
                "route": "return",
                "return_deadline": deadline.isoformat(),
                "question": (
                    "Is the item unused with tags and original packaging? For footwear, "
                    "was it worn outdoors?"
                ),
            }

        return {
            "status": "eligible",
            "route": "return",
            "product_id": item["product_id"],
            "product_name": item["name"],
            "trail_club_member": member,
            "delivered_date": delivered.isoformat(),
            "return_window_days": return_days,
            "return_deadline": deadline.isoformat(),
            "days_since_delivery": days_since_delivery,
            "message": "Eligibility is based on the supplied condition and verified order.",
        }
