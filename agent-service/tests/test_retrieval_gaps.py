"""Gap taxonomy for post-baseline retrieval failures."""

from clinician_agent.profile_assembly import apply_retrieval_limitation, assemble_profile
from clinician_agent.retrieval.supplemental import PostBaselineRetrievalOutcome
from clinician_agent.schemas import Profile


def _minimal_profile() -> Profile:
    return assemble_profile(
        patient_id="P001",
        as_of=__import__("datetime").date(2026, 9, 24),
        inventory=[],
        records={},
        inventory_complete=True,
        inventory_empty=True,
    )


def test_historical_comparison_failure_emits_prior_result_unavailable():
    outcome = PostBaselineRetrievalOutcome(historical_comparison_failed=True)
    profile = apply_retrieval_limitation(_minimal_profile(), outcome)
    codes = {gap.code for gap in profile.gaps}
    assert profile.status == "incomplete"
    assert "prior_result_unavailable" in codes
    assert "retrieval_limited" not in codes


def test_adaptive_supplemental_failure_emits_retrieval_limited():
    outcome = PostBaselineRetrievalOutcome(adaptive_supplemental_failed=True)
    profile = apply_retrieval_limitation(_minimal_profile(), outcome)
    codes = {gap.code for gap in profile.gaps}
    assert profile.status == "incomplete"
    assert "retrieval_limited" in codes
    assert "prior_result_unavailable" not in codes
