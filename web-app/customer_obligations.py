"""Shared read-only calendar activity state for the sales CRM."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
import hashlib
import json
from zoneinfo import ZoneInfo

STOCKHOLM = ZoneInfo("Europe/Stockholm")
STATE_EVENT_COLUMNS = [
    "event_id", "kind", "entity_id", "customer_id", "owner_user_name",
    "actor_user_name", "revision", "occurred_at", "client_request_id",
    "fingerprint", "payload_json", "recorded_at",
]
OPEN_STATUSES = {"open", "scheduled", "needs_review"}
CLOSED_STATUSES = {"resolved", "cancelled"}
UNREACHED = {"ej anträffbar", "unreachable", "not_reached"}


def text(value):
    return str(value or "").strip()


def key(value):
    return " ".join(text(value).casefold().split())


def instant(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        raw = text(value)
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            for fmt in ("%Y/%m/%d", "%d/%m/%Y", "%d.%m.%Y"):
                try:
                    parsed = datetime.strptime(raw, fmt)
                    break
                except ValueError:
                    continue
            else:
                from priority import parse_datetime
                parsed = parse_datetime(raw)
                if parsed is None:
                    return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=STOCKHOLM)
    return parsed.astimezone(STOCKHOLM)


def day(value):
    parsed = instant(value)
    return parsed.date() if parsed else None


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def source_fingerprint(row):
    """Use stable contact evidence rather than mutable row positions."""
    return fingerprint({name: text(row.get(name)) for name in (
        "customer_id", "date_time", "sales_person", "contact_channel", "comment",
    )})


def contact_anchor(row):
    """Immutable-enough legacy anchor; editable notes/owner/result are not IDs.

    A collision is quarantined by build_customer_state, never disambiguated by
    spreadsheet position. Correcting an event timestamp still needs an explicit
    source mapping; only persisted IDs can survive arbitrary identity edits.
    """
    when = instant(row.get("date_time") or row.get("source_created_at"))
    channel = key(row.get("contact_channel") or row.get("contact_type"))
    channel = {"telefon": "phone", "mejl": "email", "bes\u00f6k": "visit", "besok": "visit"}.get(channel, channel)
    return fingerprint([text(row.get("customer_id")), when.isoformat() if when else "", channel])


def stable_contact_source_id(row):
    return (text(row.get("_stable_source_id")) or text(row.get("contact_id"))
            or "legacy2:" + contact_anchor(row)[:32])


def confirmed(value):
    return key(value) in {"true", "y", "yes", "1", "ja"}


def obligation_id_for_contact(row):
    return "followup:" + stable_contact_source_id(row)


def obligation_id_for_activity(row):
    if text(row.get("obligation_id")):
        return text(row.get("obligation_id"))
    source = text(row.get("source_contact_id"))
    return ("followup:" + source) if source else "calendar:" + text(row.get("planned_activity_id"))


def _rows(rows):
    return [row[1] if isinstance(row, (tuple, list)) and len(row) == 2
            and isinstance(row[1], dict) else row for row in rows or ()]


def event_payload(event):
    payload = event.get("payload_json") or event.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("Customer state event payload is not an object")
    return dict(payload)


def event_revision(row):
    try:
        return max(0, int(float(row.get("revision") or 0)))
    except (ValueError, TypeError):
        return 0


def latest_state_events(events, *, as_of):
    current = instant(as_of)
    latest = {}
    for event in _rows(events):
        try:
            event_payload(event)
        except (ValueError, TypeError):
            continue
        when = instant(event.get("occurred_at"))
        recorded = instant(event.get("recorded_at") or event.get("created_at"))
        if when is None or when.timestamp() > current.timestamp() or (recorded and recorded.timestamp() > current.timestamp()):
            continue
        identity = (text(event.get("kind")), text(event.get("customer_id")),
                    text(event.get("entity_id")))
        marker = (when.timestamp(), event_revision(event), text(event.get("event_id")))
        if identity not in latest or marker > latest[identity][0]:
            latest[identity] = (marker, event)
    return {identity: value[1] for identity, value in latest.items()}


def build_customer_state(customers, contact_rows, planned_activity_rows, state_events=(), *,
                         as_of, owner_user_names=None, order_rows=(), order_features=None):
    """One read-only activity projection, shared by every operational consumer.

    History is retained. Superseded is never completed. Decision instants (not
    future appointment dates or note edits) cover only earlier missed work.
    Ownership comes from the current master; attribution stays on source rows.
    """
    from priority import _canonicalize_rows, _known_at, is_human_contact, normalize_contact_result
    current = instant(as_of)
    if current is None:
        raise ValueError("An explicit as_of instant is required")
    counts = defaultdict(int)
    for row in customers:
        counts[text(row.get("customer_id"))] += 1
    masters = {text(row.get("customer_id")): row for row in customers
               if text(row.get("customer_id")) and counts[text(row.get("customer_id"))] == 1
               and key(row.get("status")) not in {"cancelled", "deleted", "inactive"}
               and not confirmed(row.get("cancelled_flag"))}

    def valid_rows(rows):
        return [dict(row) for row in _canonicalize_rows(_rows(rows), customers,
                    name_field="customer", number_field="customer_number")
                if text(row.get("customer_id")) in masters and not row.get("_identity_unresolved")
                and _known_at(row, current)]

    contacts = [row for row in valid_rows(contact_rows)
                if instant(row.get("date_time")) and instant(row["date_time"]).timestamp() <= current.timestamp()]
    saved = latest_state_events(state_events, as_of=current)
    by_contact = {stable_contact_source_id(row): row for row in contacts
                  if contact_counts[stable_contact_source_id(row)] == 1}
    plans = [row for row in valid_rows(planned_activity_rows)
             if key(row.get("status")) != "route_pending"
             and (not instant(row.get("created_at")) or instant(row["created_at"]).timestamp() <= current.timestamp())]
    # A cross-customer source is corrupt history, never an operational blocker.
    plans = [row for row in plans if not row.get("source_contact_id")
             or row["source_contact_id"] not in by_contact
             or text(by_contact[row["source_contact_id"]].get("customer_id")) == text(row.get("customer_id"))]
    saved = latest_state_events(state_events, as_of=current)
    grouped = defaultdict(list)
    actions = defaultdict(list)
    attempts, reached = {}, {}
    for row in contacts:
        cid = text(row.get("customer_id"))
        when = instant(row["date_time"])
        result = normalize_contact_result(row.get("result"))
        # Technical mail events, imports and historical permission decisions
        # never stand in for a seller's actual registered contact attempt.
        if is_human_contact(row) and key(row.get("result")) not in {"återkom ej", "kontakt tillåten", "kontakta ej", "ring ej"} and result in {"Positiv", "Neutral", "Negativ", "Ej anträffbar", "Order lagd"}:
            evidence = (when, "contact", stable_contact_source_id(row))
            actions[cid].append(evidence)
            if cid not in attempts or when.timestamp() > instant(attempts[cid]["date_time"]).timestamp():
                attempts[cid] = row
            if result in {"Positiv", "Neutral", "Negativ"} and (cid not in reached or when.timestamp() > instant(reached[cid]["date_time"]).timestamp()):
                reached[cid] = row
    source_plan_counts = defaultdict(int)
    for row in plans:
        if row.get("source_contact_id"):
            source_plan_counts[text(row["source_contact_id"])] += 1

    def make(cid, oid, due, source, plan):
        owner = text((owner_user_names or {}).get(cid)) if owner_user_names is not None else text(masters[cid].get("sales_person"))
        source_id = stable_contact_source_id(source) if source else text(plan.get("source_contact_id"))
        aid = text(plan.get("planned_activity_id"))
        item = dict(customer_id=cid, customer=text(masters[cid].get("customer")),
            customer_row=masters[cid].get("row"), customer_number=text(masters[cid].get("customer_number")),
            owner_user_name=owner, obligation_id=oid, source_scope="obligation:" + oid,
            source_contact_id=source_id, source_created_at=text(source.get("date_time") or plan.get("created_at")),
            created_at=text(plan.get("created_at") or source.get("date_time")),
            due_date=due.date().isoformat(), due_at=due.isoformat(),
            original_due_date=due.date().isoformat(), attention_scheduled_at=due.isoformat(),
            planned_activity_id=aid, original_planned_activity_id=aid,
            contact_type=text(plan.get("contact_type") or source.get("contact_channel")),
            note=text(plan.get("note") or source.get("comment")),
            appointment_confirmed=plan.get("appointment_confirmed", ""), picking_help=plan.get("picking_help", ""),
            agreed_at=text(plan.get("agreed_at") or plan.get("created_at")) if confirmed(plan.get("appointment_confirmed")) else "",
            purpose="calendar_activity", commitment_kind="planned_task", customer_agreement_confirmed=False,
            evidence_status="documented", review_status="not_required", review_reasons=[],
            evidence_quality="calendar", calendar_status=key(plan.get("status")),
            status="scheduled", snooze_until="", resolution_event_id="",
            latest_attempt_at=text(attempts.get(cid, {}).get("date_time")),
            latest_attempt_result=text(attempts.get(cid, {}).get("result")),
            # Persisting the already projected source ID is not a source edit.
            source_state_fingerprint=fingerprint({k: v for k, v in source.items()
                if k not in {"contact_id", "_stable_source_id"}}), planning_state_fingerprint=fingerprint(plan))
        status = key(plan.get("status"))
        if status in {"completed", "cancelled", "skipped", "superseded"}:
            item.update(status={"completed": "resolved"}.get(status, status),
                        resolution_event_id=text(plan.get("completed_contact_id") or aid),
                        resolution_basis="activity_" + status)
        calendar_event = saved.get(("obligation", cid, "calendar:" + aid)) if aid else None
        event = calendar_event or saved.get(("obligation", cid, text(plan.get("obligation_id")) or oid))
        if event:
            payload = event_payload(event)
            event_aid = text(payload.get("planned_activity_id") or payload.get("original_planned_activity_id"))
            # Unscoped source events cannot close another calendar occurrence.
            same_occurrence = event_aid == aid if event_aid else bool(calendar_event)
            if same_occurrence and payload.get("status") in {"resolved", "cancelled", "skipped"} and item["status"] in OPEN_STATUSES:
                item.update(status=payload["status"], resolution_basis="legacy_administrative_closure",
                            resolution_event_id=text(event.get("event_id")))
        grouped[cid].append(item)
        return item

    for row in plans:
        cid, aid = text(row.get("customer_id")), text(row.get("planned_activity_id"))
        due = instant(row.get("scheduled_at"))
        if not aid or not due:
            continue
        source = by_contact.get(text(row.get("source_contact_id")), {})
        oid = (obligation_id_for_contact(source) if source and source_plan_counts[stable_contact_source_id(source)] == 1
               else "calendar:" + aid)
        make(cid, oid, due, source, row)
        decision = instant(row.get("planning_decided_at") or row.get("created_at"))
        if decision and decision.timestamp() <= current.timestamp():
            actions[cid].append((decision, "planning", aid))
        skipped = instant(row.get("skipped_through_at"))
        if not skipped and key(row.get("status")) == "skipped" and due.date() < current.date():
            skipped = due
        if skipped and skipped.timestamp() <= current.timestamp():
            actions[cid].append((skipped, "skip", aid))
    for cid, items in grouped.items():
        # Three maxima make the reduction linear after identity indexing.
        # The newest planning decision may be the item's own; retain the two
        # latest distinct pieces of evidence to exclude that self-reference.
        ordered = sorted(actions[cid], key=lambda action: (action[0].timestamp(), action[1], action[2]), reverse=True)
        for item in items:
            due = instant(item.get("due_at") or item["due_date"])
            if item["status"] in OPEN_STATUSES and due.date() < current.date():
                for when, kind, evidence_id in ordered:
                    own = evidence_id in {item["planned_activity_id"], item["source_contact_id"], item["obligation_id"]}
                    covers = (when.timestamp() >= due.timestamp() if kind == "skip" else when.timestamp() > due.timestamp())
                    if not covers:
                        break
                    if covers and (not own or kind == "skip" and not item["planned_activity_id"]):
                        item.update(status="skipped" if own and kind == "skip" else "superseded",
                                    resolution_basis=kind, resolution_event_id=evidence_id,
                                    resolution_at=when.isoformat())
                        break
            item["revision"] = int(fingerprint(item)[:12], 16)
        items.sort(key=lambda item: (item["due_date"], item["obligation_id"]))
    return {"obligations": dict(grouped), "contact_permissions": {}, "workflows": {},
            "latest_attempts": attempts, "latest_reached": reached, "as_of": current.isoformat(),
            "activity_contract_version": "customer-activity-v1"}


def ordinary_attention_followup(item):
    return bool(item.get("customer_id") and not item.get("identity_conflict") and not item.get("identity_ambiguous"))


def attention_schedule_marker(item):
    return instant(item.get("due_at") or item.get("due_date")) or datetime(1900, 1, 1, tzinfo=STOCKHOLM)


def attention_items(state, *, as_of, owner_user_name=None, query=None):
    """Group current missed work before search, totals and pagination."""
    current = instant(as_of)
    groups = defaultdict(list)
    for cid, obligations in state.get("obligations", {}).items():
        for item in obligations:
            due = day(item.get("due_date"))
            if (item.get("status") in OPEN_STATUSES and due and due < current.date()
                    and ordinary_attention_followup(item)
                    and (owner_user_name is None or key(item.get("owner_user_name")) == key(owner_user_name))):
                groups[(cid, key(item.get("owner_user_name")))].append(item)
    result = []
    for group in groups.values():
        latest = max(group, key=lambda item: (attention_schedule_marker(item), item["obligation_id"]))
        if query and key(query) not in key(" ".join(text(latest.get(field)) for field in (
                "customer", "customer_id", "customer_number", "note", "contact_type"))):
            continue
        older = len(group) - 1
        result.append({**latest, "item_type": "missed_calendar_activity",
                       "older_missed_count": older,
                       "older_missed_note": f"{older} äldre missade aktiviteter finns i historiken." if older else "",
                       "days_overdue": (current.date() - day(latest["due_date"])).days,
                       "review_only": False, "actions": ["log_contact", "reschedule", "skip"]})
    return sorted(result, key=lambda item: (-attention_schedule_marker(item).timestamp(), key(item["customer"]), item["obligation_id"]))
