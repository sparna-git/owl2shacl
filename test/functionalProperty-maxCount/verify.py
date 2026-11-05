#!/usr/bin/env python3
"""Offline verification of the owl:FunctionalProperty rule.

Applies a ruleset's SHACL-AF rules to ``input.ttl`` with pyshacl and reports the
``sh:minCount`` / ``sh:maxCount`` triples produced::

    pip install pyshacl
    python verify.py                    # all flavors
    python verify.py owl2sh-closed      # one flavor

Exit status is 0 when every checked flavor matches ``EXPECTED``, 1 otherwise.
``owl2sh-original.ttl`` is out of scope, as in ``test/onDataRange-cardinality``.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

#: Counts every flavor is expected to produce, as (property local name, constraint, value).
EXPECTED = {
    ("Road.name", "maxCount", "1"),  # functional, the class restricts another property
    ("Bridge.name", "maxCount", "1"),  # functional, a superclass restricts another property
    ("Junction.name", "maxCount", "1"),  # control: functional, no restriction
    ("Road.length", "maxCount", "1"),  # owl:cardinality 1
    ("Road.length", "minCount", "1"),
}
FLAVORS = ("owl2sh-closed", "owl2sh-semi-closed", "owl2sh-open")


def counts(graph) -> set[tuple[str, str, str]]:
    """Extract (property, constraint, value) for every count constraint in *graph*."""
    from rdflib import URIRef

    sh_path = URIRef("http://www.w3.org/ns/shacl#path")
    found = set()
    for subject, predicate, obj in graph:
        local = str(predicate).split("#")[-1]
        if local in ("minCount", "maxCount"):
            path = graph.value(subject, sh_path)
            found.add((str(path).split("#")[-1], local, str(obj)))
    return found


def check(flavor: str) -> bool:
    from pyshacl import validate
    from rdflib import Graph

    data = Graph().parse(HERE / "input.ttl", format="turtle")
    rules = Graph().parse(REPO / f"{flavor}.ttl", format="turtle")
    validate(data, shacl_graph=rules, advanced=True, inplace=True, do_owl_imports=False)

    produced = counts(data)
    ok = produced == EXPECTED
    print(f"{'PASS' if ok else 'FAIL'}  {flavor}")
    for constraint in sorted(EXPECTED - produced):
        print(f"        missing: {constraint}")
    for constraint in sorted(produced - EXPECTED):
        print(f"        unexpected: {constraint}")
    return ok


def main(argv: list[str]) -> int:
    flavors = argv[1:] or list(FLAVORS)
    unknown = [f for f in flavors if f not in FLAVORS]
    if unknown:
        print(f"unknown flavor(s): {unknown}; choose from {list(FLAVORS)}", file=sys.stderr)
        return 2
    return 0 if all(check(f) for f in flavors) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
