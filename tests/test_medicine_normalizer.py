from __future__ import annotations

from src.meds.medicine_normalizer import normalize_medicine_mentions


def _canonical_names(text: str) -> list[str]:
    return [mention.canonical_name for mention in normalize_medicine_mentions(text)]


def test_aspirin_chinese_alias_normalizes_to_aspirin() -> None:
    assert "aspirin" in _canonical_names("阿司匹林")


def test_aspirin_cantonese_alias_normalizes_to_aspirin() -> None:
    assert "aspirin" in _canonical_names("亞士匹靈")


def test_asa_normalizes_to_aspirin() -> None:
    assert "aspirin" in _canonical_names("ASA")


def test_panadol_chinese_alias_normalizes_to_paracetamol() -> None:
    assert "paracetamol" in _canonical_names("必理痛")


def test_aricept_normalizes_to_donepezil() -> None:
    assert "donepezil" in _canonical_names("Aricept")

