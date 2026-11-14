"""The LLM agent loop, driven by a scripted provider so it runs offline."""

import json

import pytest

from shopgym.agents.llm import LLMAgent, ScriptedProvider, parse_reply
from shopgym.env.env import ShopGymEnv
from shopgym.harness.runner import run_episode
from shopgym.tasks.registry import load_tasks

pytestmark = pytest.mark.e2e
TASK = load_tasks()["newsletter-subscribe"]


def test_parse_reply_finds_the_json_object_inside_prose():
    reply = 'I will type the email now.\n{"type": "type", "element": "e3", "text": "a@b.test"}\nThanks.'
    assert parse_reply(reply) == {"type": "type", "element": "e3", "text": "a@b.test"}


def test_parse_reply_passes_unparseable_text_through():
    assert parse_reply("I think I should click things.") == "I think I should click things."


def test_scripted_llm_completes_a_task(live_server, tmp_path):
    # Element ids are deterministic for a given seed, so the script can name them up front.
    with ShopGymEnv(live_server["base_url"], live_server["data_dir"]) as probe:
        first = probe.reset(TASK.id)
        email = first.find("textbox", "Email address").id
        button = first.find("button", "Subscribe").id
    replies = [
        json.dumps({"type": "type", "element": email, "text": TASK.params["email"]}),
        json.dumps({"type": "click", "element": button}),
        json.dumps({"type": "finish", "answer": ""}),
    ]
    agent = LLMAgent(ScriptedProvider(replies), mode="text")
    result = run_episode(agent, TASK, base_url=live_server["base_url"], data_dir=live_server["data_dir"],
                         out_dir=tmp_path / "llm", seed=TASK.seed)
    assert result["success"] and result["steps"] == 3


def test_screenshot_mode_sends_the_image(live_server):
    seen = []

    class Recording(ScriptedProvider):
        def complete(self, system, messages):
            seen.append(messages[-1]["content"])
            return json.dumps({"type": "finish", "answer": ""})

    with ShopGymEnv(live_server["base_url"], live_server["data_dir"]) as env:
        obs = env.reset(TASK.id)
        agent = LLMAgent(Recording([]), mode="screenshot")
        agent.start(TASK, obs, env.initial_db)
        agent.act(obs)
    content = seen[0]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/png"
    assert content[1]["type"] == "text"
