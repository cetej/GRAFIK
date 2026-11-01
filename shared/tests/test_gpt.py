"""OpenAI se stejným rozhraním jako Claude: tvar vstupu, cena z usage, pojistka v testech, nedokončená odpověď."""
from types import SimpleNamespace as NS

import pytest

from ngm_shared import claude, gpt


class FakeClient:
    def __init__(self, reply):
        self.reply, self.kwargs = reply, None
        self.responses = NS(create=self.create)

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.reply


def reply(text="{}", status="completed"):
    return NS(output_text=text, model="gpt-6.1-terra-2026-10", status=status, usage=NS(input_tokens=10_000, output_tokens=2_000))


def test_paid_call_is_refused_in_tests():
    with pytest.raises(claude.ClaudeError, match="placené volání"):
        gpt.ask([{"type": "text", "text": "x"}], "s", what="návrhy", model="gpt-6.1-terra")


def test_ask_sends_text_and_image_and_prices_from_usage(monkeypatch):
    client = FakeClient(reply('{"a": 1}'))
    monkeypatch.setenv(claude.LIVE_ENV, "1")
    monkeypatch.setattr(gpt, "_client", lambda: client)
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAA"}}

    answer = gpt.ask([image, {"type": "text", "text": "zadání"}], "systém", what="návrhy", model="gpt-6.1-terra", effort="medium", max_tokens=99)

    assert client.kwargs["instructions"] == "systém" and client.kwargs["reasoning"] == {"effort": "medium"} and client.kwargs["max_output_tokens"] == 99
    assert client.kwargs["input"][0]["content"] == [{"type": "input_image", "image_url": "data:image/png;base64,AAA"}, {"type": "input_text", "text": "zadání"}]
    assert answer.text == '{"a": 1}' and answer.usd == pytest.approx(0.02) and answer.cost()["in"] == 10_000


@pytest.mark.parametrize("text,status", [("kus", "incomplete"), ("", "completed")])
def test_unfinished_reply_is_an_error_that_keeps_the_cost(monkeypatch, text, status):
    monkeypatch.setenv(claude.LIVE_ENV, "1")
    monkeypatch.setattr(gpt, "_client", lambda: FakeClient(reply(text, status)))
    with pytest.raises(claude.ClaudeError) as e:
        gpt.ask([{"type": "text", "text": "x"}], "s", what="návrhy", model="gpt-6.1-terra")
    assert e.value.cost["usd"] == pytest.approx(0.02)


def test_unknown_model_counts_at_the_highest_price():
    assert gpt.usd_for("gpt-nove", 1_000_000, 0) == 2.0
