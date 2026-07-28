import argparse
import os
from pathlib import Path

import torch
from dotenv import load_dotenv
from neo4j import GraphDatabase


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRAPH = PROJECT_ROOT / "graph.pt"


def batched(items, size):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def connect():
    load_dotenv(PROJECT_ROOT / ".env")
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    if not all((uri, user, password)):
        raise RuntimeError(
            "Missing NEO4J_URI, NEO4J_USER or NEO4J_PASSWORD in .env"
        )
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    return driver


def import_graph(graph_path, clear=False, batch_size=500):
    graph = torch.load(graph_path, weights_only=False)
    nodes = list(graph["nodes"].values())
    near = [
        {"src": source, **edge}
        for source, neighbors in graph["edges"]["near"].items()
        for edge in neighbors
    ]

    driver = connect()
    try:
        with driver.session() as session:
            if clear:
                session.run("MATCH (n) DETACH DELETE n").consume()

            session.run(
                "CREATE CONSTRAINT place_id IF NOT EXISTS "
                "FOR (p:Place) REQUIRE p.id IS UNIQUE"
            ).consume()
            session.run(
                "CREATE CONSTRAINT vibe_name IF NOT EXISTS "
                "FOR (v:Vibe) REQUIRE v.name IS UNIQUE"
            ).consume()
            session.run(
                "CREATE CONSTRAINT type_name IF NOT EXISTS "
                "FOR (t:Type) REQUIRE t.name IS UNIQUE"
            ).consume()
            session.run(
                "CREATE CONSTRAINT region_name IF NOT EXISTS "
                "FOR (r:Region) REQUIRE r.name IS UNIQUE"
            ).consume()

            for batch in batched(nodes, batch_size):
                session.run(
                    """
                    UNWIND $rows AS row
                    MERGE (p:Place {id: row.id})
                    SET p.google_place_id = row.google_place_id,
                        p.name = row.name,
                        p.type = row.type,
                        p.all_types = row.all_types,
                        p.address = row.address,
                        p.region = row.region,
                        p.lat = row.lat,
                        p.lng = row.lng,
                        p.rating = row.rating,
                        p.review_count = row.review_count,
                        p.operation_hours = row.operation_hours,
                        p.description = row.description,
                        p.activities = row.activities,
                        p.reviews = row.reviews,
                        p.main_image = row.main_image,
                        p.images = row.images
                    FOREACH (vibe IN row.vibes |
                        MERGE (v:Vibe {name: vibe})
                        MERGE (p)-[:HAS_VIBE]->(v)
                    )
                    FOREACH (type IN row.all_types |
                        MERGE (t:Type {name: type})
                        MERGE (p)-[:HAS_TYPE]->(t)
                    )
                    FOREACH (
                        region IN
                        CASE
                            WHEN row.region = "" THEN []
                            ELSE [row.region]
                        END |
                        MERGE (r:Region {name: region})
                        MERGE (p)-[:LOCATED_IN]->(r)
                    )
                    """,
                    rows=batch,
                ).consume()

            for batch in batched(near, batch_size):
                session.run(
                    """
                    UNWIND $rows AS row
                    MATCH (a:Place {id: row.src})
                    MATCH (b:Place {id: row.to})
                    MERGE (a)-[r:NEAR]->(b)
                    SET r.distance = row.distance
                    """,
                    rows=batch,
                ).consume()

            counts = session.run(
                """
                MATCH (p:Place)-[:LOCATED_IN]->(:Region)
                WITH count(DISTINCT p) AS places,
                     count(*) AS located_in
                MATCH ()-[r:NEAR]->()
                RETURN places, located_in, count(r) AS near_edges
                """
            ).single()
            return dict(counts)
    finally:
        driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import canonical graph.pt into Neo4j"
    )
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete all existing Neo4j nodes before importing",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    result = import_graph(args.graph, args.clear, args.batch_size)
    print(f"Neo4j Place nodes: {result['places']}")
    print(f"Neo4j LOCATED_IN relationships: {result['located_in']}")
    print(f"Neo4j directed NEAR edges: {result['near_edges']}")
