"""Authored controls against the private model, without Store access.

Run in the private runner: python -m scripts.check_store_conversation_grounding
The writer is controlled; the actual source review is exercised once per case.
These checks are not a semantic guarantee or a live Store validation.
"""
import json
from urllib.parse import urlparse

from scripts.store_v1_playground import load_service

CASES = [
    ('positive paraphrase', {'description': 'Displays electric meter readings and daily charts.'},
     'You can inspect meter values and daily charts.', True),
    ('future delivery', {'description': 'Provides earthquake warnings.',
                         'readme': 'SMS delivery is planned and is not available yet.'},
     'It delivers earthquake warnings by SMS today.', False),
    ('cross-field restriction', {'description': 'Provides MQTT telemetry.',
                                'readme': 'MQTT is available only in simulation. Production does not support MQTT.'},
     'It supports MQTT for production deployments.', False),
    ('commercial invention', {'description': 'Displays readings.', 'billable': 'false', 'price': '0.0'},
     'It is free with a EUR 0 monthly licence.', False),
    ('connector target', {'builtForConnector': 'Example Connector', 'connectorVersion': '1.0'},
     "The Store's builtForConnector field is Example Connector and its connectorVersion field is 1.0.", True),
    ('compatibility invention', {'builtForConnector': 'Example Connector', 'connectorVersion': '1.0'},
     'It is certified compatible with every release of Example Connector.', False),
    ('version-order invention', {'appVersionList[0].name': 'v1', 'appVersionList[1].name': 'v2'},
     'The first listed version, v1, is the latest release.', False),
    ('feature ownership', {'description': 'Water readings are sent by SMS. Earthquake warnings are displayed only on the dashboard.'},
     'It sends earthquake warnings by SMS.', False),
]


def check(module, real_client, fields, answer):
    draft = {'decision': 'answer', 'focus': ['1'], 'answer': answer, 'evidence': {'1': list(fields)}}

    class ControlledWriter:
        model = real_client().model

        def __init__(self):
            self.calls = 0

        def chat_structured(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return json.dumps(draft)
            return real_client().chat_structured(*args, **kwargs)

    module.OllamaClient = ControlledWriter
    try:
        return module.respond(
            'What does this Store evidence establish about the App?',
            [{'rank': 1, 'app': {'id': 'authored', 'app_id': 'authored', 'name': 'Example App',
                                'source_evidence': fields}}],
            'en', 'answer', [], references={'focus': ['1'], 'previous': ['1'], 'other': [], 'named': []},
            allow_repair=False,
        )
    finally:
        module.OllamaClient = real_client


def main():
    module = load_service('grounding_check_expert', 'expert-recommend')('store_conversation')
    real_client = module.OllamaClient
    if urlparse(real_client().base_url).hostname not in {'127.0.0.1', 'localhost'}:
        raise SystemExit('Grounding controls require the private loopback model')
    failures = 0
    for name, fields, answer, expected in CASES:
        result = check(module, real_client, fields, answer)
        served = result['generation']['source'] == 'ollama' and result['decision'] == 'answer'
        passed = served if expected else result['generation']['reason'] == 'grounding_review_rejected'
        failures += not passed
        print(json.dumps({'case': name, 'pass': passed, 'served': served,
                          'reason': result['generation']['reason'],
                          'seconds': result['generation']['seconds']}), flush=True)
    raise SystemExit(1 if failures else 0)


if __name__ == '__main__':
    main()
