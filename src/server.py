from fastmcp import FastMCP, Context
from typing import Literal
import tiktoken
from modules.utils import (
company_cik_by_ticker,
fetch_selected_company_details_and_filing_accessions,
get_latest_filings_index,
create_base_df_for_sec_company_data,
fetch_all_filings,
preprocess_docs_content,
chunk_docs_content
)


FormType = Literal[
    "10-K", "10-Q", "8-K",
    "S-1", "S-3", "DEF 14A",
    "20-F", "6-K", "4",
    "13D", "13G",
]
enc = tiktoken.encoding_for_model("gpt-4o")

mcp = FastMCP("sec-edgar-mcp-server")

@mcp.tool("edgar-api-latest-filings")
async def company_filings(ctx: Context, company_ticker: str, form:FormType, user_agent: str, cursor:int):
    """
    Fetch the latest SEC filing for a given company and form type,
    returning the filing text in token-safe chunks.

    Args:
        ctx (Context): The MCP request context (provided by FastMCP).
        company_ticker (str): Public ticker symbol, e.g. "MSFT".
        form (FormType): SEC form type to retrieve (e.g. "10-K", "10-Q").
        user_agent (str): User agent string for SEC API requests (SEC requires a valid UA).
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
    cik = await company_cik_by_ticker(ctx, company_ticker, user_agent)
    context_1, context_2, context_3 = await fetch_selected_company_details_and_filing_accessions(ctx, cik, user_agent)
    mapped_index = get_latest_filings_index(context_3)
    sec_base_df = create_base_df_for_sec_company_data(mapping_latest_docs=mapped_index, filings=context_3, cik=cik)
    latest_filings = await fetch_all_filings(ctx=ctx, sec__base_df=sec_base_df, user_agent=user_agent)
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
    sec_filing = preprocess_docs_content(filing['filing_raw']).document.export_to_markdown()
    chunks = chunk_docs_content(sec_filing)
    sec_contex_dict['max_cursor'] = len(chunks) - 1 
    sec_contex_dict[f'filing_chunk_{cursor}'] = chunks[cursor]

    return sec_contex_dict

if __name__ == "__main__":
    mcp.run()
