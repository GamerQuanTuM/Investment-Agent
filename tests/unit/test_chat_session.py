"""Chat session persistence: Redis-backed (mocked) with an in-memory fallback."""

from __future__ import annotations

from investment_agent.research import chat, chat_session


async def test_state_survives_between_turns_via_redis(fake_redis):
    await chat.chat_turn("s1", "monthly SIP")
    assert "chat:s1" in fake_redis.store
    assert fake_redis.ttls["chat:s1"] == 24 * 60 * 60

    # A different process (empty memory) still sees the conversation through Redis.
    chat_session._memory.clear()
    second = await chat.chat_turn("s1", "7")
    assert second["collected"]["horizon_years"] == 7
    assert second["collected"]["intent"] == "plan_sip_fund"


async def test_falls_back_to_memory_when_redis_is_down(fake_redis):
    fake_redis.down = True
    await chat.chat_turn("s2", "monthly SIP")
    second = await chat.chat_turn("s2", "5")
    assert second["collected"]["horizon_years"] == 5
    assert fake_redis.store == {}


async def test_history_keeps_only_the_last_six_turns(fake_redis):
    for i in range(10):
        await chat.chat_turn("s3", f"what is the weather {i}")
    state = await chat_session.load_session("s3")
    assert len(state["history"]) == 12  # 6 turns = 6 user + 6 assistant messages
    assert state["history"][-2]["text"] == "what is the weather 9"


async def test_reset_clears_redis_and_memory(fake_redis):
    await chat.chat_turn("s4", "monthly SIP")
    await chat.chat_turn("s4", "start over")
    assert "chat:s4" not in fake_redis.store
    assert "s4" not in chat_session._memory


async def test_corrupt_payload_starts_a_fresh_session(fake_redis):
    fake_redis.store["chat:s5"] = "{not json"
    state = await chat_session.load_session("s5")
    assert state == chat_session.new_state()


async def test_sessions_are_isolated(fake_redis):
    await chat.chat_turn("iso-a", "monthly SIP")
    other = await chat_session.load_session("iso-b")
    assert other["intent"] is None
