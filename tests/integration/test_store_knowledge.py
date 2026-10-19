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
