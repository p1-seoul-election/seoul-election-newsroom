"""Contract v0.1 checks; no repair, official-data inference or approval."""
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import math

IDS = {f"0020260603_SEOUL_C{i:02}" for i in (1, 2, 4, 5, 7)}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def percentage(value, numerator, denominator, code):
    if denominator == 0:
        require(value is None, code)
        return
    require(type(value) in (int, float) and math.isfinite(value)
            and 0 <= value <= 100, code)
    expected = (Decimal(numerator) * 100 / Decimal(denominator)).quantize(
        Decimal('0.000001'), rounding=ROUND_HALF_UP)
    require(Decimal(str(value)) == expected, code)


def validate(event, previous=None):
    require(isinstance(event, dict), 'EVENT_OBJECT_REQUIRED')
    kind = event.get('type')
    require(kind in {'snapshot', 'update', 'status', 'error'}, 'EVENT_TYPE')
    require(isinstance(event.get('run_id'), str) and bool(event['run_id'].strip()), 'RUN_ID')
    require(integer(event.get('seq'), 1), 'SEQ')
    require(event.get('data_mode') == 'MOCK' and event.get('simulated') is True
            and event.get('official_data', False) is False, 'MOCK_ONLY')
    require(event.get('contract_version') == '0.1', 'CONTRACT_VERSION')
    require(event.get('election_id') == '0020260603'
            and event.get('election_type') == 'GOVERNOR', 'ELECTION_ID')
    require(isinstance(event.get('notice'), str) and bool(event['notice'].strip()), 'NOTICE')
    for key in ('event_time', 'emitted_at'):
        try:
            stamp = datetime.fromisoformat(event[key])
            require(stamp.utcoffset() == timedelta(hours=9), 'TIMEZONE')
        except (KeyError, TypeError, ValueError):
            raise ValueError('EVENT_TIME') from None
    require(event.get('contract_status') == 'PROPOSAL_UNIMPLEMENTED', 'CONTRACT_STATUS')
    require(isinstance(event.get('notice'), str) and bool(event['notice'].strip()), 'NOTICE')
    for key in ('event_time', 'emitted_at'):
        require(isinstance(event.get(key), str), key.upper())
        try:
            stamp = datetime.fromisoformat(event[key])
        except ValueError:
            raise ValueError(key.upper()) from None
        require(stamp.utcoffset() == timedelta(hours=9), key.upper())
    ref = event.get('reference')
    require(isinstance(ref, dict), 'REFERENCE_REQUIRED')
    for key in ('source_snapshot_id', 'dataset_version'):
        require(isinstance(ref.get(key), str) and bool(ref[key].strip()), 'REFERENCE_ID')
    require(ref.get('verification_status') in {'PASS', 'FAIL', 'REVIEW_REQUIRED'}, 'REFERENCE_STATE')
    require('results_as_of' in ref and ref['results_as_of'] is None
            and ref.get('results_as_of_precision') == 'UNKNOWN', 'REFERENCE_TIME')
    require(isinstance(ref.get('source_ids'), list) and bool(ref['source_ids'])
            and all(isinstance(x, str) and x.strip() for x in ref['source_ids']), 'SOURCE_IDS')
    require(event.get('state') in {'IDLE', 'RUNNING', 'PAUSED', 'COMPLETED', 'ERROR'}, 'STATE')
    if kind == 'error':
        require(isinstance(event.get('error'), dict), 'ERROR_OBJECT')
        raise ValueError('UPSTREAM_ERROR')
    require(event['state'] != 'ERROR', 'UPSTREAM_ERROR')
    require(ref['verification_status'] != 'FAIL', 'REFERENCE_FAIL')
    if kind == 'status':
        require(isinstance(event.get('reason'), str) and bool(event['reason']), 'STATUS_REASON')
        require(not any(k in event for k in ('regions', 'catalog', 'scope_region_ids')), 'STATUS_WITH_VOTES')
        return
    require(isinstance(event.get('snapshot_id'), str) and bool(event['snapshot_id']), 'SNAPSHOT_ID')
    if kind == 'snapshot':
        require(integer(event.get('sync_cursor_seq'), 1)
                and event['sync_cursor_seq'] >= event['seq'], 'SYNC_CURSOR_SEQ')
    require(event.get('scope_region_ids') == ['SEOUL'], 'SCOPE_UNSUPPORTED')
    require(kind != 'snapshot' or isinstance(event.get('catalog'), dict), 'CATALOG_REQUIRED')
    catalog = event.get('catalog', (previous or {}).get('catalog'))
    require(isinstance(catalog, dict), 'CATALOG_REQUIRED')
    candidates = catalog.get('candidates')
    require(isinstance(candidates, list) and len(candidates) == 5
            and all(isinstance(c, dict) and isinstance(c.get('candidate_id'), str) for c in candidates)
            and {c['candidate_id'] for c in candidates} == IDS, 'CATALOG_CANDIDATES')
    require(isinstance(catalog.get('regions'), list)
            and any(isinstance(r, dict) and r.get('region_id') == 'SEOUL' for r in catalog['regions']), 'CATALOG_REGIONS')
    regions = event.get('regions')
    require(isinstance(regions, list) and len(regions) == 1 and isinstance(regions[0], dict), 'REGIONS')
    r = regions[0]
    require(r.get('region_id') == 'SEOUL', 'REGION_ID')
    require(integer(r.get('target_ballots'), 1)
            and r.get('target_ballots_basis') == 'SCENARIO_FIXED_EDUCATIONAL', 'TARGET')
    for key in ('counted_votes', 'valid_votes', 'invalid_votes'):
        require(integer(r.get(key)), key.upper())
    require(r['counted_votes'] <= r['target_ballots'], 'COUNT_EXCEEDS_TARGET')
    votes = r.get('candidate_votes')
    require(isinstance(votes, list) and len(votes) == 5
            and all(isinstance(c, dict) and isinstance(c.get('candidate_id'), str) for c in votes)
            and {c['candidate_id'] for c in votes} == IDS, 'CANDIDATE_IDS')
    require(all(integer(c.get('votes')) for c in votes), 'CANDIDATE_VOTES')
    require(sum(c['votes'] for c in votes) == r['valid_votes'], 'VALID_SUM')
    require(r['valid_votes'] + r['invalid_votes'] == r['counted_votes'], 'COUNTED_SUM')
    percentage(r.get('count_rate_pct'), r['counted_votes'], r['target_ballots'], 'COUNT_RATE')
    for c in votes:
        require('vote_share_pct' in c, 'VOTE_SHARE_REQUIRED')
        percentage(c['vote_share_pct'], c['votes'], r['valid_votes'], 'VOTE_SHARE')
    if (previous and previous['run_id'] == event['run_id']
            and event['seq'] > previous['seq']):
        old = previous['regions'][0]
        require(r['target_ballots'] == old['target_ballots'], 'TARGET_CHANGED')
        for key in ('counted_votes', 'valid_votes', 'invalid_votes'):
            require(r[key] >= old[key], 'CUMULATIVE_DECREASE')
        old_votes = {c['candidate_id']: c['votes'] for c in old['candidate_votes']}
        require(all(c['votes'] >= old_votes[c['candidate_id']] for c in votes), 'CANDIDATE_DECREASE')
    require(event['state'] != 'COMPLETED' or r['counted_votes'] == r['target_ballots'], 'EARLY_COMPLETED')
