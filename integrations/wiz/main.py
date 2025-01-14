from enum import StrEnum
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from loguru import logger

from wiz.client import WizClient
from port_ocean.context.ocean import ocean
from port_ocean.core.ocean_types import ASYNC_GENERATOR_RESYNC_TYPE


class ObjectKind(StrEnum):
    PROJECT = "project"
    ISSUE = "issue"
    SERVICE_TICKET = "serviceTicket"
    CONTROL = "control"


def init_client() -> WizClient:
    return WizClient(
        ocean.integration_config["wiz_api_url"],
        ocean.integration_config["wiz_client_id"],
        ocean.integration_config["wiz_client_secret"],
        ocean.integration_config["wiz_token_url"],
    )


@ocean.on_resync()
async def on_resync(kind: str) -> ASYNC_GENERATOR_RESYNC_TYPE:
    wiz_client = init_client()

    if kind == ObjectKind.PROJECT:
        async for projects in wiz_client.get_projects():
            logger.info(f"Received {len(projects)} projects")
            yield projects
    else:
        async for _issues in wiz_client.get_issues():
            logger.info(f"Received {len(_issues)} issues")
            if kind == ObjectKind.ISSUE:
                yield _issues
            elif kind == ObjectKind.CONTROL:
                yield [
                    issue["sourceRule"]
                    for issue in _issues
                    if issue.get("sourceRule") is not None
                ]
            elif kind == ObjectKind.SERVICE_TICKET:
                yield [
                    ticket
                    for issue in _issues
                    for ticket in issue.get("serviceTickets", [])
                ]


@ocean.router.post("/webhook")
async def handle_webhook_request(
    data: dict[str, Any], token: Any = Depends(HTTPBearer())
) -> dict[str, Any]:
    if ocean.integration_config["wiz_webhook_verification_token"] != token.credentials:
        raise HTTPException(
            status_code=401,
            detail={
                "ok": False,
                "message": "Wiz webhook token verification failed, ignoring request",
            },
        )

    logger.info(f"Received webhook request: {data}")
    wiz_client = init_client()

    issue = await wiz_client.get_single_issue(data["issue"]["id"])
    await ocean.register_raw(ObjectKind.ISSUE, [issue])

    return {"ok": True}
