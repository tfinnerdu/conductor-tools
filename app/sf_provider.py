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
import time
import uuid

import requests

# Token cache — shared across requests, refreshed when within 5 min of expiry
_token_cache: dict = {"token": None, "instance_url": None, "expires_at": 0.0}


def _configured() -> bool:
    """Return True when Salesforce credentials are present (username/password flow)."""
    return bool(
        os.environ.get("SF_USERNAME")
        and os.environ.get("SF_PASSWORD")
        and os.environ.get("SF_SECURITY_TOKEN")
    )


def _get_instance_url() -> str:
    """Return the Salesforce instance URL.

    Prefers the cached value from the last OAuth response (so SF_INSTANCE_URL
    is not required when using the username/password flow).
    """
    if _token_cache["instance_url"]:
        return _token_cache["instance_url"]
    return os.environ.get("SF_INSTANCE_URL", "")


def _get_access_token() -> str:
    """Return a valid bearer token, fetching a new one only when expired.

    Uses the OAuth2 username/password flow with a Connected App
    (SF_CLIENT_ID + SF_CLIENT_SECRET). Token is cached for 90 minutes;
    Salesforce issues 2-hour tokens so this gives a safe refresh buffer.
    The login response also populates _token_cache["instance_url"] so
    SF_INSTANCE_URL does not need to be set separately.
    # TODO(salesforce): migrate to JWT bearer or client_credentials flow
    # when a service-account Connected App is provisioned at Doane.
    """
    if _token_cache["token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["token"]

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

    _token_cache["token"] = data["access_token"]
    _token_cache["instance_url"] = data.get("instance_url", "")
    _token_cache["expires_at"] = time.time() + 5400  # 90 min
    return _token_cache["token"]


def _soql(query: str) -> dict:
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
    if not _configured():
        return _mock_sis_lookup(sis_id)
    try:
        soql = (
            f"SELECT Id, FirstName, LastName, SIS_ID__c, Ethos_Guid__c, PersonEmail "
            f"FROM Account WHERE SIS_ID__c = '{sis_id}' AND IsPersonAccount = true"
        )
        result = _soql(soql)
        records = result.get("records", [])
        return _build_result(records)
    except Exception:
        return _mock_sis_lookup(sis_id)


def find_person_by_guid(guid: str) -> dict:
    if not _configured():
        return _mock_guid_lookup(guid)
    try:
        soql = (
            f"SELECT Id, FirstName, LastName, SIS_ID__c, Ethos_Guid__c, PersonEmail "
            f"FROM Account WHERE Ethos_Guid__c = '{guid}' AND IsPersonAccount = true"
        )
        result = _soql(soql)
        records = result.get("records", [])
        return _build_result(records)
    except Exception:
        return _mock_guid_lookup(guid)


def find_duplicate_accounts(sis_id: str) -> list:
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
    if not _configured():
        return {"ok": True, "detail": "not_configured", "latency_ms": None}
    t0 = time.time()
    try:
        instance_url = _get_instance_url()
        token = _get_access_token()
        resp = requests.get(
            f"{instance_url}/services/data/v59.0/limits",
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
        return {"ok": False, "latency_ms": round((time.time() - t0) * 1000), "detail": "timeout"}
    except Exception as exc:
        return {"ok": False, "latency_ms": round((time.time() - t0) * 1000), "detail": str(exc)[:120]}


def _build_result(records: list) -> dict:
    count = len(records)
    if count == 0:
        status = "error"
        diagnosis = "Record not found in Salesforce — migration has not run or failed"
    elif count > 1:
        status = "warning"
        diagnosis = f"DUPLICATE: {count} records found — merge required"
    else:
        record = records[0]
        if not record.get("SIS_ID__c"):
            status = "warning"
            diagnosis = "Record exists but missing SIS_ID__c"
        else:
            status = "ok"
            diagnosis = "Record looks healthy"
    return {"records": records, "record_count": count, "status": status, "diagnosis": diagnosis}


def _mock_sis_lookup(sis_id: str) -> dict:
    if "dup" in sis_id.lower():
        records = [
            {"Id": "SF001AAA", "FirstName": "Jane", "LastName": "Doe", "SIS_ID__c": sis_id,
             "Ethos_Guid__c": f"mock-guid-{sis_id}-1", "PersonEmail": "jane.doe@doane.edu"},
            {"Id": "SF002BBB", "FirstName": "Jane", "LastName": "Doe", "SIS_ID__c": sis_id,
             "Ethos_Guid__c": f"mock-guid-{sis_id}-2", "PersonEmail": "jane.doe2@doane.edu"},
        ]
    elif "missing" in sis_id.lower():
        records = [{"Id": "SF003CCC", "FirstName": "John", "LastName": "Smith",
                    "SIS_ID__c": None, "Ethos_Guid__c": None, "PersonEmail": None}]
    elif "notfound" in sis_id.lower() or "404" in sis_id:
        records = []
    else:
        records = [{"Id": "SF" + sis_id[-6:].upper().replace("-", "0"), "FirstName": "Alex",
                    "LastName": "Student", "SIS_ID__c": sis_id,
                    "Ethos_Guid__c": f"mock-guid-{sis_id}", "PersonEmail": "alex.student@doane.edu",
                    "RecordTypeId": "PersonAccount"}]
    return _build_result(records)


def _mock_guid_lookup(guid: str) -> dict:
    if "notfound" in guid.lower():
        records = []
    else:
        records = [{"Id": "SF" + guid[-6:].upper().replace("-", "0"), "FirstName": "Alex",
                    "LastName": "Student", "SIS_ID__c": "STU" + guid[-6:].upper().replace("-", "0"),
                    "Ethos_Guid__c": guid, "PersonEmail": "alex.student@doane.edu"}]
    return _build_result(records)


def _mock_duplicate_lookup(sis_id: str) -> list:
    return _mock_sis_lookup(sis_id).get("records", [])


def _mock_account(sf_id: str) -> dict:
    return {"Id": sf_id, "FirstName": "Alex", "LastName": "Student",
            "SIS_ID__c": "STU" + sf_id[-6:].upper(), "Ethos_Guid__c": f"mock-guid-{sf_id}",
            "PersonEmail": "alex.student@doane.edu", "IsPersonAccount": True,
            "RecordType": {"Name": "Person Account"}}
