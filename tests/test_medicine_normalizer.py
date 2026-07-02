from __future__ import annotations

from src.meds.medicine_normalizer import normalize_medicine_mentions


def test_normalize_aspirin_chinese() -> None:
    meds = normalize_medicine_mentions("可以食阿司匹林嗎？")
    assert any(m["canonical_name"] == "aspirin" for m in meds)


def test_normalize_aspirin_hk_variant() -> None:
    meds = normalize_medicine_mentions("可以食亞士匹靈嗎？")
    assert any(m["canonical_name"] == "aspirin" for m in meds)


def test_normalize_asa() -> None:
    meds = normalize_medicine_mentions("Can I take ASA?")
    assert any(m["canonical_name"] == "aspirin" for m in meds)


def test_normalize_panadol() -> None:
    meds = normalize_medicine_mentions("可以食必理痛嗎？")
    assert any(m["canonical_name"] == "paracetamol" for m in meds)


def test_normalize_donepezil_brand() -> None:
    meds = normalize_medicine_mentions("Can I stop Aricept?")
    assert any(m["canonical_name"] == "donepezil" for m in meds)
