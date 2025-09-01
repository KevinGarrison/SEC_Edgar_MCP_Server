from fastmcp.server.auth.providers.workos import AuthKitProvider
from starlette.responses import JSONResponse
from fastmcp import FastMCP, Context
from modules.utils import Utils
from typing import Literal
import os

utils = Utils()

authkit_domain = os.getenv("AUTHKIT_DOMAIN", None)
base_url = os.getenv("BASE_URL", None)

AUTHKIT_DOMAIN = authkit_domain.rstrip("/")
BASE_URL = base_url.rstrip("/")

auth_provider = AuthKitProvider(
    authkit_domain=AUTHKIT_DOMAIN,   
    base_url=BASE_URL               
)

FormType = Literal[
    "10-K", "10-Q", "8-K",
    "S-1", "S-3", "DEF 14A",
    "20-F", "6-K", "4",
    "13D", "13G",
]

instructions = """
This MCP server provides a search for the latest SEC filings from the EDGAR API.
"""
mcp = FastMCP('sec_edgar_mcp', instructions=instructions, auth=auth_provider)

app = mcp.streamable_http_app()

async def resource_metadata(request):
    return JSONResponse({
        "resource": BASE_URL,
        "authorization_servers": [AUTHKIT_DOMAIN],  
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["openid", "profile", "email", "offline_access"]
    })

app.add_route("/.well-known/oauth-protected-resource", resource_metadata, methods=["GET"])

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "healthy", "service": "mcp-server"})


@mcp.tool("edgar-api-latest-filings")
async def company_filings(ctx: Context, company_ticker: str, form:FormType, cursor:int, user_agent:str):
    """
    Fetch the latest SEC filing for a given company and form type,
    returning the filing text in token-safe chunks.

    Args:
        ctx (Context): The MCP request context (provided by FastMCP).
        company_ticker (str): Public ticker symbol, e.g. "MSFT".
        form (FormType): SEC form type to retrieve (e.g. "10-K", "10-Q").
        user_agent (str): User agent string for SEC API requests (SEC requires a valid UA with email).
        cursor (int): The index of the chunk to return. 
                      Chunks allow large filings to be retrieved piece by piece.

    Returns:
        dict: Dictionary containing:
            - company_cik (str): SEC CIK identifier for the company.
            - filing_accession (str): Accession number of the filing.
            - filing_report_date (str): Report date of the filing.
            - filing_form (str): The SEC form type.
            - company_context_1, company_context_2 (dict): Extra company metadata.
            - filing_filename (str): The SEC’s filing filename.
            - max_cursor (int): Maximum valid cursor index for this filing.
            - filing_chunk_{cursor} (str): The text of the requested filing chunk.
    """
    cik = await utils.company_cik_by_ticker(ctx, company_ticker, user_agent)
    context_1, context_2, context_3 = await utils.fetch_selected_company_details_and_filing_accessions(ctx, cik, user_agent)
    mapped_index = utils.get_latest_filings_index(context_3)
    sec_base_df = utils.create_base_df_for_sec_company_data(mapping_latest_docs=mapped_index, filings=context_3, cik=cik)
    latest_filings = await utils.fetch_all_filings(ctx=ctx, sec__base_df=sec_base_df, user_agent=user_agent)
    sec_base_df['filing_raw'] = latest_filings
    selected_form = sec_base_df[sec_base_df['form'] == form]
    filing = selected_form.iloc[0]
    sec_contex_dict = dict()
    sec_contex_dict['company_cik'] = cik
    sec_contex_dict['filing_accession'] = filing['accession_number']
    sec_contex_dict['filing_report_date'] = filing['report_date']
    sec_contex_dict['filing_form'] = filing['form']
    sec_contex_dict['company_context_1'] = context_1
    sec_contex_dict['company_context_2'] = context_2
    sec_contex_dict['filing_filename'] = filing['docs']
    sec_filing = utils.preprocess_docs_content(filing['filing_raw']).document.export_to_markdown()
    chunks = utils.chunk_docs_content(sec_filing)
    sec_contex_dict['max_cursor'] = len(chunks) - 1 
    sec_contex_dict[f'filing_chunk_{cursor}'] = chunks[cursor]

    return sec_contex_dict


