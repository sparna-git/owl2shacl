#!/usr/bin/env python3
"""Offline verification of the owl:onDataRange simple-cardinality rules.

Applies a ruleset's SHACL-AF rules to ``input.ttl`` with pyshacl and reports the
``sh:minCount`` / ``sh:maxCount`` triples produced, so the fix can be checked without
the SHACL Play! web UI or a Java toolchain::

    pip install pyshacl
    python verify.py                    # all flavors
    python verify.py owl2sh-closed      # one flavor

Exit status is 0 when every checked flavor matches its expectation below, 1 otherwise.

Why the expectations differ per flavor
--------------------------------------
The new rules are exact mirrors of the pre-existing ``owl:onClass`` rules, so each one
fires exactly where its sibling fires. In the ``open`` flavor a restriction carrying only
``owl:maxQualifiedCardinality`` produces no count at all -- and that is true for the
*object* property (``Road.junction``, ``owl:onClass``) just as much as for the *data*
property (``Road.speedLimit``, ``owl:onDataRange``). The fixture contains both so the
symmetry is visible rather than looking like a gap in the data-property rules.

No flavor may emit a plain and a qualified count for the same property: the simple rules
and the qualified rules are mutually exclusive by construction, each guarded by
``FILTER EXISTS`` / ``FILTER NOT EXISTS`` on ``?property rdfs:range ?onDataRange``.

``owl2sh-original.ttl`` is deliberately out of scope: it is the unwired historical import
of TopQuadrant's rules, is not one of the three documented flavors, and is not offered by
the CLI or the hosted converter. See the README.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

#: Every count constraint the rules can emit. Plain and qualified are both collected so a
#: property receiving both -- the simple rule and the qualified rule firing on the same
#: restriction -- fails the check instead of passing unnoticed.
COUNT_CONSTRAINTS = ("minCount", "maxCount", "qualifiedMinCount", "qualifiedMaxCount")

#: Counts each flavor is expected to produce, as (property local name, constraint, value).
#: "closed" and "semi-closed" constrain optional properties; "open" does not, for object
#: and data properties alike.
FULL = {
    # Qualification NOT redundant (onDataRange xsd:int narrower than range xsd:decimal):
    # the qualified rule fires, the simple one must not. Same in every flavor.
    ("Road.laneCount", "qualifiedMaxCount", "1"),
    ("Road.laneCount", "qualifiedMinCount", "1"),
    ("Road.junction", "maxCount", "1"),  # optional object property (owl:onClass)
    ("Road.lane", "maxCount", "1"),  # exactly-one object property
    ("Road.lane", "minCount", "1"),
    ("Road.name", "maxCount", "1"),  # exactly-one data property (owl:onDataRange)
    ("Road.name", "minCount", "1"),
    ("Road.speedLimit", "maxCount", "1"),  # optional data property (owl:onDataRange)
    ("Road.width", "minCount", "1"),  # required data property (owl:onDataRange)
}
OPEN = {c for c in FULL if not (c[1] == "maxCount" and c[0] in {"Road.junction", "Road.speedLimit"})}

EXPECTED = {
    "owl2sh-closed": FULL,
    "owl2sh-semi-closed": FULL,
    "owl2sh-open": OPEN,
}


def counts(graph) -> set[tuple[str, str, str]]:
    """Extract (property, constraint, value) for every count constraint in *graph*."""
    from rdflib import URIRef

    sh_path = URIRef("http://www.w3.org/ns/shacl#path")
    found = set()
    for subject, predicate, obj in graph:
        local = str(predicate).split("#")[-1]
        # Qualified counts are collected too: a property that receives both a plain and a
        # qualified count has been hit by the simple and the qualified rule at once, which
        # is the double-firing this check must catch, not hide.
        if local in COUNT_CONSTRAINTS:
            path = graph.value(subject, sh_path)
            found.add((str(path).split("#")[-1].split("/")[-1], local, str(obj)))
    return found


def check(flavor: str) -> bool:
    from pyshacl import validate
    from rdflib import Graph

    data = Graph().parse(HERE / "input.ttl", format="turtle")
    rules = Graph().parse(REPO / f"{flavor}.ttl", format="turtle")
    validate(data, shacl_graph=rules, advanced=True, inplace=True, do_owl_imports=False)

    produced, expected = counts(data), EXPECTED[flavor]
    ok = produced == expected
    print(f"{'PASS' if ok else 'FAIL'}  {flavor}")
    for constraint in sorted(expected - produced):
        print(f"        missing: {constraint}")
    for constraint in sorted(produced - expected):
        print(f"        unexpected: {constraint}")
    return ok


def main(argv: list[str]) -> int:
    flavors = argv[1:] or list(EXPECTED)
    unknown = [f for f in flavors if f not in EXPECTED]
    if unknown:
        print(f"unknown flavor(s): {unknown}; choose from {list(EXPECTED)}", file=sys.stderr)
        return 2
    return 0 if all(check(f) for f in flavors) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
