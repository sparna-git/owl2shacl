# Proof: `rdfs:range` datatypes → `sh:datatype`, and `owl:oneOf` → `sh:in`

This folder is a self-contained regression proof for three related defects in the
`rdfs:range` handling: datatype ranges that received `sh:class`, enumerated data ranges whose
permitted values were dropped entirely, and enumerations written as OWL 2 datatype
definitions, which received an `sh:datatype` that no value satisfies.

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
Syntax, 2nd ed., Sec. 7.4), which RDF writes as an `rdfs:Datatype` with `owl:oneOf` over
literals, often directly on the named datatype — has no representation in the output at all.
No rule reads `owl:oneOf`, so the permitted values are lost and the shape says nothing about
them.

On the same ontology, 55 `rdfs:Datatype` declarations carrying 290 literals produced **zero**
`sh:in` constraints. Combined with defect 1, every enumeration-typed property instead received
`sh:class` naming the datatype: 81 constraints that reject all of their own permitted values.

### 3. An enumeration written as a datatype definition was not recognised

OWL 2 gives a named datatype its value space with a datatype definition,
`DatatypeDefinition( DT DataOneOf( ... ) )` (Structural Specification, Sec. 9.4), and OWL 2 DL
requires one for every datatype that is neither `rdfs:Literal` nor in the OWL 2 datatype map
(Sec. 11.2). In RDF, the named datatype is `owl:equivalentClass` to an anonymous
`rdfs:Datatype` that carries the `owl:oneOf` list (Mapping to RDF Graphs, Sec. 2.1, Table 1):

```turtle
ex:FuelEnum a rdfs:Datatype ;
    owl:equivalentClass [ a rdfs:Datatype ; owl:oneOf ( "petrol" "diesel" "electric" ) ] .
```

The rules looked for `owl:oneOf` only on the range itself. For this form, `owlOneOf2shIn` found
nothing, and the guard in `rdfsRange2shClassOrDatatype` did not apply, so the property received
`sh:datatype ex:FuelEnum`, which every permitted value violates, and no `sh:in`.

The defects share one code path, which is why they are proved together.

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

It also gains a guard, so an enumerated range is left to the new rule. Emitting `sh:datatype`
naming the enumeration would be worse than emitting nothing: the permitted values are plain
literals, so `sh:datatype ex:ColourEnum` is violated by `"red"` itself.

```sparql
FILTER NOT EXISTS {
  { ?range owl:oneOf ?enumeratedValues }
  UNION
  { ?range owl:equivalentClass ?enumeratedRange .
    ?enumeratedRange a rdfs:Datatype ; owl:oneOf ?enumeratedValues . }
} .
```

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
  { ?range owl:oneOf ?permittedValues }
  UNION
  { ?range owl:equivalentClass ?dataRange .
    ?dataRange a rdfs:Datatype ; owl:oneOf ?permittedValues . }
  ?permittedValues rdf:rest* ?listNode .
  ?listNode rdf:first ?value ;
            rdf:rest ?remainder .
}
```

The two branches find the list on the range itself, and on the `rdfs:Datatype` that the range
is `owl:equivalentClass` to, which a datatype definition writes as an anonymous node. Both
rules use the same two branches, so a range that `owlOneOf2shIn` turns into `sh:in` is always
one that `rdfsRange2shClassOrDatatype` leaves alone.

`owl:equivalentClass` is followed only to an `rdfs:Datatype`. A class enumerated through
`owl:equivalentClass`, `C owl:equivalentClass [ a owl:Class ; owl:oneOf ( ... ) ]`
(ObjectOneOf, Structural Specification, Sec. 8.1.4), is a class whose members are individuals,
so a property ranging over it keeps `sh:class`; `Car.size` is the control for this. Only the
direction with the datatype as subject is read, because that is the only one the OWL 2 mapping
reads as a datatype definition (Mapping to RDF Graphs, Sec. 3.2.5, Table 16).

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
- **OWL 2 Structural Specification and Functional-Style Syntax (2nd ed.), Sec. 7.4
  "Enumeration of Literals"** — `DataOneOf` enumerates at least one literal; mapped to RDF as
  an anonymous `rdfs:Datatype` with `owl:oneOf` (Mapping to RDF Graphs, Sec. 2.1, Table 1, and
  Sec. 3.2.4, Table 12).
- **OWL 2 Structural Specification, Sec. 9.4 "Datatype Definitions" and Sec. 11.2** — a named
  datatype receives a data range through `DatatypeDefinition`, which OWL 2 DL requires for
  every datatype that is neither `rdfs:Literal` nor in the OWL 2 datatype map; mapped to RDF as
  `owl:equivalentClass` from the datatype to the data range (Mapping to RDF Graphs, Sec. 2.1,
  Table 1), and read back only in that direction (Sec. 3.2.5, Table 16).
- **OWL 2 Structural Specification, Sec. 8.1.4 "Enumeration of Individuals"** — `ObjectOneOf`
  is a class expression, so a class defined as equivalent to one is a class.

## Files

- `input.ttl` — eight properties on one class: an enumerated datatype in the three RDF forms
  of an enumeration of literals — `owl:oneOf` on the named range, a datatype definition, and an
  anonymous range (the cases under test) — `xsd:double` (on two flavors' lists but not
  `closed`'s), `xsd:nonNegativeInteger` (on no flavor's list), `xsd:string` (on every list, so
  a control that must not change), and two object properties, one whose range is a class and
  one whose range is a class enumerated through `owl:equivalentClass` (controls that must
  remain `sh:class`). All reached through `rdfs:domain`, so the only rules under test are the
  range rules.
- `expected/owl2sh-closed.ttl` — expected `closed`-flavor output after the fix.
- `verify.py` — offline check with pyshacl.

## How to reproduce

Use SHACL Play! (the maintainer's own tool):

- **Online:** <https://shacl-play.sparna.fr/play/convert> — upload `input.ttl`, choose a
  flavor, convert.
- **CLI:** `shaclplay owl2shacl -i input.ttl -o out.ttl --rules <ruleset>`

The output went through three states:

1. **Before the structural range decision**, `Car.colour`, `Car.fuel`, `Car.doors` and — in
   `closed` only — `Car.mass` carry `sh:class`, and `Car.gear` carries nothing.
2. **With it, before datatype definitions were read**, `Car.colour` and `Car.gear` carry
   `sh:in`, but `Car.fuel` carries `sh:datatype ex:FuelEnum`.
3. **Now**, `Car.colour`, `Car.fuel` and `Car.gear` carry `sh:in` with their literals, and
   `Car.doors` and `Car.mass` carry `sh:datatype`.

`Car.name`, `Car.owner` and `Car.size` are identical in all three.

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

With the three ruleset files as they were in state 1, all three fail, and the output shows the
flavor divergence directly — `closed` additionally loses `Car.mass`:

```
FAIL  owl2sh-closed
        missing: ('Car.colour', 'in', 'red|green|blue')
        missing: ('Car.doors', 'datatype', '...#nonNegativeInteger')
        missing: ('Car.fuel', 'in', 'petrol|diesel|electric')
        missing: ('Car.gear', 'in', 'neutral|drive|reverse')
        missing: ('Car.mass', 'datatype', '...#double')
        unexpected: ('Car.colour', 'class', '...#ColourEnum')
        unexpected: ('Car.doors', 'class', '...#nonNegativeInteger')
        unexpected: ('Car.fuel', 'class', '...#FuelEnum')
        unexpected: ('Car.mass', 'class', '...#double')
FAIL  owl2sh-semi-closed
        missing: ('Car.colour', 'in', 'red|green|blue')
        missing: ('Car.doors', 'datatype', '...#nonNegativeInteger')
        ...
FAIL  owl2sh-open
        (same as semi-closed)
```

In state 2, all three fail on `Car.fuel` alone, with the `sh:in` missing and
`sh:datatype ex:FuelEnum` unexpected. Removing the datatype-definition branch from the guard
alone gives only the unexpected `sh:datatype`; removing it from `owlOneOf2shIn` alone gives only
the missing `sh:in`. Following `owl:equivalentClass` to any `owl:oneOf`, not only to an
`rdfs:Datatype`, fails `Car.size`, which then carries `sh:in` over the individuals instead of
`sh:class`.

`verify.py` collects `sh:in`, `sh:datatype` and `sh:class` together, so a property receiving
two of them — for instance an `sh:in` alongside an `sh:datatype` naming the enumeration —
fails the check rather than passing unnoticed. It resolves each `sh:in` to its literal values,
so a dangling or truncated list is a failure rather than an opaque node identifier. It also
fails a property shape with more than one `sh:in` or `sh:datatype`, of which SHACL allows at
most one (SHACL Core, Sec. 4.8.3 and 4.1.2).

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
there is no fixture here that would exercise them, and the sibling test's README sets the
precedent that a ruleset change nothing can execute should not be added blind. Say the word and
they can be brought in line with a fixture of their own.

The datatype-definition form is read only where an enumeration reaches `sh:in`, through
`rdfs:range`, and only one step deep. No fixture here exercises the following, so they are
left as they are:

- an `owl:onDataRange` that differs from the range gives `sh:qualifiedValueShape
  [ sh:datatype DT ]`, and `owl:allValuesFrom DT` gives `sh:class DT` next to the `sh:in`, for
  both forms of an enumeration;
- an alias of a defined datatype, `DT2 owl:equivalentClass DT`, is not followed and gives
  `sh:datatype DT2`;
- an empty list, `owl:oneOf ()`, gives neither `sh:in` nor `sh:datatype`. OWL 2 has no empty
  `DataOneOf` (Sec. 7.4). On the range itself this was already so. In a datatype definition it
  is new: the definition used to give `sh:datatype DT`.

A datatype defined in any other way, for instance by a `DatatypeRestriction`, still receives
`sh:datatype DT`. No literal that OWL 2 permits satisfies it: a defined datatype has an empty
lexical space, so OWL 2 allows no literal typed with it (Structural Specification, Sec. 9.4).

A range with more than one `owl:oneOf` list — directly and through a datatype definition, or
through two definitions — receives one `sh:in` per list, and `verify.py` reports the repeated
`sh:in` as a failure. Such a range is outside OWL 2 DL: a datatype has at most one definition
(Sec. 11.2), and the OWL 2 mapping reads no data range from `owl:oneOf` on a named datatype
(Sec. 3.2.4, Table 12).

A class with `owl:oneOf` directly on it, `C a owl:Class ; owl:oneOf ( ... )`, which the OWL 2
mapping reads as `ObjectOneOf` for compatibility with OWL 1 DL (Sec. 3.2.5, Table 18), has
received `sh:in` over its individuals since the rules first read `owl:oneOf`, and still does.
A class enumerated through `owl:equivalentClass` keeps `sh:class`. This change leaves both as
they are.

`owl2sh-original.ttl` is untouched for the reason given in `../onDataRange-cardinality/README.md`:
it is the unwired historical import of TopQuadrant's rules, is not one of the three documented
flavors, and is offered by neither the CLI nor the hosted converter.
