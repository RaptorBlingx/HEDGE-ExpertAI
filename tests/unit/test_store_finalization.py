"""Connected source assertions remain grounded; output style cannot grant suitability."""
import pytest
from hedge_shared.store_knowledge import prepare
from hedge_shared.store_v1 import StoreAppMetadata

from scripts.store_v1_playground import load_service

suitability = load_service('finalize_suitability', 'expert-recommend')('suitability')

FIRST = 'BatchBridge provides a service for records coming from multiple sensors in one site.'
SECOND = ('Those records are then combined, according to available agreements '
          'and sent under a common record.')
CAPACITY = ('Although the field trial only includes 2 sensors, '
            'the system is prepared to handle more than 2.')


def app_for(text):
    app = StoreAppMetadata(store_id='Store', app_id='opaque-new', name='BatchBridge',
                           active=True, visible=True, readme=text)
    knowledge = prepare(app)
    return {**knowledge['projection'], 'prepared_explanation':knowledge['explanation']}


def test_connected_passive_assertions_and_sample_capacity_do_not_need_manual_prose():
    app = app_for(FIRST + ' ' + SECOND + ' ' + CAPACITY)
    decision = suitability.assess('combine records from multiple sensors', app, 'en')
    assert decision['status'] == 'source_supported'
    assert decision['evidence_spans'] == [FIRST + ' ' + SECOND]
    assert suitability.assess('100 sensors in production', app, 'en')['status'] == 'uncertain'
    fact = next(f for f in app['prepared_explanation']['facts'] if 'simple_en' in f)
    assert fact['quote'] in app['source_evidence'][fact['path']]
    assert fact['short_en'] == 'It combines multiple records within one site into one record.'


@pytest.mark.parametrize('text', [
    FIRST + ' Those records are not combined.',
    FIRST + ' Those records are then combined only in simulation.',
    FIRST + ' Those records are then combined by an external service.',
    FIRST + ' Those records are then combined when cloud access is available.',
    FIRST + ' Those records are then combined using an unspecified licensed module.',
    FIRST.replace('BatchBridge', 'Another app') + ' ' + SECOND,
    FIRST + ' Those records are then combined. This app requires another app.',
    FIRST + ' ' + SECOND + ' Only 2 sensors are supported.',
    FIRST + ' ' + SECOND + ' ' + CAPACITY.replace('is prepared', 'is not prepared'),
])
def test_unresolved_actors_dependencies_and_real_capacity_restrictions_are_not_recommended(text):
    assert suitability.assess('combine records from multiple sensors', app_for(text), 'en')['status'] != 'source_supported'
