"""Export the canonical SoulViet graph from Neo4j to graph.pt.

For the normal local pipeline, prefer scripts/build_graph.py, which builds
graph.pt directly from new_data.csv. This exporter is useful after editing
or exploring data in Neo4j.
"""

import argparse
import os
from pathlib import Path

import torch
from dotenv import load_dotenv
from neo4j import GraphDatabase


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "graph.pt"


def export_graph(output_path):
    load_dotenv(PROJECT_ROOT / ".env")
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    if not all((uri, user, password)):
        raise RuntimeError(
            "Missing NEO4J_URI, NEO4J_USER or NEO4J_PASSWORD in .env"
        )

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            node_result = session.run(
                """
                MATCH (p:Place)
                OPTIONAL MATCH (p)-[:HAS_VIBE]->(v:Vibe)
                OPTIONAL MATCH (p)-[:HAS_TYPE]->(t:Type)
                OPTIONAL MATCH (p)-[:LOCATED_IN]->(r:Region)
                RETURN p, collect(DISTINCT v.name) AS vibes,
                       collect(DISTINCT t.name) AS types,
                       head(collect(DISTINCT r.name)) AS region
                """
            )
            nodes = {}
            for record in node_result:
                props = dict(record["p"])
                place_id = props["id"]
                props["vibes"] = record["vibes"]
                props["types"] = record["types"]
                props["region"] = record["region"] or props.get("region", "")
                nodes[place_id] = props

            near = {place_id: [] for place_id in nodes}
            edge_result = session.run(
                """
                MATCH (a:Place)-[r:NEAR]->(b:Place)
                RETURN a.id AS src, b.id AS dst, r.distance AS distance
                """
            )
            for record in edge_result:
                near.setdefault(record["src"], []).append(
                    {
                        "to": record["dst"],
                        "distance": float(record["distance"]),
                    }
                )
    finally:
        driver.close()

    edge_count = sum(len(neighbors) for neighbors in near.values())
    graph = {
        "metadata": {
            "schema_version": 2,
            "source": "neo4j",
            "node_count": len(nodes),
            "near_edge_count": edge_count,
        },
        "nodes": nodes,
        "edges": {"near": near},
    }
    torch.save(graph, output_path)
    return graph


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = export_graph(args.output)
    print(f"Created: {args.output.resolve()}")
    print(f"Nodes: {result['metadata']['node_count']}")
    print(f"Directed NEAR edges: {result['metadata']['near_edge_count']}")
