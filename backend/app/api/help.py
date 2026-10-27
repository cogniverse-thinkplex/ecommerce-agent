from __future__ import annotations
from collections.abc import Callable
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.help.service import HelpService
from app.support.service import SupportService


class AssistantRequest(BaseModel): conversation_id: str | None = None


def create_help_router(get_help:Callable[[],HelpService],get_support:Callable[[],SupportService])->APIRouter:
    router=APIRouter(prefix="/api/v1/help",tags=["help"])
    def customer(request:Request):
        actor=getattr(request.state,"authenticated_user",None)
        if actor is None or actor.role!="customer": raise HTTPException(403,detail={"code":"forbidden","message":"当前账户不能访问帮助中心。"})
        return actor
    @router.get("/categories")
    def categories(request:Request,service:HelpService=Depends(get_help)):
        customer(request);return {"categories":service.categories()}
    @router.get("/articles")
    def articles(request:Request,category:str|None=None,service:HelpService=Depends(get_help)):
        customer(request);return {"articles":service.articles(category)}
    @router.get("/articles/{policy_id}")
    def article(policy_id:str,request:Request,service:HelpService=Depends(get_help)):
        customer(request)
        try:return service.article(policy_id)
        except KeyError:raise HTTPException(404,detail={"code":"policy_not_found","message":"未找到该政策。"})
    @router.get("/search")
    def search(request:Request,q:str=Query(min_length=1,max_length=200),service:HelpService=Depends(get_help)):
        customer(request);return service.search(q)
    @router.post("/articles/{policy_id}/assistant")
    def assistant(policy_id:str,payload:AssistantRequest,request:Request,help_service:HelpService=Depends(get_help),support:SupportService=Depends(get_support)):
        actor=customer(request);help_service.article(policy_id)
        try:
            conversation=support.get_conversation(payload.conversation_id,actor.user_id) if payload.conversation_id else support.create_conversation(actor.user_id,actor.retail_user_id)
            support.set_policy_context(conversation.conversation_id,actor.user_id,policy_id)
        except KeyError: raise HTTPException(404,detail={"code":"conversation_not_found","message":"未找到该会话。"})
        return {"conversation_id":conversation.conversation_id,"policy_id":policy_id}
    return router
