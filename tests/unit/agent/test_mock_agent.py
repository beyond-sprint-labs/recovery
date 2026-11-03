from app.agent.mock_agent import mock_agent_run


def test_mock_agent_s03_exceeds_discount():

    # Test that the agent detects the excessive discount scenario (S03)
    intent = mock_agent_run("Can I get 40% off?", scenario_id="S03_exceeds_discount")
    assert intent.requested_discount_pct == "40"


def test_mock_agent_natural_language_40_pct():

    # Test that the agent detects 40% via natural language
    intent = mock_agent_run("I need a 40% discount or I can't pay")
    assert intent.requested_discount_pct == "40"


def test_mock_agent_natural_language_pay_partial():

    # Test that the agent detects the intention to pay a portion (300)
    intent = mock_agent_run("I can pay 300 today")
    assert intent.available_now == "300.00"
    assert intent.preferred_installments == 3


def test_mock_agent_empty_intent():

    # Test that it returns an empty intent if it doesn't understand the message
    intent = mock_agent_run("Hello, how are you?")
    assert intent.requested_discount_pct is None
    assert intent.available_now is None
