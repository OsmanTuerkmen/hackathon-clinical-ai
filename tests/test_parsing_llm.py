"""Task10 contract tests; the only external boundary is a recording fake SDK client."""
import copy
import dataclasses
import json
import re
import time
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from ehds_desk import parsing
from ehds_desk.models import AccessRequest, Applicant, QuerySpec
from ehds_desk.parsing.rules import parse_rules
from ehds_desk.pipeline import DeskService
from ehds_desk.terminology import Terminology

class FakeClient:

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []
        self.messages = self

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        if callable(output):
            return output()
        return SimpleNamespace(stop_reason='end_turn', parsed_output=copy.deepcopy(output))

@pytest.fixture
def llm():
    from ehds_desk.parsing import llm
    return llm

@pytest.fixture(scope='module')
def term(db):
    return Terminology(db)

@pytest.fixture
def cfg(settings, tmp_path):
    return dataclasses.replace(settings, var_dir=tmp_path, anthropic_api_key='fake-no-network')

@pytest.fixture
def access_request():
    return AccessRequest(id='L1', applicant=Applicant(name='Researcher', organisation='University'), requested_as='health data request', purpose='Research on diabetes.', question='Please tally those with diabetes.', definitions=['diabetes = type 2 diabetes.', 'Tally the cohort using our novel protocol.'])

@pytest.fixture
def valid():
    return {'spec': {'population': [{'kind': 'condition', 'codes': {'system': 'icd10', 'prefixes': ['E11'], 'label': 'diabetes', 'source': 'llm'}}], 'metrics': [{'kind': 'count', 'name': 'n', 'label': 'Patients'}]}, 'purpose': {'prohibited': [], 'permitted': [{'source': 'llm', 'category': '53(1)(e)', 'quote': 'Research on diabetes.'}], 'spe_justification': []}}

def test_payload_contains_no_patient_rows(llm, access_request, term):
    access_request.model_extra.update(patient_rows=[{'patient_id': 'p-deadbeef', 'birth_year': 1980}], rows=17)
    payload = llm.build_payload(access_request, term.catalogue())
    assert set(payload) == {'request', 'catalogue', 'schema'}
    assert set(payload['request']) == {'requested_as', 'requested_format', 'purpose', 'question', 'definitions'}
    encoded = json.dumps(payload)
    assert not re.search('p-[0-9a-f]{8}', encoded)
    assert 'patient_rows' not in encoded and 'birth_year' not in encoded
    assert 'Researcher' not in encoded and 'University' not in encoded
    assert all((len(entry) == 2 for entries in payload['catalogue'].values() for entry in entries))

def test_patient_id_in_text_is_never_sent(llm, access_request, term, cfg, valid):
    access_request.question = 'Count p-deadbeef'
    client = FakeClient(valid)
    with pytest.raises(llm.LLMError):
        llm.parse_with_llm(access_request, term, cfg, client=client)
    assert not client.calls

def test_valid_tool_output_becomes_spec(llm, access_request, term, cfg, valid):
    client = FakeClient(valid)
    spec, purpose, cached = llm.parse_with_llm(access_request, term, cfg, client=client)
    assert isinstance(spec, QuerySpec) and spec.population[0].codes.prefixes == ['E11']
    assert purpose.permitted[0].quote == 'Research on diabetes.' and (not cached)
    call = client.calls[0]
    assert call['model'] == 'claude-opus-5-5'
    assert '66(3)' in call['system']
    assert call['output_config'] == {'effort': 'medium'}
    assert call['output_format'] is llm.LLMTranslation
    assert 0 < call['timeout'] <= 30
    assert not {'temperature', 'top_p', 'top_k', 'tool_choice', 'thinking'} & call.keys()
    assert set(json.loads(call['messages'][0]['content'])) == {'request', 'catalogue', 'schema'}

def test_invalid_output_retries_once_then_raises(llm, access_request, term, cfg):
    client = FakeClient({'spec': {}}, {'spec': {}})
    with pytest.raises(llm.LLMError):
        llm.parse_with_llm(access_request, term, cfg, client=client)
    assert len(client.calls) == 2
    assert len(client.calls[1]['messages']) > len(client.calls[0]['messages'])
    assert not list(cfg.var_dir.rglob('*.json'))

def test_schema_correction_can_succeed(llm, access_request, term, cfg, valid):
    client = FakeClient({'spec': {}}, valid)
    spec, _, cached = llm.parse_with_llm(access_request, term, cfg, client=client)
    assert spec.metrics[0].name == 'n' and (not cached)
    assert len(client.calls) == 2

def test_client_validation_rejects_semantically_invalid_spec(llm, access_request, term, cfg, valid):
    valid['spec']['metrics'] = [{'kind': 'percent', 'name': 'p', 'label': 'Percent', 'numerator': 'absent', 'denominator': 'absent'}]
    with pytest.raises(llm.LLMError):
        llm.parse_with_llm(access_request, term, cfg, client=FakeClient(valid, valid))

def test_cache_hit_skips_client(llm, access_request, term, cfg, valid):
    first = llm.parse_with_llm(access_request, term, cfg, client=FakeClient(valid))
    no_call = FakeClient()
    second = llm.parse_with_llm(access_request, term, cfg, client=no_call)
    assert second[:2] == first[:2] and second[2] and (not no_call.calls)
    assert len(list((cfg.var_dir / 'cache' / 'llm').glob('*.json'))) == 1

@pytest.mark.parametrize('change', ['request', 'model', 'prompt', 'catalogue'])
def test_cache_key_covers_inputs(llm, access_request, term, cfg, valid, monkeypatch, change):
    llm.parse_with_llm(access_request, term, cfg, client=FakeClient(valid))
    if change == 'request':
        access_request.question += ' Please.'
    elif change == 'model':
        cfg = dataclasses.replace(cfg, llm_model='different-model')
    elif change == 'prompt':
        monkeypatch.setattr(llm, 'PROMPT_VERSION', 'next-version')
    else:
        catalogue = term.catalogue()
        catalogue['icd10'].append(('X123', 'New description'))
        monkeypatch.setattr(term, 'catalogue', lambda: catalogue)
    client = FakeClient(valid)
    assert not llm.parse_with_llm(access_request, term, cfg, client=client)[2]
    assert len(client.calls) == 1

@pytest.mark.parametrize('corrupt', ['not-json', '{"spec": {}, "purpose": {}}'])
def test_invalid_cache_is_revalidated(llm, access_request, term, cfg, valid, corrupt):
    llm.parse_with_llm(access_request, term, cfg, client=FakeClient(valid))
    path = next((cfg.var_dir / 'cache' / 'llm').glob('*.json'))
    path.write_text(corrupt, encoding='utf-8')
    client = FakeClient(valid)
    spec, _, hit = llm.parse_with_llm(access_request, term, cfg, client=client)
    assert spec.metrics[0].name == 'n' and (not hit) and (len(client.calls) == 1)

def test_quotes_not_in_request_are_dropped(llm, access_request, term, cfg, valid):
    valid['purpose']['prohibited'] = [{'source': 'rules', 'category': '54(c)', 'quote': 'invented marketing'}]
    valid['purpose']['spe_justification'] = [{'source': 'llm', 'category': 'spe', 'quote': ''}]
    valid['purpose']['permitted'][0]['source'] = 'rules'
    _, purpose, _ = llm.parse_with_llm(access_request, term, cfg, client=FakeClient(valid))
    assert not purpose.prohibited and (not purpose.spe_justification)
    assert purpose.permitted[0].source == 'llm'

@pytest.mark.parametrize('reason', ['refusal', 'max_tokens'])
def test_refusal_and_truncation_are_not_retried(llm, access_request, term, cfg, valid, reason):
    client = FakeClient(lambda: SimpleNamespace(stop_reason=reason, parsed_output=valid))
    with pytest.raises(llm.LLMError):
        llm.parse_with_llm(access_request, term, cfg, client=client)
    assert len(client.calls) == 1
    assert not list(cfg.var_dir.rglob('*.json'))

def test_timeout_budget_includes_schema_retry(llm, access_request, term, cfg, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(llm.time, 'monotonic', lambda: now[0])

    def invalid_late():
        now[0] = 28.0
        return SimpleNamespace(stop_reason='end_turn', parsed_output={'spec': {}})
    client = FakeClient(invalid_late, TimeoutError('secret transport details'))
    with pytest.raises(llm.LLMError) as exc:
        llm.parse_with_llm(access_request, term, cfg, client=client)
    assert len(client.calls) == 2 and 0 < client.calls[1]['timeout'] <= 2
    assert 'secret' not in str(exc.value)

def test_wall_clock_deadline_even_for_blocking_client(llm, access_request, term, cfg, valid, monkeypatch):
    monkeypatch.setattr(llm, 'TIMEOUT_SECONDS', 0.03)

    def slow():
        time.sleep(0.2)
        return SimpleNamespace(stop_reason='end_turn', parsed_output=valid)
    started = time.monotonic()
    with pytest.raises(llm.LLMError):
        llm.parse_with_llm(access_request, term, cfg, client=FakeClient(slow))
    assert time.monotonic() - started < 0.15
    assert not list(cfg.var_dir.rglob('*.json'))

def test_api_error_is_sanitized_without_retry(llm, access_request, term, cfg):
    client = FakeClient(RuntimeError('api-key-and-request-data'))
    with pytest.raises(llm.LLMError) as exc:
        llm.parse_with_llm(access_request, term, cfg, client=client)
    assert len(client.calls) == 1 and 'api-key-and-request-data' not in str(exc.value)

def test_sdk_client_disables_retries(llm, access_request, term, cfg, valid, monkeypatch):
    anthropic = pytest.importorskip('anthropic')
    captured = {}
    fake = FakeClient(valid)
    fake.close = lambda: None

    def construct(**kwargs):
        captured.update(kwargs)
        return fake
    monkeypatch.setattr(anthropic, 'Anthropic', construct)
    assert llm.parse_with_llm(access_request, term, cfg)[0].metrics[0].name == 'n'
    assert captured['max_retries'] == 0 and captured['timeout'] <= 30

def test_sdk_generates_compatible_schema_offline(llm, access_request, term, cfg, valid, monkeypatch):
    anthropic = pytest.importorskip('anthropic')
    client = anthropic.Anthropic(api_key='fake-no-network', max_retries=0)
    bodies = []

    def intercept(*args, **kwargs):
        bodies.append(kwargs['body'])
        return SimpleNamespace(stop_reason='end_turn', parsed_output=valid)
    monkeypatch.setattr(client.messages, '_post', intercept)
    try:
        llm.parse_with_llm(access_request, term, cfg, client=client)
    finally:
        client.close()
    schema = bodies[0]['output_config']['format']['schema']

    def check(node):
        if isinstance(node, dict):
            assert 'oneOf' not in node and 'discriminator' not in node
            if node.get('type') == 'object':
                assert node.get('additionalProperties') is False
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for value in node:
                check(value)
    check(schema)
    with pytest.raises(ValidationError):
        llm.LLMTranslation.model_validate({'spec': {'metrics': []}, 'purpose': valid['purpose']})

def test_parse_request_uses_rules_when_complete(llm, settings, term, cfg, monkeypatch):
    complete = AccessRequest.model_validate_json((settings.data_dir / 'requests' / 'R01.json').read_text(encoding='utf-8'))

    def forbidden(*args, **kwargs):
        pytest.fail('Complete rules must never call the LLM')
    monkeypatch.setattr(llm, 'parse_with_llm', forbidden)
    result = parsing.parse_request(complete, term, cfg)
    assert result.source == 'rules' and result.report.complete

def test_parse_request_without_key_reports_needs_review(access_request, term, cfg):
    result = parsing.parse_request(access_request, term, dataclasses.replace(cfg, anthropic_api_key=None))
    assert not result.report.complete and result.source != 'llm'

def test_llm_off_does_not_call(llm, access_request, term, cfg, monkeypatch):
    monkeypatch.setattr(llm, 'parse_with_llm', lambda *a, **k: pytest.fail('off mode'))
    result = parsing.parse_request(access_request, term, dataclasses.replace(cfg, llm_mode='off'))
    assert not result.report.complete

def test_llm_success_exposes_verified_codes_in_staff_report(llm, access_request, term, cfg, valid, monkeypatch):
    original = llm.parse_with_llm
    monkeypatch.setattr(llm, 'parse_with_llm', lambda *args: original(*args, client=FakeClient(valid)))
    result = parsing.parse_request(access_request, term, cfg)
    assert result.source == 'llm' and result.report.complete and (result.llm_purpose is not None)
    assert result.report.mappings[0].table == 'conditions' and result.report.mappings[0].matches
    assert result.report.mappings[0].codes.source == 'llm'
    cached = parsing.parse_request(access_request, term, cfg)
    assert cached.source == 'llm_cache' and cached.report.mappings

def test_missing_codes_warn_staff(llm, access_request, term, cfg, valid, monkeypatch):
    valid['spec']['population'][0]['codes']['prefixes'] = ['Z99999']
    original = llm.parse_with_llm
    monkeypatch.setattr(llm, 'parse_with_llm', lambda *args: original(*args, client=FakeClient(valid)))
    result = parsing.parse_request(access_request, term, cfg)
    assert result.report.mappings[0].warning and (not result.report.mappings[0].matches)
    assert any(('No code' in note for note in result.report.notes))

def test_failure_falls_back_and_reaches_pipeline_staff(llm, access_request, term, cfg, monkeypatch):

    def fail(*args, **kwargs):
        raise llm.LLMError('unavailable')
    monkeypatch.setattr(llm, 'parse_with_llm', fail)
    expected_spec, expected_report = parse_rules(access_request, term)
    result = parsing.parse_request(access_request, term, cfg)
    assert result.spec == expected_spec and result.report.not_understood == expected_report.not_understood
    assert result.source in ('rules', 'none') and result.llm_purpose is None
    service = DeskService(cfg)
    staff = service.process(access_request).staff
    assert any(('LLM' in warning for warning in staff.warnings))
    assert any(('LLM' in note for note in staff.parse_report.notes))

# These cases cover every field where the compiler assigns a fixed clinical table.
_CODE_POSITIONS = [
    "population_condition", "population_medication", "population_observation", "population_encounter",
    "count_condition", "count_medication", "count_observation", "count_encounter",
    "encounter_scope", "mean", "observation_codes",
]


def _code_system_case(valid, position):
    """Build a valid spec and the same shape with a syntactically valid wrong system."""
    output = copy.deepcopy(valid)
    output["spec"] = {"metrics": [{"kind": "count", "name": "n", "label": "Patients"}]}
    kind = position.split("_")[-1]
    system, prefix = {
        "condition": ("icd10", "E11"), "medication": ("atc", "A10"),
        "observation": ("loinc", "2339-0"), "encounter": ("icd10", "J18"),
        "scope": ("icd10", "J18"), "mean": ("loinc", "2339-0"),
        "codes": ("loinc", "2339-0"),
    }[kind]
    codes = {"system": system, "prefixes": [prefix], "label": "Selected term", "source": "llm"}
    spec = output["spec"]
    if position.startswith(("population_", "count_")):
        key = "primary_icd10" if kind == "encounter" else "codes"
        criterion = {"kind": kind, key: codes}
        if position.startswith("population_"):
            spec["population"] = [criterion]
        else:
            spec["metrics"][0]["where"] = [criterion]
    elif position == "encounter_scope":
        spec["unit"] = "encounter"
        spec["encounter_scope"] = {"primary_icd10": codes}
    elif position == "mean":
        spec["metrics"].append({"kind": "mean", "name": "m", "label": "Mean", "codes": codes})
    else:
        spec["observation_codes"] = codes
    correct = copy.deepcopy(output)
    # C is valid in ICD-10 and ATC syntax, so only field-aware validation can reject this.
    codes.update(system="icd10" if system == "atc" else "atc", prefixes=["C"])
    return correct, output


@pytest.mark.parametrize("position", _CODE_POSITIONS)
def test_wrong_code_system_is_retried_once_then_rejected(llm, access_request, term, cfg, valid, position):
    _, wrong = _code_system_case(valid, position)
    client = FakeClient(wrong, wrong)
    with pytest.raises(llm.LLMError):
        llm.parse_with_llm(access_request, term, cfg, client=client)
    assert len(client.calls) == 2
    assert not list(cfg.var_dir.rglob("*.json"))


@pytest.mark.parametrize("position", _CODE_POSITIONS)
def test_cached_wrong_code_system_is_revalidated(llm, access_request, term, cfg, valid, position):
    correct, wrong = _code_system_case(valid, position)
    expected_spec, _, _ = llm.parse_with_llm(access_request, term, cfg, client=FakeClient(correct))
    path = next((cfg.var_dir / "cache" / "llm").glob("*.json"))
    path.write_text(json.dumps(wrong), encoding="utf-8")
    client = FakeClient(correct)
    actual_spec, _, cached = llm.parse_with_llm(access_request, term, cfg, client=client)
    assert not cached and actual_spec == expected_spec
    assert len(client.calls) == 1


def test_wrong_code_system_can_be_corrected_once(llm, access_request, term, cfg, valid):
    correct, wrong = _code_system_case(valid, "population_condition")
    client = FakeClient(wrong, correct)
    spec, _, cached = llm.parse_with_llm(access_request, term, cfg, client=client)
    assert spec.population[0].codes.system == "icd10" and not cached
    assert len(client.calls) == 2
