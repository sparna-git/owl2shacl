#!/usr/bin/env python3
"""Offline verification of the rdfs:range class-or-datatype decision and the sh:in rule.

Applies a ruleset's SHACL-AF rules to ``input.ttl`` with pyshacl and reports the
``sh:in`` / ``sh:datatype`` / ``sh:class`` constraints produced, so the change can be
checked without the SHACL Play! web UI or a Java toolchain::

    pip install pyshacl
    python verify.py                    # all flavors
    python verify.py owl2sh-closed      # one flavor

Exit status is 0 when every checked flavor matches its expectation below, 1 otherwise.

Why every flavor expects the same result
----------------------------------------
Unlike the count constraints in ``../onDataRange-cardinality``, the range decision does not
depend on how a flavor treats optional properties: a property's ``rdfs:range`` yields either
a class constraint or a datatype constraint in all three. The three flavors previously
*disagreed* only because each carried its own hardcoded list of datatype IRIs - ``closed``
omitted ``xsd:double`` while ``open`` and ``semi-closed`` included it, and ``semi-closed``
listed ``xsd:integer`` twice. Testing the range itself removes the divergence, so the
expectation is shared and a future drift between flavors fails the check.

``owl2sh-original.ttl`` is out of scope for the same reason as in the sibling test: it is the
unwired historical import of TopQuadrant's rules, is not one of the three documented flavors,
and is not offered by the CLI or the hosted converter. See the README.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

#: The three constraints that express a property's permitted values, all collected so that a
#: property receiving both sh:class and sh:datatype -- or an sh:in alongside a datatype naming
#: the enumeration -- fails the check instead of passing unnoticed.
RANGE_CONSTRAINTS = ("in", "datatype", "class")

#: Expected constraints, as (property local name, constraint, value). The value for sh:in is
#: the list contents joined with "|", so a truncated or dangling list is visible rather than
#: being reported as a bare node identifier.
EXPECTED_ALL = {
    # the case under test: an enumerated data range becomes sh:in and nothing else. A
    # sh:datatype naming ex:ColourEnum would be violated by "red", which is an xsd:string.
    ("Car.colour", "in", "red|green|blue"),
    # xsd:double was listed as a datatype by open and semi-closed but not by closed
    ("Car.mass", "datatype", "http://www.w3.org/2001/XMLSchema#double"),
    # xsd:nonNegativeInteger was on no flavor's list, so every flavor emitted sh:class
    ("Car.doors", "datatype", "http://www.w3.org/2001/XMLSchema#nonNegativeInteger"),
    # control: already on every list, must be unchanged
    ("Car.name", "datatype", "http://www.w3.org/2001/XMLSchema#string"),
    # control: an object property whose range is a class, must remain sh:class
    ("Car.owner", "class", "http://example.org/ontology/test#Person"),
}

EXPECTED = {
    "owl2sh-closed": EXPECTED_ALL,
    "owl2sh-semi-closed": EXPECTED_ALL,
    "owl2sh-open": EXPECTED_ALL,
}


def range_constraints(graph) -> set[tuple[str, str, str]]:
    """Extract (property, constraint, value) for every range constraint in *graph*."""
    from rdflib import URIRef
    from rdflib.collection import Collection

    sh = "http://www.w3.org/ns/shacl#"
    sh_path = URIRef(sh + "path")
    found = set()
    for subject, predicate, obj in graph:
        local = str(predicate).split("#")[-1]
        if str(predicate) != sh + local or local not in RANGE_CONSTRAINTS:
            continue
        path = graph.value(subject, sh_path)
        if path is None:
            # sh:class also appears on node shapes in the semi-closed flavor; only property
            # shapes are under test here
            continue
        if local == "in":
            value = "|".join(str(item) for item in Collection(graph, obj))
        else:
            value = str(obj)
        found.add((str(path).split("#")[-1].split("/")[-1], local, value))
    return found


def check(flavor: str) -> bool:
    from pyshacl import validate
    from rdflib import Graph

    data = Graph().parse(HERE / "input.ttl", format="turtle")
    rules = Graph().parse(REPO / f"{flavor}.ttl", format="turtle")
    validate(data, shacl_graph=rules, advanced=True, inplace=True, do_owl_imports=False)

    produced, expected = range_constraints(data), EXPECTED[flavor]
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
    # every flavor is checked before returning, rather than short-circuiting, so a
    # divergence between flavors is visible in one run
    results = [check(f) for f in flavors]
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
