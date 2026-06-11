import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from src.mcp.resources.programs import list_programs, get_program
from src.mcp.resources.assets import list_assets_for_program, list_new_assets
from src.mcp.resources.findings import list_findings_for_program, list_findings_by_status
from src.mcp.resources.alerts import get_unseen_alerts
from src.mcp.resources.notes import list_notes_for_program, list_notes_for_asset
from src.mcp.resources.recon_runs import get_latest_recon, get_recon_history
from src.mcp.resources.scores import get_ranked_programs, get_program_score
from src.mcp.resources.exchanges import list_exchanges_for_session
from src.mcp.tools.search import search_assets, summarize_program

server = Server("bug-bounty")


@server.list_resources()
async def list_resources() -> list[types.Resource]:
    return [
        types.Resource(
            uri="bounty://programs",
            name="All Programs",
            description="List all tracked bug bounty programs with their latest scores and recon status",
            mimeType="application/json",
        ),
        types.Resource(
            uri="bounty://alerts/unseen",
            name="Unseen Alerts",
            description="All unread alerts (new assets, score changes, etc.)",
            mimeType="application/json",
        ),
        types.Resource(
            uri="bounty://scores/ranked",
            name="Ranked Programs",
            description="All programs sorted by total score descending",
            mimeType="application/json",
        ),
    ]


@server.read_resource()
async def read_resource(uri: types.AnyUrl) -> str:
    uri_str = str(uri)

    if uri_str == "bounty://programs":
        return list_programs()

    if uri_str == "bounty://alerts/unseen":
        return get_unseen_alerts()

    if uri_str == "bounty://scores/ranked":
        return get_ranked_programs()

    # bounty://programs/{id}
    if uri_str.startswith("bounty://programs/") and "/assets" not in uri_str and "/findings" not in uri_str and "/recon" not in uri_str and "/notes" not in uri_str and "/score" not in uri_str:
        program_id = uri_str.removeprefix("bounty://programs/")
        return get_program(program_id)

    # bounty://programs/{id}/assets
    if uri_str.startswith("bounty://programs/") and uri_str.endswith("/assets"):
        program_id = uri_str.removeprefix("bounty://programs/").removesuffix("/assets")
        return list_assets_for_program(program_id)

    # bounty://programs/{id}/assets/new
    if uri_str.startswith("bounty://programs/") and uri_str.endswith("/assets/new"):
        program_id = uri_str.removeprefix("bounty://programs/").removesuffix("/assets/new")
        return list_new_assets(program_id)

    # bounty://programs/{id}/findings
    if uri_str.startswith("bounty://programs/") and uri_str.endswith("/findings"):
        program_id = uri_str.removeprefix("bounty://programs/").removesuffix("/findings")
        return list_findings_for_program(program_id)

    # bounty://programs/{id}/recon/latest
    if uri_str.startswith("bounty://programs/") and uri_str.endswith("/recon/latest"):
        program_id = uri_str.removeprefix("bounty://programs/").removesuffix("/recon/latest")
        return get_latest_recon(program_id)

    # bounty://programs/{id}/recon/history
    if uri_str.startswith("bounty://programs/") and uri_str.endswith("/recon/history"):
        program_id = uri_str.removeprefix("bounty://programs/").removesuffix("/recon/history")
        return get_recon_history(program_id)

    # bounty://programs/{id}/notes
    if uri_str.startswith("bounty://programs/") and uri_str.endswith("/notes"):
        program_id = uri_str.removeprefix("bounty://programs/").removesuffix("/notes")
        return list_notes_for_program(program_id)

    # bounty://programs/{id}/score
    if uri_str.startswith("bounty://programs/") and uri_str.endswith("/score"):
        program_id = uri_str.removeprefix("bounty://programs/").removesuffix("/score")
        return get_program_score(program_id)

    # bounty://assets/{id}/notes
    if uri_str.startswith("bounty://assets/") and uri_str.endswith("/notes"):
        asset_id = uri_str.removeprefix("bounty://assets/").removesuffix("/notes")
        return list_notes_for_asset(asset_id)

    # bounty://findings/status/{status}
    if uri_str.startswith("bounty://findings/status/"):
        status = uri_str.removeprefix("bounty://findings/status/")
        return list_findings_by_status(status)

    # bounty://hunt/{session_id}/exchanges — Repeater request/response log (redacted)
    if uri_str.startswith("bounty://hunt/") and uri_str.endswith("/exchanges"):
        session_id = uri_str.removeprefix("bounty://hunt/").removesuffix("/exchanges")
        return list_exchanges_for_session(session_id)

    return '{"error": "Unknown resource URI"}'


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_assets",
            description="Search assets by value substring (e.g. domain keyword). Optionally filter by program_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Substring to search for in asset values",
                    },
                    "program_id": {
                        "type": "string",
                        "description": "Optional UUID — restrict search to one program",
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="summarize_program",
            description="Return a high-level summary of a program: asset counts by type, finding counts by severity and status, total payout earned.",
            inputSchema={
                "type": "object",
                "properties": {
                    "program_id": {
                        "type": "string",
                        "description": "UUID of the program to summarize",
                    },
                },
                "required": ["program_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "search_assets":
        result = search_assets(
            query=arguments["query"],
            program_id=arguments.get("program_id"),
        )
    elif name == "summarize_program":
        result = summarize_program(program_id=arguments["program_id"])
    else:
        result = f'{{"error": "Unknown tool: {name}"}}'

    return [types.TextContent(type="text", text=result)]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
