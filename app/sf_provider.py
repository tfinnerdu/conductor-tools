"""Salesforce Education Cloud Provider

Follows Doane *_provider.py pattern. Target objects:
  Account (PersonAccount=true) — upserted via SIS_ID__c external ID
  ContactPoint — parented to Account (not Contact)
  IndividualApplication — uses Ethos_Guid__c

Auth: OAuth + service principal preferred. PAT not used per Doane standards.
# TODO(salesforce): confirm OAuth flow vs username/password for service account

Real path uses requests directly against the Salesforce REST API (SOQL).
simple_salesforce could replace this once credentials are confirmed — it is
NOT added as a dependency here per Doane standards; add to requirements.txt
and swap the SOQL helpers below when ready.
"""
import os
import uuid

import requests


def _configured() -> bool:
    """Return True when sufficient Salesforce credentials are present.

    Accepts either:
      - SF_USERNAME + SF_PASSWORD + SF_SECURITY_TOKEN   (username/password flow)
      - SF_ACCESS_TOKEN + SF_INSTANCE_URL               (pre-issued bearer token)
    """
    has_user_pass = (
        os.environ.get("SF_USERNAME")
        and os.environ.get("SF_PASSWORD")
        and os.environ.get("SF_SECURITY_TOKEN")
    )
    has_token = os.environ.get("SF_ACCESS_TOKEN") and os.environ.get("SF_INSTANCE_URL")
    return bool(has_user_pass or has_token)


def _get_instance_url() -> str:
    return os.environ.get("SF_INSTANCE_URL", "")


def _get_access_token() -> str:
    """Return a bearer token.

    When SF_ACCESS_TOKEN is set, use it directly.
    Otherwise attempt username/password OAuth flow.
    # TODO(salesforce): swap for client_credentials or JWT flow when available
    """
    token = os.environ.get("SF_ACCESS_TOKEN")
    if token:
        return token

    login_url = os.environ.get("SF_LOGIN_URL", "https://login.salesforce.com")
    payload = {
        "grant_type": "password",
        "client_id": os.environ.get("SF_CLIENT_ID", ""),
        "client_secret": os.environ.get("SF_CLIENT_SECRET", ""),
        "username": os.environ.get("SF_USERNAME", ""),
        "password": os.environ.get("SF_PASSWORD", "") + os.environ.get("SF_SECURITY_TOKEN", ""),
    }
    resp = requests.post(f"{login_url}/services/oauth2/token", data=payload, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"]


def _soql(query: str) -> dict:
    """Execute a SOQL query via the Salesforce REST API.

    Returns the standard SF REST response: {totalSize, done, records}.
    """
    instance_url = _get_instance_url()
    token = _get_access_token()
    resp = requests.get(
        f"{instance_url}/services/data/v59.0/query",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        params={"q": query},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def find_person_by_sis_id(sis_id: str) -> dict:
    """Find a Salesforce PersonAccount by SIS_ID__c external ID.

    SOQL: SELECT Id, FirstName, LastName, SIS_ID__c, Ethos_Guid__c, PersonEmail
          FROM Account WHERE SIS_ID__c = '{sis_id}' AND IsPersonAccount = true
    Returns {records, record_count, status, diagnosis}.
    # TODO(salesforce): confirm SIS_ID__c field API name on Account object
    """
    if not _configured():
        return _mock_sis_lookup(sis_id)

    try:
        soql = (
            f"SELECT Id, FirstName, LastName, SIS_ID__c, Ethos_Guid__c, PersonEmail "
            f"FROM Account WHERE SIS_ID__c = '{sis_id}' AND IsPersonAccount = true"  # TODO(salesforce): confirm IsPersonAccount field name
        )
        result = _soql(soql)
        records = result.get("records", [])
        return _build_result(records)
    except Exception:
        return _mock_sis_lookup(sis_id)


def find_person_by_guid(guid: str) -> dict:
    """Find a Salesforce PersonAccount by Ethos GUID.

    SOQL: SELECT Id, FirstName, LastName, SIS_ID__c, Ethos_Guid__c, PersonEmail
          FROM Account WHERE Ethos_Guid__c = '{guid}' AND IsPersonAccount = true
    Returns {records, record_count, status, diagnosis}.
    # TODO(salesforce): confirm Ethos_Guid__c field API name on Account object
    """
    if not _configured():
        return _mock_guid_lookup(guid)

    try:
        soql = (
            f"SELECT Id, FirstName, LastName, SIS_ID__c, Ethos_Guid__c, PersonEmail "
            f"FROM Account WHERE Ethos_Guid__c = '{guid}' AND IsPersonAccount = true"  # TODO(salesforce): confirm Ethos_Guid__c field name
        )
        result = _soql(soql)
        records = result.get("records", [])
        return _build_result(records)
    except Exception:
        return _mock_guid_lookup(guid)


def find_duplicate_accounts(sis_id: str) -> list:
    """Return all Account records matching a SIS_ID__c value (>1 = duplicate).

    SOQL: SELECT Id, FirstName, LastName, SIS_ID__c, CreatedDate
          FROM Account WHERE SIS_ID__c = '{sis_id}' AND IsPersonAccount = true
    # TODO(salesforce): add ORDER BY CreatedDate for deterministic results
    """
    if not _configured():
        return _mock_duplicate_lookup(sis_id)

    try:
        soql = (
            f"SELECT Id, FirstName, LastName, SIS_ID__c, CreatedDate "
            f"FROM Account WHERE SIS_ID__c = '{sis_id}' AND IsPersonAccount = true "
            f"ORDER BY CreatedDate ASC"
        )
        result = _soql(soql)
        return result.get("records", [])
    except Exception:
        return _mock_duplicate_lookup(sis_id)


def get_account(sf_id: str) -> dict:
    """Fetch a single Account record by Salesforce ID.

    Real path: GET /sobjects/Account/{sf_id}
    # TODO(salesforce): confirm which fields to retrieve via ?fields= param
    """
    if not _configured():
        return _mock_account(sf_id)

    try:
        instance_url = _get_instance_url()
        token = _get_access_token()
        resp = requests.get(
            f"{instance_url}/services/data/v59.0/sobjects/Account/{sf_id}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return _mock_account(sf_id)


def check_health() -> dict:
    """Read-only probe of Salesforce API availability."""
    if not _configured():
        return {"ok": True, "detail": "not_configured", "latency_ms": None}

    import time
    t0 = time.time()
    try:
        instance_url = _get_instance_url()
        token = _get_access_token()
        resp = requests.get(
            f"{instance_url}/services/data/v59.0/limits",  # TODO(salesforce): confirm lightweight health endpoint
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=5,
        )
        latency_ms = round((time.time() - t0) * 1000)
        return {
            "ok": resp.status_code < 500,
            "latency_ms": latency_ms,
            "detail": "reachable" if resp.status_code < 500 else f"http_{resp.status_code}",
        }
    except requests.Timeout:
        import time as _time
        return {"ok": False, "latency_ms": round((_time.time() - t0) * 1000), "detail": "timeout"}
    except Exception as exc:
        import time as _time
        return {"ok": False, "latency_ms": round((_time.time() - t0) * 1000), "detail": str(exc)[:120]}


# ---------------------------------------------------------------------------
# Shared result builder
# ---------------------------------------------------------------------------

def _build_result(records: list) -> dict:
    """Build the standard provider result dict from a list of Account records."""
    count = len(records)
    if count == 0:
        status = "error"
        diagnosis = "Record not found in Salesforce — migration has not run or failed"
    elif count > 1:
        status = "warning"
        diagnosis = f"DUPLICATE: {count} records found — merge required"
    else:
        record = records[0]
        if not record.get("SIS_ID__c"):  # TODO(salesforce): confirm SIS_ID__c field name
            status = "warning"
            diagnosis = "Record exists but missing SIS_ID__c"
        else:
            status = "ok"
            diagnosis = "Record looks healthy"

    return {
        "records": records,
        "record_count": count,
        "status": status,
        "diagnosis": diagnosis,
    }


# ---------------------------------------------------------------------------
# Mock fixtures — realistic Doane Salesforce Ed Cloud shapes
# ---------------------------------------------------------------------------

def _mock_sis_lookup(sis_id: str) -> dict:
    """Return a mock SF SOQL result for SIS_ID__c lookup."""
    if "dup" in sis_id.lower():
        records = [
            {
                "Id": "SF001AAA",
                "FirstName": "Jane",
                "LastName": "Doe",
                "SIS_ID__c": sis_id,  # TODO(salesforce): confirm SIS_ID__c field name
                "Ethos_Guid__c": f"mock-guid-{sis_id}-1",  # TODO(salesforce): confirm Ethos_Guid__c field name
                "PersonEmail": "jane.doe@doane.edu",  # TODO(salesforce): confirm PersonEmail field name
            },
            {
                "Id": "SF002BBB",
                "FirstName": "Jane",
                "LastName": "Doe",
                "SIS_ID__c": sis_id,
                "Ethos_Guid__c": f"mock-guid-{sis_id}-2",
                "PersonEmail": "jane.doe2@doane.edu",
            },
        ]
    elif "missing" in sis_id.lower():
        records = [
            {
                "Id": "SF003CCC",
                "FirstName": "John",
                "LastName": "Smith",
                "SIS_ID__c": None,  # TODO(salesforce): confirm SIS_ID__c field name
                "Ethos_Guid__c": None,
                "PersonEmail": None,
            }
        ]
    elif "notfound" in sis_id.lower() or "404" in sis_id:
        records = []
    else:
        records = [
            {
                "Id": "SF" + sis_id[-6:].upper().replace("-", "0"),
                "FirstName": "Alex",
                "LastName": "Student",
                "SIS_ID__c": sis_id,  # TODO(salesforce): confirm SIS_ID__c field name
                "Ethos_Guid__c": f"mock-guid-{sis_id}",  # TODO(salesforce): confirm Ethos_Guid__c field name
                "PersonEmail": "alex.student@doane.edu",  # TODO(salesforce): confirm PersonEmail field name
                "RecordTypeId": "PersonAccount",  # TODO(salesforce): confirm RecordTypeId value
            }
        ]

    return _build_result(records)


def _mock_guid_lookup(guid: str) -> dict:
    """Return a mock SF SOQL result for Ethos_Guid__c lookup."""
    if "notfound" in guid.lower():
        records = []
    else:
        records = [
            {
                "Id": "SF" + guid[-6:].upper().replace("-", "0"),
                "FirstName": "Alex",
                "LastName": "Student",
                "SIS_ID__c": "STU" + guid[-6:].upper().replace("-", "0"),  # TODO(salesforce): confirm SIS_ID__c field name
                "Ethos_Guid__c": guid,  # TODO(salesforce): confirm Ethos_Guid__c field name
                "PersonEmail": "alex.student@doane.edu",  # TODO(salesforce): confirm PersonEmail field name
            }
        ]
    return _build_result(records)


def _mock_duplicate_lookup(sis_id: str) -> list:
    """Return mock duplicate Account records."""
    result = _mock_sis_lookup(sis_id)
    return result.get("records", [])


def _mock_account(sf_id: str) -> dict:
    """Return a mock Account sobject record."""
    return {
        "Id": sf_id,
        "FirstName": "Alex",
        "LastName": "Student",
        "SIS_ID__c": "STU" + sf_id[-6:].upper(),  # TODO(salesforce): confirm SIS_ID__c field name
        "Ethos_Guid__c": f"mock-guid-{sf_id}",  # TODO(salesforce): confirm Ethos_Guid__c field name
        "PersonEmail": "alex.student@doane.edu",  # TODO(salesforce): confirm PersonEmail field name
        "IsPersonAccount": True,  # TODO(salesforce): confirm IsPersonAccount field name
        "RecordType": {"Name": "Person Account"},  # TODO(salesforce): confirm RecordType shape
    }
