from fastapi import APIRouter, Depends, Query

from app.help.service import HelpService


def create_rag_router(get_service) -> APIRouter:
    router=APIRouter(prefix="/api/v1/rag",tags=["rag"])

    @router.get("/status")
    def status(service: HelpService=Depends(get_service)):
        documents=service.unit.policy_documents.list_enabled()
        chunks=service.unit.policy_chunks.list_enabled()
        return {
            "model": service.retrieval.model_name,
            "dense_available": service.retrieval.dense_available,
            "document_count": len(documents),
            "chunk_count": len(chunks),
            "categories": service.categories(),
            "retrieval": "BGE + BM25 + RRF(k=60)",
        }

    @router.get("/debug")
    def debug(q: str=Query(min_length=1,max_length=300),service: HelpService=Depends(get_service)):
        return service.search(q)

    return router
