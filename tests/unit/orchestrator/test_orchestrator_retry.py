from orchestrator.retry import RetryPolicy


def test_retry_policy_respects_limit():
    policy = RetryPolicy(retry_limit=2, backoff_seconds=0.1)
    assert policy.should_retry(1)
    assert policy.should_retry(2)
    assert not policy.should_retry(3)


def test_retry_policy_backoff_is_exponential():
    policy = RetryPolicy(retry_limit=3, backoff_seconds=0.5)
    assert policy.backoff_duration(1) == 0.5
    assert policy.backoff_duration(2) == 1.0
    assert policy.backoff_duration(3) == 2.0
