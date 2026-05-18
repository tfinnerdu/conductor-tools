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
