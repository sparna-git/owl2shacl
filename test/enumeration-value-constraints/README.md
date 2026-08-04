# Proof: `rdfs:range` datatypes → `sh:datatype`, and `owl:oneOf` → `sh:in`

This folder is a self-contained regression proof for two related defects in the
`rdfs:range` handling: datatype ranges that received `sh:class`, and enumerated data
ranges whose permitted values were dropped entirely.

## The bug

### 1. A hardcoded list decided what counts as a datatype

`rdfsRange2shClassOrDatatype` chose between `sh:datatype` and `sh:class` by matching the
range against a fixed list of IRIs:

```sparql
BIND (
  IF(
    (?range IN (xsd:boolean, xsd:string, xsd:date, xsd:dateTime, xsd:integer, xsd:float, xsd:duration, xsd:anyURI, rdf:langString)),
    sh:datatype,
    sh:class
  ) AS ?parameter) .
```

Anything outside that list became `sh:class` — including most XML Schema built-ins and every
`rdfs:Datatype`. That constraint can never be satisfied. SHACL Core, Sec. 4.1.1:

> For each value node that is either a literal, or a non-literal that is not a SHACL instance
> of `$class` in the data graph, there is a validation result with the value node as
> `sh:value`.

A literal value node always produces a validation result for `sh:class`. So a property whose
range is `xsd:double` received a constraint that rejects every conforming value.

**The three flavors did not even agree with each other**, which is how this surfaced:

| Ruleset | `xsd:double` on the list? | Note |
|---|---|---|
| `owl2sh-closed` | **no** | so every `xsd:double` property got `sh:class` |
| `owl2sh-semi-closed` | yes | but lists `xsd:integer` twice |
| `owl2sh-open` | yes | |

On one real ontology of 238 classes, the `closed` flavor emitted `sh:class xsd:double` **241
times**, plus 20 more for `xsd:nonNegativeInteger`, `xsd:int`, `xsd:positiveInteger` and
`xsd:negativeInteger`.

### 2. `owl:oneOf` on a data range was dropped

An enumerated data range — OWL 2's `DataOneOf` (Structural Specification and Functional-Style
Syntax, 2nd ed., Sec. 7.4), written as an `rdfs:Datatype` with `owl:oneOf` over literals — has
no representation in the output at all. No rule reads `owl:oneOf`, so the permitted values are
lost and the shape says nothing about them.

On the same ontology, 55 `rdfs:Datatype` declarations carrying 290 literals produced **zero**
`sh:in` constraints. Combined with defect 1, every enumeration-typed property instead received
`sh:class` naming the datatype: 81 constraints that reject all of their own permitted values.

The two defects are one code path, which is why they are fixed and proved together.

## The fix

**`rdfsRange2shClassOrDatatype`** decides structurally instead of by list:

```sparql
BIND (
  IF(
    (EXISTS { ?range a rdfs:Datatype } || STRSTARTS(STR(?range), "http://www.w3.org/2001/XMLSchema#") || ?range = rdf:langString),
    sh:datatype,
    sh:class
  ) AS ?parameter) .
```

A range is a datatype when it is declared as one, when it is an XML Schema built-in, or when
it is `rdf:langString`. This removes the divergence between flavors rather than reconciling
three lists, and it extends automatically to datatypes nobody enumerated.

It also gains a guard, `FILTER NOT EXISTS { ?range owl:oneOf ?enumeratedValues }`, so an
enumerated range is left to the new rule. Emitting `sh:datatype` naming the enumeration would
be worse than emitting nothing: the permitted values are plain literals, so
`sh:datatype ex:ColourEnum` is violated by `"red"` itself.

**`owlOneOf2shIn`** (new) turns the enumerated range into `sh:in` (SHACL Core, Sec. 4.8.3):

```sparql
CONSTRUCT {
  ?propertyShape sh:in ?permittedValues .
  ?listNode rdf:first ?value ;
            rdf:rest ?remainder .
}
WHERE {
  { $this sh:property ?propertyShape . }
  ?propertyShape sh:path ?property .
  ?property rdfs:range ?range .
  ?range owl:oneOf ?permittedValues .
  ?permittedValues rdf:rest* ?listNode .
  ?listNode rdf:first ?value ;
            rdf:rest ?remainder .
}
```

The list triples are re-asserted deliberately. Constructing only `?propertyShape sh:in
?permittedValues` reuses the list node from the input ontology, and the shapes output does not
carry that ontology's `rdf:first`/`rdf:rest` triples — so `sh:in` would point at a list that
is not in the file. `rdf:rest*` walks the list and re-states it, which was verified by
resolving every produced `sh:in` back to its literals rather than by inspecting the node
identifiers.

## Standards basis

- **SHACL Core, Sec. 4.1.1 (`sh:class`)** — a literal value node always yields a validation
  result, so `sh:class` cannot express a datatype range.
- **SHACL Core, Sec. 4.1.2 (`sh:datatype`)** — the value node's datatype must equal the given
  IRI, which is the correct constraint for a datatype range.
- **SHACL Core, Sec. 4.8.3 (`sh:in`)** — restricts value nodes to an enumerated list, which is
  the only Core component that can express `DataOneOf`.
- **OWL 2 Structural Specification and Functional-Style Syntax (2nd ed.), Sec. 7.4 "Data Ranges"**
  — `DataOneOf` enumerates literals; mapped to RDF as `rdfs:Datatype` with `owl:oneOf`
  (Mapping to RDF Graphs, Sec. 2).

## Files

- `input.ttl` — five properties on one class: an enumerated data range (the case under test),
  `xsd:double` (on two flavors' lists but not `closed`'s), `xsd:nonNegativeInteger` (on no
  flavor's list), `xsd:string` (on every list, so a control that must not change), and an
  object property whose range is a class (a control that must remain `sh:class`). All reached
  through `rdfs:domain`, so the only rule under test is the range rule.
- `expected/owl2sh-closed.ttl` — expected `closed`-flavor output after the fix.
- `verify.py` — offline check with pyshacl.

## How to reproduce

Use SHACL Play! (the maintainer's own tool):

- **Online:** <https://shacl-play.sparna.fr/play/convert> — upload `input.ttl`, choose a
  flavor, convert.
- **CLI:** `shaclplay owl2shacl -i input.ttl -o out.ttl --rules <ruleset>`

**Before** the fix, `Car.colour`, `Car.doors` and — in `closed` only — `Car.mass` carry
`sh:class`. **After**, `Car.colour` carries `sh:in ( "red" "green" "blue" )` and the other two
carry `sh:datatype`. `Car.name` and `Car.owner` are identical in both.

## Reproducing offline

```bash
pip install pyshacl
python test/enumeration-value-constraints/verify.py                 # all three flavors
python test/enumeration-value-constraints/verify.py owl2sh-closed   # one flavor
```

It exits non-zero on any mismatch, so it can be dropped into CI as-is. Current result:

```
PASS  owl2sh-closed
PASS  owl2sh-semi-closed
PASS  owl2sh-open
```

Reverting only the three ruleset files makes all three fail, and the output shows the flavor
divergence directly — `closed` additionally loses `Car.mass`:

```
FAIL  owl2sh-closed
        missing: ('Car.colour', 'in', 'red|green|blue')
        missing: ('Car.doors', 'datatype', '...#nonNegativeInteger')
        missing: ('Car.mass', 'datatype', '...#double')
        unexpected: ('Car.colour', 'class', '...#ColourEnum')
        unexpected: ('Car.doors', 'class', '...#nonNegativeInteger')
        unexpected: ('Car.mass', 'class', '...#double')
FAIL  owl2sh-semi-closed
        missing: ('Car.colour', 'in', 'red|green|blue')
        missing: ('Car.doors', 'datatype', '...#nonNegativeInteger')
        ...
FAIL  owl2sh-open
        (same as semi-closed)
```

`verify.py` collects `sh:in`, `sh:datatype` and `sh:class` together, so a property receiving
two of them — for instance an `sh:in` alongside an `sh:datatype` naming the enumeration —
fails the check rather than passing unnoticed. It resolves each `sh:in` to its literal values,
so a dangling or truncated list is a failure rather than an opaque node identifier.

### Why all three flavors share one expectation

Unlike the count constraints proposed in [#7](https://github.com/sparna-git/owl2shacl/pull/7), the range decision does not
depend on how a flavor treats optional properties. The flavors differed here only because each
carried its own list of datatype IRIs. Testing the range itself removes the divergence, so the
expectation is shared and any future drift between flavors fails the check.

### Scope

Three further rules — `owlSomeValuesFromAllValuesFrom2dashHasValueWithClass`,
`owlSomeValuesFromIRI2dashHasValueWithClass` and `owlAllValuesFrom2shClassOrDatatype` — carry
the same hardcoded list against `?someValuesFrom` / `?allValuesFrom`. They are left unchanged:
the ontology that surfaced this uses neither `owl:someValuesFrom` nor `owl:allValuesFrom`, so
there is no fixture here that would exercise them, and a ruleset change that nothing here can
execute should not be added blind. Say the word and they can be brought in line with a fixture
of their own.

`owl2sh-original.ttl` is untouched: it is the unwired historical import of TopQuadrant's rules,
is not one of the three documented flavors (the README documents open, semi-closed and closed),
and is offered by neither the `shacl-play` CLI nor the hosted converter. Changing a ruleset that
nothing consumes and no available tool can execute would add unverifiable code.
