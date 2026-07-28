# SoulViet DUE Startup

## Run the API

```powershell
.\myenv\Scripts\Activate.ps1
python -m uvicorn app:app --reload
```

Open Swagger at <http://127.0.0.1:8000/docs>.

Example request for `POST /plan`:

```json
{
  "duration": 2,
  "vibe": "Chữa lành & Yên bình"
}
```

## Rebuild graph.pt directly from the clean CSV

```powershell
python -m scripts.build_graph
```

Defaults:

- Input: `new_data_soulviet/new_data.csv`
- Output: `graph.pt`
- `NEAR` threshold: 2 km

Override the distance threshold when needed:

```powershell
python -m scripts.build_graph --threshold-km 3
```

## Import graph.pt into Neo4j for visualization

Copy `.env.example` to `.env` and set your Neo4j connection values. Then:

```powershell
python -m scripts.import_to_neo4j --clear
```

`--clear` deletes the existing Neo4j graph before importing, ensuring the
database contains exactly the places from the current `graph.pt`. Omit it to
upsert without deleting existing nodes.

Useful Neo4j Browser checks:

```cypher
MATCH (p:Place) RETURN count(p) AS places;
```

```cypher
MATCH ()-[r:NEAR]->() RETURN count(r) AS directed_near_edges;
```

```cypher
MATCH path=(p:Place)-[:HAS_VIBE|HAS_TYPE|NEAR]->()
RETURN path
LIMIT 100;
```

```cypher
MATCH (p:Place)-[:LOCATED_IN]->(r:Region)
RETURN r.name AS region, count(p) AS places
ORDER BY places DESC;
```
