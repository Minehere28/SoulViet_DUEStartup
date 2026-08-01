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
PRICE_PROPERTIES = (
    "entrance_fee_min",
    "entrance_fee_max",
    "typical_spend_min",
    "typical_spend_max",
    "price_unit",
    "price_source",
    "price_verified_at",
    "price_confidence",
    "price_verification_status",
)


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


def load_and_validate_graph(graph_path):
    graph = torch.load(graph_path, weights_only=False)
    raw_nodes = graph.get("nodes", {})
    nodes = list(
        raw_nodes.values()
        if isinstance(raw_nodes, dict)
        else raw_nodes
    )
    if not nodes:
        raise ValueError("graph.pt does not contain Place nodes")

    missing_ids = [node for node in nodes if not node.get("id")]
    if missing_ids:
        raise ValueError(f"{len(missing_ids)} Place nodes have no id")

    missing_price_fields = {
        field: sum(field not in node for node in nodes)
        for field in PRICE_PROPERTIES
    }
    missing_price_fields = {
        field: count
        for field, count in missing_price_fields.items()
        if count
    }
    if missing_price_fields:
        raise ValueError(
            f"Missing price properties in graph: {missing_price_fields}"
        )

    duplicate_count = len(nodes) - len({node["id"] for node in nodes})
    if duplicate_count:
        raise ValueError(f"graph.pt has {duplicate_count} duplicate Place IDs")

    return graph, {
        "places": len(nodes),
        "estimated_prices": sum(
            node["price_verification_status"] == "estimated"
            for node in nodes
        ),
        "priced_places": sum(
            node["entrance_fee_max"] > 0
            or node["typical_spend_max"] > 0
            for node in nodes
        ),
    }


def import_graph(graph_path, clear=False, batch_size=500):
    graph, validation = load_and_validate_graph(graph_path)
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
                    p.images = row.images,
                    p.entrance_fee_min = row.entrance_fee_min,
                    p.entrance_fee_max = row.entrance_fee_max,
                    p.typical_spend_min = row.typical_spend_min,
                    p.typical_spend_max = row.typical_spend_max,
                    p.price_unit = row.price_unit,
                    p.price_source = row.price_source,
                    p.price_verified_at = row.price_verified_at,
                    p.price_confidence = row.price_confidence,
                    p.price_verification_status =
                        row.price_verification_status
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

        imported_ids = [node["id"] for node in nodes]
        records, _, _ = driver.execute_query(
            """
            MATCH (p:Place)
            WHERE p.id IN $imported_ids
            RETURN count(p) AS imported_places,
                   count(p.price_verification_status) AS price_status_count,
                   sum(
                       CASE WHEN p.entrance_fee_max > 0
                                  OR p.typical_spend_max > 0
                            THEN 1 ELSE 0 END
                   ) AS priced_places,
                   sum(
                       CASE WHEN p.price_verification_status = "estimated"
                            THEN 1 ELSE 0 END
                   ) AS estimated_prices
            """,
            imported_ids=imported_ids,
            database_=database,
        )
        result = dict(records[0])
        result["expected_places"] = validation["places"]
        if result["imported_places"] != validation["places"]:
            raise RuntimeError(
                "Neo4j verification failed: "
                f"expected {validation['places']} imported Place nodes, "
                f"found {result['imported_places']}"
            )
        if result["price_status_count"] != validation["places"]:
            raise RuntimeError(
                "Neo4j verification failed: some Place nodes have no "
                "price_verification_status"
            )
        return result
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
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate graph and price fields without connecting to Neo4j",
    )
    args = parser.parse_args()

    if args.validate_only:
        _, result = load_and_validate_graph(args.graph)
        print(f"Validated Place nodes: {result['places']}")
        print(f"Places with a non-zero price: {result['priced_places']}")
        print(f"Estimated price statuses: {result['estimated_prices']}")
        raise SystemExit(0)

    result = import_graph(args.graph, args.clear, args.batch_size)
    print(f"Neo4j imported Place nodes: {result['imported_places']}")
    print(f"Neo4j places with price status: {result['price_status_count']}")
    print(f"Neo4j places with a non-zero price: {result['priced_places']}")
    print(f"Neo4j estimated price statuses: {result['estimated_prices']}")
