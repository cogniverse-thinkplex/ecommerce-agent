from __future__ import annotations
from collections.abc import Callable
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from app.auth.models import AuthenticatedUser
from app.auth.service import AuthService
from app.orders.models import OrderDetail, OrderIndex
from app.orders.service import OrderNotFoundError
from app.support.service import SupportService

class OrderAssistantRequest(BaseModel): conversation_id: str | None = None
class OrderAssistantResponse(BaseModel): conversation_id: str; order_id: str

def create_orders_router(get_auth_service: Callable[[], AuthService], get_support_service: Callable[[], SupportService]) -> APIRouter:
    router=APIRouter(prefix="/api/v1/orders",tags=["orders"])
    def actor(request:Request)->AuthenticatedUser:
        value=getattr(request.state,"authenticated_user",None)
        if value is None or value.role!="customer": raise HTTPException(403,detail={"code":"forbidden","message":"当前账户不能访问订单中心。"})
        return value
    def orders(service:AuthService):
        if service.orders is None: raise HTTPException(409,detail={"code":"orders_unavailable","message":"订单服务暂不可用。"})
        return service.orders
    @router.get("",response_model=OrderIndex)
    def index(request:Request,status:Literal["all","pending","shipped","delivered","cancelled"]="all",service:AuthService=Depends(get_auth_service)): return orders(service).list_orders(actor(request),status)
    @router.get("/{order_id}",response_model=OrderDetail)
    def detail(order_id:str,request:Request,service:AuthService=Depends(get_auth_service)):
        try:return orders(service).get_order(actor(request),order_id)
        except OrderNotFoundError:raise HTTPException(404,detail={"code":"order_not_found","message":"未找到该订单。"})
    @router.post("/{order_id}/assistant",response_model=OrderAssistantResponse)
    def assistant(order_id:str,payload:OrderAssistantRequest,request:Request,auth:AuthService=Depends(get_auth_service),support:SupportService=Depends(get_support_service)):
        customer=actor(request)
        try: orders(auth).get_order(customer,order_id)
        except OrderNotFoundError: raise HTTPException(404,detail={"code":"order_not_found","message":"未找到该订单。"})
        try:
            conversation=support.get_conversation(payload.conversation_id,customer.user_id) if payload.conversation_id else support.create_conversation(customer.user_id,customer.retail_user_id)
            support.set_order_context(conversation.conversation_id,customer.user_id,order_id)
        except KeyError: raise HTTPException(404,detail={"code":"conversation_not_found","message":"未找到该会话。"})
        return OrderAssistantResponse(conversation_id=conversation.conversation_id,order_id=order_id)
    return router
