# `owl:FunctionalProperty` → `sh:maxCount 1`

## The bug

`owlFunctionalProperty2shMaxCount1` gives a functional property `sh:maxCount 1`, "unless
there is an OWL cardinality restriction". Its guard did not say on which property:

```sparql
FILTER NOT EXISTS {
  $this rdfs:subClassOf* ?class .
  ?class rdfs:subClassOf ?restriction .
  ?restriction a owl:Restriction .
  ?restriction owl:maxCardinality|owl:cardinality ?any .
}
```

So a class, or any of its superclasses, with an `owl:cardinality` or `owl:maxCardinality`
restriction on *any* property took `sh:maxCount 1` away from *all* its functional
properties, with nothing else setting a count on them.

## The fix

In the three flavors, the guard now matches only a restriction on the same property:

```sparql
  ?restriction owl:onProperty ?property .
```

`owl2sh-original.ttl` is left alone, as in `test/onDataRange-cardinality`.

## Files

- `input.ttl`: `Road` has `owl:cardinality 1` on `Road.length`, and the functional
  `Road.name`; its subclass `Bridge` has the functional `Bridge.name`; `Junction`, with no
  restriction, has the functional `Junction.name` as a control.
- `verify.py`: applies a flavor's rules with pyshacl and checks every `sh:minCount` and
  `sh:maxCount` produced.

```bash
pip install pyshacl
python test/functionalProperty-maxCount/verify.py
```

```
PASS  owl2sh-closed
PASS  owl2sh-semi-closed
PASS  owl2sh-open
```

Before the fix, all three flavors fail the same way, and the control passes:

```
FAIL  owl2sh-closed
        missing: ('Bridge.name', 'maxCount', '1')
        missing: ('Road.name', 'maxCount', '1')
```
