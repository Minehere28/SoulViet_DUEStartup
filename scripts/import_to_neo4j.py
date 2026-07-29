import argparse
import json
import os
from pathlib import Path

import torch
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable


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
    try:
        driver.verify_connectivity()
    except ServiceUnavailable as error:
        driver.close()
        raise RuntimeError(
            f"Cannot connect to Neo4j at {uri}. "
            "Start the Neo4j Desktop instance and try again."
        ) from error
    return driver


def import_graph(graph_path, clear=False, batch_size=500):
    graph = torch.load(graph_path, weights_only=False)
    nodes = []
    for node in graph["nodes"].values():
        serialized = dict(node)
        serialized["opening_hours_json"] = json.dumps(
            node.get("opening_hours", {}),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        serialized.pop("opening_hours", None)
        nodes.append(serialized)
    near = [
        {"src": source, **edge}
        for source, neighbors in graph["edges"]["near"].items()
        for edge in neighbors
    ]

    driver = connect()
    try:
        database = os.getenv("NEO4J_DATABASE", "neo4j")

        if clear:
            driver.execute_query(
                "MATCH (n) DETACH DELETE n",
                database_=database,
            )

        driver.execute_query(
                "CREATE CONSTRAINT place_id IF NOT EXISTS "
                "FOR (p:Place) REQUIRE p.id IS UNIQUE",
                database_=database,
            )
        driver.execute_query(
                "CREATE CONSTRAINT vibe_name IF NOT EXISTS "
                "FOR (v:Vibe) REQUIRE v.name IS UNIQUE",
                database_=database,
            )
        driver.execute_query(
                "CREATE CONSTRAINT type_name IF NOT EXISTS "
                "FOR (t:Type) REQUIRE t.name IS UNIQUE",
                database_=database,
            )
        driver.execute_query(
                "CREATE CONSTRAINT region_name IF NOT EXISTS "
                "FOR (r:Region) REQUIRE r.name IS UNIQUE",
                database_=database,
            )
        driver.execute_query(
                "CREATE CONSTRAINT activity_name IF NOT EXISTS "
                "FOR (a:Activity) REQUIRE a.name IS UNIQUE",
                database_=database,
            )

        for batch in batched(nodes, batch_size):
            driver.execute_query(
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
                    p.opening_hours_json = row.opening_hours_json,
                    p.opening_hours_status = row.opening_hours_status,
                    p.opening_hours_needs_review =
                        row.opening_hours_needs_review,
                    p.opening_hours_verification_status =
                        row.opening_hours_verification_status,
                    p.visit_duration_minutes =
                        row.visit_duration_minutes,
                    p.visit_duration_source = row.visit_duration_source,
                    p.visit_duration_confidence =
                        row.visit_duration_confidence,
                    p.description = row.description,
                    p.activities = row.activities,
                    p.activity_categories = row.activity_categories,
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
                FOREACH (activity IN row.activity_categories |
                    MERGE (a:Activity {name: activity})
                    MERGE (p)-[:SUPPORTS_ACTIVITY]->(a)
                )
                """,
                rows=batch,
                database_=database,
            )

        for batch in batched(near, batch_size):
            driver.execute_query(
                """
                UNWIND $rows AS row
                MATCH (a:Place {id: row.src})
                MATCH (b:Place {id: row.to})
                MERGE (a)-[r:NEAR]->(b)
                SET r.distance = row.distance
                """,
                rows=batch,
                database_=database,
            )

        records, _, _ = driver.execute_query(
            """
            MATCH (p:Place)
            WITH count(p) AS places
            MATCH ()-[located:LOCATED_IN]->()
            WITH places, count(located) AS located_in
            MATCH ()-[activity:SUPPORTS_ACTIVITY]->()
            WITH places, located_in,
                 count(activity) AS supports_activity
            MATCH ()-[r:NEAR]->()
            RETURN places, located_in, supports_activity,
                   count(r) AS near_edges
            """,
            database_=database,
        )
        return dict(records[0])
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
    print(
        "Neo4j SUPPORTS_ACTIVITY relationships: "
        f"{result['supports_activity']}"
    )
    print(f"Neo4j directed NEAR edges: {result['near_edges']}")
