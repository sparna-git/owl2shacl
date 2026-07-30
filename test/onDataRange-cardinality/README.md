# Proof: `owl:onDataRange` qualified cardinality → `sh:minCount` / `sh:maxCount`

This folder is a self-contained regression proof for the fix that adds the
**data-property** (`owl:onDataRange`) counterparts of the existing
**object-property** (`owl:onClass`) *simple* cardinality rules.

## The bug

Each ruleset already collapses an **object-property** qualified cardinality
restriction to a plain `sh:minCount` / `sh:maxCount` when the `owl:onClass`
equals the property's `rdfs:range` (rules
`owlMaxQualifiedCardinalityOnClass2shMaxCount`,
`owlMinQualifiedCardinalityOnClass2shMinCount`,
`owlQualifiedCardinalityOnClass2shMinMaxCount`).

For **data properties** the rulesets only had the *qualified* `onDataRange`
variants (`FILTER NOT EXISTS { ?property rdfs:range ?onDataRange }`) and **no
simple variant**. So a required datatype attribute expressed as

```turtle
[ a owl:Restriction ;
  owl:onProperty ex:Road.name ;
  owl:qualifiedCardinality 1 ;
  owl:onDataRange xsd:string ]
```

produced a property shape with `sh:datatype xsd:string` **but no count** — the
`minCount`/`maxCount` was silently dropped.

## The fix

Three new rules per ruleset, exact mirrors of the `owl:onClass` simple rules
with `owl:onClass` → `owl:onDataRange`:

| New rule | Fires on | Emits |
|----------|----------|-------|
| `owlMaxQualifiedCardinalityOnDataRange2shMaxCount` | `owl:maxQualifiedCardinality` + `owl:onDataRange` == range | `sh:maxCount` |
| `owlMinQualifiedCardinalityOnDataRange2shMinCount` | `owl:minQualifiedCardinality` + `owl:onDataRange` == range | `sh:minCount` |
| `owlQualifiedCardinalityOnDataRange2shMinMaxCount` | `owl:qualifiedCardinality` + `owl:onDataRange` == range | `sh:minCount` + `sh:maxCount` |

Each is guarded by `FILTER EXISTS { ?property rdfs:range ?onDataRange }`, exactly
like its `owl:onClass` sibling, and each is wired into the `ClassShape`
`sh:rule` list right after its qualified `onDataRange` sibling. The pre-existing
qualified `onDataRange` rules keep their `FILTER NOT EXISTS` guard, so there is
no double-firing.

## Standards basis

- **OWL 2 Web Ontology Language, Structural Specification and Functional-Style
  Syntax (2nd ed.), Sec. 8.5 "Data Property Cardinality Restrictions"** — a data
  property cardinality restriction is qualified by a *data range*, exactly as an
  object property cardinality restriction (Sec. 8.3) is qualified by a *class*.
- **OWL 2 Mapping to RDF Graphs, Sec. 3.2** — a qualified data property
  cardinality restriction maps to `owl:onDataRange`, mirroring `owl:onClass` for
  object properties. Emitting `owl:onClass` on a datatype is invalid OWL 2 DL.
- **SHACL Core, Sec. 4.6 (`sh:minCount` / `sh:maxCount`)** — count constraints
  restrict the number of value nodes independent of their type; combined with
  the sibling `sh:datatype` they express the OWL 2 data-property QCR.

The generator [ShapeChange](https://github.com/ShapeChange/ShapeChange) emits
these `owl:onDataRange` qualified restrictions (see
[ShapeChange PR #756](https://github.com/ShapeChange/ShapeChange/pull/756)),
which is what surfaced this gap.

## Files

- `input.ttl` — OWL input: three data properties (`owl:onDataRange`) plus one
  object property control (`owl:onClass`). Datatypes are chosen from the
  ruleset's `rdfs:range` allow-list (`xsd:string`, `xsd:integer`) so the *only*
  before/after delta is the presence of the counts.
- `expected/owl2sh-closed.ttl` — expected `closed`-flavor output **after** the
  fix. The three data-property shapes gain `sh:minCount`/`sh:maxCount`; the
  object-property `lane` shape is unchanged.

## How to reproduce

Use SHACL Play! (the maintainer's own tool):

- **Online:** <https://shacl-play.sparna.fr/play/convert> — upload `input.ttl`,
  choose the *closed* flavor, convert.
- **CLI:** `shaclplay owl2shacl --input input.ttl --output out.ttl` with the
  `closed` ruleset from this repo.

**Before** the fix the three data-property shapes have `sh:datatype` but no
count. **After** the fix they gain the counts shown in
`expected/owl2sh-closed.ttl`. The object-property `lane` shape is identical in
both. The `semi-closed` and `open` flavors behave the same for these
constraints; `original` behaves the same but additionally `owl:imports`
`http://datashapes.org/dash`, so it requires network access to run.

## Reproducing offline

`verify.py` applies a ruleset's rules to `input.ttl` with
[pyshacl](https://github.com/RDFLib/pySHACL) and checks the resulting
`sh:minCount` / `sh:maxCount` triples, so the fix can be re-verified without the
SHACL Play! web UI or a Java toolchain:

```bash
pip install pyshacl
python test/onDataRange-cardinality/verify.py                 # all checkable flavors
python test/onDataRange-cardinality/verify.py owl2sh-closed   # one flavor
```

It exits non-zero on any mismatch, so it can be dropped into CI as-is. Current result:

```
PASS  owl2sh-closed
PASS  owl2sh-semi-closed
PASS  owl2sh-open
```

### Per-flavor expectations, and why they differ

`input.ttl` pairs every data-property case with its object-property sibling:

| Restriction | Data property (`owl:onDataRange`) | Object property (`owl:onClass`) |
|---|---|---|
| `owl:qualifiedCardinality 1` | `Road.name` | `Road.lane` |
| `owl:minQualifiedCardinality 1` | `Road.width` | — |
| `owl:maxQualifiedCardinality 1` | `Road.speedLimit` | `Road.junction` |
| `owl:qualifiedCardinality 1`, datatype **narrower** than the range | `Road.laneCount` | — |

`Road.laneCount` covers the other direction of the mutual exclusion: its `owl:onDataRange`
(`xsd:int`) is narrower than its `rdfs:range` (`xsd:decimal`), so the qualification is not
redundant, the *qualified* rule fires and the simple rule must stay silent. Together with
the redundant cases above, that pins both guards: a property may never receive a plain and
a qualified count for the same restriction.

In `closed` and `semi-closed` every pair produces the same counts. In `open`, a
restriction carrying only `owl:maxQualifiedCardinality` produces no count — and that holds
for `Road.junction` (`owl:onClass`, pre-existing behaviour) exactly as for
`Road.speedLimit` (`owl:onDataRange`, added here). The new rules are therefore faithful
mirrors of their siblings in all three flavors, which is the point of the contribution;
the `open` flavor's treatment of maximum-only restrictions is pre-existing and unchanged.

### A missing guard in `owl2sh-open` and `owl2sh-original`

Adding the simple rules surfaced a pre-existing asymmetry in two of the four rulesets. In
`closed` and `semi-closed` the *qualified* `owl:onDataRange` rules carry
`FILTER NOT EXISTS { ?property rdfs:range ?onDataRange }`, mirroring their `owl:onClass`
siblings. In `open` and `original` that line was absent from the three `onDataRange`
qualified rules, while their `onClass` siblings had it.

On its own that was harmless: with no simple `onDataRange` rule to compete with, the
qualified rule was the only one that could fire. Adding the simple rules makes it a defect —
both fire on the same restriction, so a property gets `sh:minCount` **and**
`sh:qualifiedMinCount`:

```
owl2sh-open, before the guard fix:
    ('Road.name', 'maxCount', '1')          ('Road.name', 'qualifiedMaxCount', '1')
    ('Road.name', 'minCount', '1')          ('Road.name', 'qualifiedMinCount', '1')
    ('Road.width', 'minCount', '1')         ('Road.width', 'qualifiedMinCount', '1')
```

This contribution therefore also adds the missing `FILTER NOT EXISTS` to those three rules
in `owl2sh-open.ttl` and `owl2sh-original.ttl`, so all four rulesets are consistent and the
simple and qualified rules remain mutually exclusive everywhere. `verify.py` collects
qualified counts as well as plain ones, so a regression here fails the check.

### Why `owl2sh-original.ttl` is not touched

`owl2sh-original.ttl` is the unwired historical import of TopQuadrant's original rules. It
is not one of the project's flavors: the repository README documents *"This comes in 3
flavors"* (open, semi-closed, closed), the `shacl-play` CLI's `owl2shacl` command accepts
only `CLOSED`, `SEMICLOSED` and `OPEN`, the hosted converter offers the same three, and no
code in the `sparna-git` organisation references the file.

Changing a ruleset that nothing consumes and no available tool can execute would add
unverifiable code, so this contribution leaves it alone. Say the word if you would rather
keep it in sync and it can be added back.

### Cross-checked against the released tool

The behaviour this contribution changes is reproducible with `shacl-play` 0.12.2
(`shacl-play-app-0.12.2-onejar.jar`, `owl2shacl -i input.ttl -o out.ttl -s <style>`) on the
fixture in this folder. The shipped rules lose data-property cardinality — and the two
flavors do not even agree with each other:

| `input.ttl` property | `-s CLOSED` (0.12.2) | `-s OPEN` (0.12.2) |
|---|---|---|
| `Road.name` (data, qualification redundant) | `sh:datatype` only — **count lost** | `sh:datatype` + `sh:qualifiedMinCount`/`MaxCount` |
| `Road.width` (data, min only) | `sh:datatype` only | `sh:datatype` + `sh:qualifiedMinCount` |
| `Road.speedLimit` (data, max only) | `sh:datatype` only | `sh:datatype` + `sh:qualifiedMaxCount` |
| `Road.lane`, `Road.junction` (object) | `sh:minCount`/`sh:maxCount` | `sh:minCount`/`sh:maxCount` |
| `Road.laneCount` (data, qualification meaningful) | `sh:qualifiedMinCount`/`MaxCount` | same |

`CLOSED` drops the constraint entirely, while `OPEN` emits a *qualified* constraint for a
qualification that carries no information — because its qualified rules lack the
`FILTER NOT EXISTS` guard that `CLOSED`'s have. After this contribution both emit the plain
`sh:minCount` / `sh:maxCount`, exactly as the `owl:onClass` siblings already do.
