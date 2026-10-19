"""Durable preparation follows source revisions without generating request-time facts."""
from copy import deepcopy
from unittest.mock import Mock

from hedge_shared import storage, store_knowledge
from hedge_shared.store_v1 import StoreAppMetadata

from .test_store_v1_persistence import database as database
from .test_store_v1_persistence import migrate


def saved(app):
    storage.upsert_catalogue_app(storage.create_ingestion_run('prepared-test'), app)
    return storage.get_catalogue_apps([app.id],store_id=app.store_id).get(app.id)


def test_unchanged_sync_reuses_preparation_and_changes_invalidate_it(database, monkeypatch):
    migrate.main()
    app = StoreAppMetadata(store_id='Preparation',app_id='Native-ID',name='Telemetry',
                           description='Displays energy readings.',active=True,visible=True)
    original = store_knowledge.prepare
    prepare = Mock(wraps=original)
    monkeypatch.setattr(store_knowledge, 'prepare', prepare)
    first = saved(app)
    assert first['revision'] == 1 and first['prepared_knowledge'] == original(app)
    assert 'prepared_knowledge' not in first['payload']
    assert saved(app) == first
    prepare.assert_called_once()
    changed = app.model_copy(update={'readme':'<p>SMS is available only in simulation.</p>'})
    second = saved(changed)
    assert second['revision'] == 2 and prepare.call_count == 2
    assert second['prepared_knowledge']['checksum'] == changed.checksum
    assert 'only in simulation' in store_knowledge.project(second)['source_evidence']['readme']
    assert saved(changed.model_copy(update={'visible':False})) is None


def test_old_or_mismatched_knowledge_falls_back_and_repairs_without_source_revision(database):
    migrate.main()
    app = StoreAppMetadata(store_id='Preparation',app_id='Native-ID',description='Displays energy readings.',active=True,visible=True)
    row = saved(app)
    corrupt = deepcopy(row['prepared_knowledge'])
    corrupt['version'] = 0
    corrupt['projection']['description'] = 'invented facts'
    import json
    with storage.connection() as conn:
        conn.execute('UPDATE catalog_apps SET prepared_knowledge=%s::jsonb WHERE id=%s',(json.dumps(corrupt),app.id))
    old = storage.get_catalogue_apps([app.id],store_id=app.store_id)[app.id]
    assert store_knowledge.project(old) == app.recommendation_projection()
    repaired = saved(app)
    assert repaired['revision'] == row['revision']
    assert repaired['prepared_knowledge'] == store_knowledge.prepare(app)



def test_offline_prose_reuses_current_source_and_cannot_publish_after_source_change(database, monkeypatch):
    import pytest

    from scripts import prepare_store_explanations

    migrate.main()
    app = StoreAppMetadata(store_id='Preparation', app_id='Prose', name='Meter',
                           description='Displays energy readings.', active=True, visible=True)
    saved(app)
    prose = {'summary':'Displays energy readings.', 'simple':'See energy readings.',
             'use_when':'viewing energy readings'}
    artifact = {'version':1, 'en':prose, 'tr':prose, 'facts':[{
        'path':'description', 'quote':app.description, 'en':prose['summary'], 'tr':prose['summary']}]}
    record = {'id':app.id, 'checksum':app.checksum, 'explanation':artifact,
              'review':{'method':'agent_source_review', 'reviewer':'Test reviewer',
                        'note':'Compared both language explanations to complete source.'}}
    assert prepare_store_explanations.prepare(app.store_id, [record])[0]['status'] == 'source_review_import'
    assert prepare_store_explanations.prepare(app.store_id, [record])[0]['status'] == 'reused'
    with pytest.raises(ValueError, match='current checksum'):
        prepare_store_explanations.prepare(app.store_id, [{**record, 'checksum':'stale'}])
    changed = app.model_copy(update={'description':'Displays district heat readings.'})
    saved(changed)
    refreshed = store_knowledge.explanation(store_knowledge.project(saved(changed)))
    assert refreshed['review']['method'] == 'source_extraction'
    assert refreshed['en']['summary'] == changed.description
    assert app.description not in str(refreshed)
    record = {**record, 'checksum':changed.checksum}
    with pytest.raises(ValueError, match='unbound quotations'):
        prepare_store_explanations.prepare(app.store_id, [record])
    record['explanation']['facts'][0]['quote'] = changed.description
    original = prepare_store_explanations.explanation
    def concurrent_change(projection):
        checked = original(projection)
        saved(changed.model_copy(update={'visible':False}))
        return checked
    monkeypatch.setattr(prepare_store_explanations, 'explanation', concurrent_change)
    with pytest.raises(ValueError, match='Source changed'):
        prepare_store_explanations.prepare(app.store_id, [record])
    assert saved(changed.model_copy(update={'visible':False})) is None


def test_automatic_english_upgrade_preserves_source_revision_and_rebuilds_after_changes(database):
    import json

    migrate.main()
    app = StoreAppMetadata(store_id='Preparation', app_id='New-App', name='Registry',
                           readme='<p>Used to publish device registers.</p>', active=True, visible=True)
    initial = saved(app)
    prose = initial['prepared_knowledge']['explanation']
    assert prose['review']['method'] == 'source_extraction'
    assert 'publish device registers' in prose['en']['simple']
    with storage.connection() as conn:
        conn.execute('UPDATE catalog_apps SET prepared_knowledge=%s::jsonb WHERE id=%s',
                     (json.dumps({'version':0}), app.id))
    assert storage.rebuild_store_knowledge(app.store_id) == 1
    assert storage.rebuild_store_knowledge(app.store_id) == 0
    rebuilt = storage.get_catalogue_apps([app.id], store_id=app.store_id)[app.id]
    assert rebuilt['revision'] == initial['revision']
    assert rebuilt['checksum'] == initial['checksum']
    assert rebuilt['prepared_knowledge']['explanation'] == prose
    updated = saved(app.model_copy(update={'readme':'<p>Used to manage laboratory samples.</p>'}))
    assert updated['revision'] == initial['revision'] + 1
    assert 'device registers' not in str(updated['prepared_knowledge']['explanation'])


def test_m2m_managed_sync_prepares_new_and_changed_apps_and_preserves_observation_on_denial(database, tmp_path):
    import time

    import httpx
    import pytest
    from hedge_shared import store_sync

    from .test_store_v1_recommendations import client_module, snapshot

    migrate.main()
    issuer = 'https://identity.invalid/realm'
    secret = tmp_path/'secret'
    secret.write_text('integration-test-only')
    secret.chmod(0o600)
    rejected = False
    def identity(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'issuer':issuer, 'token_endpoint':issuer+'/token'})
        if rejected:
            return httpx.Response(401, json={'error':'unauthorized_client'})
        return httpx.Response(200, json={'access_token':'test-token', 'token_type':'Bearer',
                                        'expires_in':300})
    auth = client_module.StoreClientCredentials(issuer, 'client', str(secret),
                                                transport=httpx.MockTransport(identity))
    raw = {'appId':'opaque-native', 'fkAppStoreId':'M2M-Test', 'name':'Registry',
           'readme':'<p>Used to publish device registers.</p>', 'active':True, 'visible':True}
    def source(request):
        assert request.headers['authorization'] == 'Bearer test-token'
        return httpx.Response(200, json=[raw])
    api = client_module.HedgeApiClient('https://store.invalid/api/v1', store_id='M2M-Test',
                                      credentials=auth, transport=httpx.MockTransport(source))
    def sync():
        return snapshot.reconcile_catalogue_snapshot('m2m-test', api.fetch_catalogue_records,
                    store_id='M2M-Test', managed_source='authorized_api')
    assert sync()['created'] == 1
    app = client_module.normalize_store_v1_app(raw)
    first = storage.get_catalogue_apps([app.id], store_id=app.store_id)[app.id]
    assert first['prepared_knowledge']['explanation']['en']['simple'] == 'It helps you publish device registers.'
    assert sync()['unchanged'] == 1
    assert storage.get_catalogue_apps([app.id], store_id=app.store_id)[app.id] == first
    raw['readme'] = '<p>Used to manage laboratory samples.</p>'
    assert sync()['updated'] == 1
    updated = storage.get_catalogue_apps([app.id], store_id=app.store_id)[app.id]
    assert updated['revision'] == first['revision'] + 1
    assert 'device registers' not in str(updated['prepared_knowledge']['explanation'])
    observed = store_sync.status(app.store_id)
    rejected = True
    auth._expires = time.monotonic() - 1
    with pytest.raises(client_module.StoreApiError) as failure:
        sync()
    assert failure.value.status_code == 401
    store_sync.failed(app.store_id, failure.value.status_code)
    failed = store_sync.status(app.store_id)
    assert failed['snapshot_at'] == observed['snapshot_at']
    assert failed['available'] == 1 and failed['last_error'] == 'authorization_required'
    assert storage.get_catalogue_apps([app.id], store_id=app.store_id)[app.id] == updated
