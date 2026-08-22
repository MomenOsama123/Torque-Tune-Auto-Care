import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from state_graph.db import get_connection

from state_graph.graphs.purchase_order_graph import (
    build_graph as build_purchase_order_graph,
    record_manager_decision as record_po_manager_decision,
    record_supplier_reply as record_po_supplier_reply,
)

from state_graph.graphs.inventory_approval_graph import (
    build_graph as build_inventory_graph,
    record_manager_decision as record_inventory_manager_decision,
)

from state_graph.graphs.warranty_graph import (
    build_graph as build_warranty_graph,
    record_manager_decision as record_warranty_manager_decision,
    record_supplier_reply as record_warranty_supplier_reply,
)

from state_graph.tickets import (
    list_tickets,
    mark_investigating,
    resolve_ticket,
)

app = FastAPI(title="Torque Tune API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PurchaseOrderRequest(BaseModel):
    thread_id: str
    user_id: int


class PurchaseOrderManagerDecisionRequest(BaseModel):
    approved: bool


class PurchaseOrderSupplierReplyRequest(BaseModel):
    decision: str
    note: str = ""


class InventoryRequest(BaseModel):
    thread_id: str
    user_id: int
    part_id: int
    quantity: int
    action: str
    reason: str


class InventoryManagerDecisionRequest(BaseModel):
    approved: bool | None = None
    revised_quantity: int | None = None


class WarrantyRequest(BaseModel):
    thread_id: str
    user_id: int
    part_id: int
    inventory_log_id: int
    claim_reason: str = ""


class WarrantyManagerDecisionRequest(BaseModel):
    approved: bool


class WarrantySupplierReplyRequest(BaseModel):
    decision: str
    note: str = ""


class ResolveTicketRequest(BaseModel):
    resolution_note: str


class ChatRequest(BaseModel):
    message: str
    agent: str = "general"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest):
    message = request.message.strip()

    if not message:
        return {"reply": "Please enter a message.", "agent": request.agent}

    try:
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        mcp_root = root / "mcp-server"
        agent_root = root / "agent"

        for path in (str(root), str(mcp_root), str(agent_root)):
            if path not in sys.path:
                sys.path.insert(0, path)

        import server

        result = server.mcp._tools["search_company_knowledge"](message)

        return {
            "reply": result.get(
                "answer",
                "I couldn't find a grounded answer for that request.",
            ),
            "agent": request.agent,
            "grounded": result.get("grounded", False),
            "sources": result.get("sources", []),
        }

    except Exception as exc:
        return {
            "reply": f"Backend error: {type(exc).__name__}: {exc}",
            "agent": request.agent,
            "error": True,
        }


@app.post("/graphs/purchase-order/invoke")
def invoke_purchase_order(request: PurchaseOrderRequest):
    compiled = build_purchase_order_graph().compile()
    result = compiled.invoke(request.thread_id, {"user_id": request.user_id})
    return {
        "thread_id": result.thread_id,
        "status": result.status,
        "node_name": result.node_name,
        "state": result.state,
    }


@app.post("/graphs/purchase-order/threads/{thread_id}/manager-decision")
def purchase_order_manager_decision(
    thread_id: str,
    request: PurchaseOrderManagerDecisionRequest,
):
    result = record_po_manager_decision(thread_id, request.approved)
    return {
        "thread_id": result.thread_id,
        "status": result.status,
        "node_name": result.node_name,
        "state": result.state,
    }


@app.post("/webhooks/supplier-po-response/{thread_id}")
def purchase_order_supplier_response(
    thread_id: str,
    request: PurchaseOrderSupplierReplyRequest,
):
    result = record_po_supplier_reply(thread_id, request.decision, request.note)
    return {
        "thread_id": result.thread_id,
        "status": result.status,
        "node_name": result.node_name,
        "state": result.state,
    }


@app.post("/graphs/inventory/invoke")
def invoke_inventory(request: InventoryRequest):
    compiled = build_inventory_graph().compile()
    result = compiled.invoke(
        request.thread_id,
        {
            "user_id": request.user_id,
            "part_id": request.part_id,
            "quantity": request.quantity,
            "action": request.action,
            "reason": request.reason,
        },
    )
    return {
        "thread_id": result.thread_id,
        "status": result.status,
        "node_name": result.node_name,
        "state": result.state,
    }


@app.post("/graphs/inventory/threads/{thread_id}/manager-decision")
def inventory_manager_decision(
    thread_id: str,
    request: InventoryManagerDecisionRequest,
):
    result = record_inventory_manager_decision(
        thread_id,
        approved=request.approved,
        revised_quantity=request.revised_quantity,
    )
    return {
        "thread_id": result.thread_id,
        "status": result.status,
        "node_name": result.node_name,
        "state": result.state,
    }


@app.post("/graphs/warranty/invoke")
def invoke_warranty(request: WarrantyRequest):
    compiled = build_warranty_graph().compile()
    result = compiled.invoke(
        request.thread_id,
        {
            "user_id": request.user_id,
            "part_id": request.part_id,
            "inventory_log_id": request.inventory_log_id,
            "claim_reason": request.claim_reason,
        },
    )
    return {
        "thread_id": result.thread_id,
        "status": result.status,
        "node_name": result.node_name,
        "state": result.state,
    }


@app.post("/graphs/warranty/threads/{thread_id}/manager-decision")
def warranty_manager_decision(
    thread_id: str,
    request: WarrantyManagerDecisionRequest,
):
    result = record_warranty_manager_decision(thread_id, request.approved)
    return {
        "thread_id": result.thread_id,
        "status": result.status,
        "node_name": result.node_name,
        "state": result.state,
    }


@app.post("/webhooks/supplier-response/{thread_id}")
def warranty_supplier_response(
    thread_id: str,
    request: WarrantySupplierReplyRequest,
):
    result = record_warranty_supplier_reply(
        thread_id, request.decision, request.note
    )
    return {
        "thread_id": result.thread_id,
        "status": result.status,
        "node_name": result.node_name,
        "state": result.state,
    }


@app.get("/hitl")
def get_hitl_tasks():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                c.id,
                c.thread_id,
                c.graph_name,
                c.node_name,
                c.status,
                c.state_json,
                c.created_at
            FROM Checkpoints c
            INNER JOIN (
                SELECT thread_id, MAX(id) AS max_id
                FROM Checkpoints
                GROUP BY thread_id
            ) latest ON c.id = latest.max_id
            WHERE c.status = 'paused_hitl'
            ORDER BY c.id DESC
            """
        ).fetchall()
    finally:
        conn.close()

    tasks = []
    for row in rows:
        state = json.loads(row["state_json"])
        tasks.append(
            {
                "id": row["thread_id"],
                "thread_id": row["thread_id"],
                "graph": row["graph_name"],
                "node": row["node_name"],
                "status": row["status"],
                "reason": state.get("_interrupt_reason"),
                "payload": state.get("_interrupt_payload"),
                "created_at": row["created_at"],
                "state": state,
            }
        )

    return {"tasks": tasks}


@app.get("/tickets")
def get_tickets(status: str | None = None):
    return {"tickets": list_tickets(status=status)}


@app.post("/tickets/{ticket_id}/investigating")
def investigate_ticket(ticket_id: int):
    mark_investigating(ticket_id)
    return {"ticket_id": ticket_id, "status": "investigating"}


@app.post("/tickets/{ticket_id}/resolve")
def resolve_ticket_endpoint(
    ticket_id: int,
    request: ResolveTicketRequest,
):
    resolve_ticket(ticket_id, request.resolution_note)
    return {"ticket_id": ticket_id, "status": "resolved"}
