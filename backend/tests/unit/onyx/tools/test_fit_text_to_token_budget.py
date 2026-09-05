from onyx.tools.tool_implementations.utils import fit_text_to_token_budget


def _char_tokens(text: str) -> int:
    return len(text)


def test_fit_keeps_text_that_already_fits() -> None:
    assert fit_text_to_token_budget("hello", _char_tokens, 10) == "hello"


def test_fit_truncates_and_keeps_the_footer() -> None:
    text = "abcdefghij" * 20
    fitted = fit_text_to_token_budget(text, _char_tokens, 80)
    assert fitted != text
    assert "output truncated" in fitted
    assert "characters omitted" in fitted
    assert _char_tokens(fitted) <= 80


def test_fit_zero_budget_is_footer_only() -> None:
    fitted = fit_text_to_token_budget("lots of text", _char_tokens, 0)
    assert fitted.startswith("... [output truncated")


def test_history_and_saved_row_share_the_fitted_text() -> None:
    text = '{"tool_result": "' + ("x" * 500) + '"}'
    fitted = fit_text_to_token_budget(text, _char_tokens, 80)
    llm_facing = fitted
    saved_row = fitted
    assert llm_facing == saved_row
    assert "output truncated" in saved_row
    assert _char_tokens(saved_row) <= 80
