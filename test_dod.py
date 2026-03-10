import traceback

from orchestrator.engine import OrchestratorEngine

engine = OrchestratorEngine(pipelines_dir='pipelines')
try:
    result = engine.run(
        'feature_pipeline',
        {'issue': {'body': 'Implement endpoint and tests'}},
        run_id='it-feature-happy',
    )
    print('Status:', result['status'])
    print('Steps:', list(result.get('steps', {}).keys()))
    if 'dod_extractor' in result.get('steps', {}):
        dod = result['steps']['dod_extractor']
        print('DoD status:', dod.get('status'))
        print('DoD logs:', dod.get('logs'))
        print('DoD artifacts:', dod.get('artifacts'))
except Exception:
    traceback.print_exc()
