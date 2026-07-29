from fastapi import APIRouter, HTTPException, Query

from services.graph_service import GraphService
from services.similarity_service import SimilarityService


router = APIRouter(prefix="/places", tags=["places"])
graph_service = GraphService()
similarity_service = SimilarityService(graph_service)


@router.get("/{place_id}")
def get_place(place_id: str):
    place = graph_service.get_place(place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return place


@router.get("/{place_id}/similar")
def get_similar_places(
    place_id: str,
    top_k: int = Query(default=5, ge=1, le=20),
    same_region: bool = True,
    max_distance_km: float | None = Query(default=None, gt=0, le=100),
    min_score: float = Query(default=0.1, ge=0, le=1),
):
    try:
        return {
            "source_id": place_id,
            "items": similarity_service.find_similar(
                place_id=place_id,
                top_k=top_k,
                same_region=same_region,
                max_distance_km=max_distance_km,
                min_score=min_score,
            ),
        }
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
