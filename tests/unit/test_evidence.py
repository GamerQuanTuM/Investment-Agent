from investment_agent.research.evidence import Evidence, EvidenceVerificationResult, SourceType


def test_evidence_model_creation():
    ev = Evidence(
        claim="TCS reported Q3 ROE of 48%",
        source_name="NSE Regulatory Filing",
        source_type=SourceType.COMPANY_FILING,
        confidence=1.0,
    )
    assert ev.source_type == SourceType.COMPANY_FILING
    assert ev.confidence == 1.0
    assert ev.retrieved_at is not None


def test_evidence_verification_result():
    res = EvidenceVerificationResult(
        is_valid=True,
        verified_claims_count=3,
        unsupported_claims_count=0,
        quality_score=1.0,
        status="VERIFIED",
    )
    assert res.is_valid is True
    assert res.status == "VERIFIED"
