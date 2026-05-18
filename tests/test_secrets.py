"""Tests for secrets routes — /api/v1/secrets/*"""
import pytest


def test_list_secrets_returns_names(client):
    resp = client.get('/api/v1/secrets')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'secrets' in data
    assert isinstance(data['secrets'], list)
    assert data['count'] == len(data['secrets'])


def test_set_secret_requires_value(client):
    resp = client.post('/api/v1/secrets/MY_SECRET', json={})
    assert resp.status_code == 400
    assert resp.get_json()['code'] == 'VALIDATION_ERROR'


def test_set_secret_succeeds(client):
    resp = client.post('/api/v1/secrets/MY_SECRET', json={'value': 'abc123'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['updated'] is True
    assert data['name'] == 'MY_SECRET'


def test_delete_secret_succeeds(client):
    resp = client.delete('/api/v1/secrets/MY_SECRET')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['deleted'] is True


def test_secret_usages_returns_list(client):
    resp = client.get('/api/v1/secrets/MY_SECRET/usages')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'usages' in data
    assert isinstance(data['usages'], list)
    assert 'usageCount' in data


def test_list_secrets_conductor_error_returns_500(client):
    """When ConductorClient raises, list_secrets returns 500."""
    from unittest.mock import patch, MagicMock
    mock_client = MagicMock()
    mock_client.list_secrets.side_effect = Exception("conductor unreachable")
    with patch("app.routes.secrets.ConductorClient", return_value=mock_client):
        resp = client.get('/api/v1/secrets')
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['code'] == 'SECRETS_ERROR'


def test_set_secret_conductor_error_returns_500(client):
    """When ConductorClient raises during set_secret, returns 500."""
    from unittest.mock import patch, MagicMock
    mock_client = MagicMock()
    mock_client.set_secret.side_effect = Exception("conductor unreachable")
    with patch("app.routes.secrets.ConductorClient", return_value=mock_client):
        resp = client.post('/api/v1/secrets/MY_SECRET', json={'value': 'abc'})
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['code'] == 'SET_SECRET_ERROR'


def test_delete_secret_conductor_error_returns_500(client):
    """When ConductorClient raises during delete, returns 500."""
    from unittest.mock import patch, MagicMock
    mock_client = MagicMock()
    mock_client.delete_secret.side_effect = Exception("conductor unreachable")
    with patch("app.routes.secrets.ConductorClient", return_value=mock_client):
        resp = client.delete('/api/v1/secrets/MY_SECRET')
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['code'] == 'DELETE_SECRET_ERROR'


def test_secret_usages_with_matching_secret(client_with_mock_conductor):
    """Test usages endpoint when a workflow definition references a task name."""
    # 'validate_order' appears in the mock's listing tasks
    resp = client_with_mock_conductor.get('/api/v1/secrets/validate_order/usages')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'usages' in data
    # The mock listing has 'validate_order' as a task name in multiple workflow definitions
    assert data['usageCount'] >= 1
