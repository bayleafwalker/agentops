"""Test 2 (zero-window golden), test 8 (renderer coverage) and STALE."""

import copy
import re
from datetime import timedelta

import pytest

from fakes import FIXTURES, FakeAuthorityClient, fixture
from operator_projection import contract, render_html, render_text
from operator_projection.cell import is_cell
from operator_projection.generate import generate
from operator_projection.sources import Authority
from world import NOW, REGISTRY, TAGS, estate

RESULTS = {"work.project.context": fixture("project-context.json"), "work.read.handoff": {"last_checkpoint": None},
           "work.read.context-candidates": {"candidates": []}}


def document(moves=True, credential=True):
    return generate(estate(moves=moves), Authority(FakeAuthorityClient(results=RESULTS), lambda: credential), REGISTRY, NOW, tags=lambda: TAGS)


def paths(doc: dict) -> set[str]:
    found = {k for k in doc if k != "panels"}
    return found | {f"panels.{p}.{k}" for p, panel in doc["panels"].items() for k in panel}


def moves_block(text: str) -> str:
    return next(block for block in text.split("\n\n") if block.startswith("MOVES")) + "\n"


def test_contract_fields_are_exactly_the_document_fields():
    assert paths(document()) == contract.FIELDS


def test_zero_window_renders_exactly_the_zero_line_and_nothing_more():
    doc = document(moves=False)
    assert moves_block(render_text.render(doc, NOW)) == (FIXTURES / "zero-window.txt").read_text()
    section = next(s for s in re.findall(r"<section>(.*?)</section>", render_html.render(doc, NOW)) if ">MOVES " in s)
    assert re.findall(r"<(\w+)", section) == ["div"] * 7


@pytest.mark.parametrize("field", sorted(contract.FIELDS))
def test_both_renderers_show_every_cell_field(field):
    doc = document()
    *parents, key = field.split(".")
    holder = doc
    for part in parents:
        holder = holder[part]
    if not is_cell(holder[key]):
        pytest.skip("structural field: covered by the contract assertion and the golden")
    changed = copy.deepcopy(doc)
    target = changed
    for part in parents:
        target = target[part]
    target[key] = target[key] | {"kind": "BLIND", "value": None, "reason": f"SENTINEL {field}"}
    assert f"SENTINEL {field}" in render_text.render(changed, NOW)
    assert f"SENTINEL {field}" in render_html.render(changed, NOW)


def test_stale_banner_only_past_stale_after():
    doc = document()
    assert not render_text.render(doc, NOW + timedelta(seconds=1800)).startswith("STALE")
    stale = render_text.render(doc, NOW + timedelta(seconds=1801))
    assert stale.startswith("STALE · generated 30m ago, past 30m")
    assert '<div class="stale">STALE' in render_html.render(doc, NOW + timedelta(hours=3))


def test_blind_pickup_renders_the_blind_token_and_html_escapes():
    doc = document(credential=False)
    text = render_text.render(doc, NOW)
    assert "PICK UP HERE   BLIND(authority.work: no generator credential (work:read, work:project-read))" in text
    doc["panels"]["hazards"]["rows"][0]["detail"] = "<script>x</script>"
    assert "<script>x" not in render_html.render(doc, NOW)
