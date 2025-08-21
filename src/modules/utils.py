from fastmcp import Context
import httpx
import pandas as pd
from typing import Tuple, Union
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import DocumentStream
from langchain_text_splitters import MarkdownTextSplitter
from io import BytesIO

async def company_cik_by_ticker(
    ctx: Context, company_ticker: str, user_agent: str
) -> Union[Tuple[str, str, str], dict]:
    """
    Look up SEC CIK, ticker, and title for a given stock ticker.

    Downloads the SEC master ticker catalog
    (https://www.sec.gov/files/company_tickers.json) and returns a tuple
    with the padded CIK, ticker, and company title.

    Args:
        ctx: FastMCP execution context (for logging).
        company_ticker: Equity ticker symbol (case-insensitive).
        user_agent: SEC requires a descriptive User-Agent string
            (e.g. "Your Name your.email@example.com").

    Returns:
        tuple(str, str, str): On success:
            - cik: 10-digit zero-padded CIK
            - ticker: Stock ticker (uppercase)
            - title: Company name
        dict: On failure, an error payload like:
            {"error": "Ticker not found", "ticker": "<input>", "status": 404}
    """
    if not user_agent:
        ctx.warning("Provide a correct user agent e-mail!")

    headers = {"User-Agent": user_agent}
    tkr = company_ticker.strip().upper()

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get("https://www.sec.gov/files/company_tickers.json", headers=headers)
        ctx.info(f"SEC status: {r.status_code}")
        r.raise_for_status()

        df = pd.DataFrame(r.json()).T
        match = df[df["ticker"].str.upper() == tkr]

        if match.empty:
            return {"error": "Ticker not found", "ticker": company_ticker, "status": 404}

        row = match.iloc[0].to_dict()

        try:
            cik = f"{int(row['cik_str']):010d}"
        except Exception:
            ctx.warning("cik_str not an int; using raw value")
            cik = str(row.get("cik_str"))

        return (cik, row["ticker"], row["title"])
    
    
async def fetch_selected_company_details_and_filing_accessions(
    ctx: Context,
    cik: str | int,
    user_agent: str
) -> tuple[dict[str, any], dict[str, any], dict[str, any]]:
    """
    Fetch company metadata and filing accessions from the SEC EDGAR submissions API.

    This function queries the SEC submissions endpoint for the given company CIK,
    extracts key metadata fields, and returns them alongside the full ``filings`` block.

    Args:
        ctx: FastMCP context object used for logging warnings/info.
        user_agent: A descriptive User-Agent string required by the SEC 
            (e.g. "Your Name your.email@example.com").
        cik: Company CIK (string or int). Should be zero-padded to 10 digits
            when constructing the URL.

    Returns:
        tuple(dict, dict, dict):
            - first_meta_data_dict: Core company-level fields:
                ``name``, ``tickers``, ``exchanges``, ``sicDescription``,
                ``description``, ``website``, ``fiscalYearEnd``.
            - secondary_meta_data_dict: Supplemental fields:
                ``stateOfIncorporation``, ``stateOfIncorporationDescription``,
                ``insiderTransactionForOwnerExists``, 
                ``insiderTransactionForIssuerExists``, ``category``, ``addresses``.
            - filings: The full ``filings`` sub-dictionary from the SEC response,
                containing ``recent`` and ``files`` arrays.

        On error, returns three empty dictionaries: ``({}, {}, {})``.

    Raises:
        httpx.HTTPStatusError: If the SEC responds with 4xx/5xx.
        httpx.RequestError: For network errors or timeouts.
        Exception: Any other unexpected errors are caught and logged
            via ``ctx.warning`` before returning empty dicts.

    Notes:
        - The SEC requires a valid User-Agent header; requests without one
          may be rejected (HTTP 403).
        - This function performs network I/O asynchronously and should be awaited.
    """

    try:
        headers = {'User-Agent': user_agent}

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f'https://data.sec.gov/submissions/CIK{cik}.json',
                headers=headers,
                timeout = None
            )
            response.raise_for_status()
            filing_dict = response.json()

        if filing_dict:
            important_keys = [
                "name", "tickers", "exchanges", "sicDescription",
                "description", "website", "fiscalYearEnd"
            ]

            secondary_keys = [
                "stateOfIncorporation", "stateOfIncorporationDescription",
                "insiderTransactionForOwnerExists", "insiderTransactionForIssuerExists",
                "category", "addresses"
            ]

            first_meta_data_dict = {k: (v if v else "N/A") for k, v in filing_dict.items() if k in important_keys}
            secondary_meta_data_dict = {k: (v if v else "N/A") for k, v in filing_dict.items() if k in secondary_keys}
            filings = filing_dict.get('filings', {})

            return first_meta_data_dict, secondary_meta_data_dict, filings

    except Exception as e:
        ctx.warning(f"Failed 'fetch_company_details_and_filing_accessions': {e}")
        return {}, {}, {}


def get_latest_filings_index(filings:dict=None)->dict:
    mapping_latest_forms_doc_index = {}
    important_forms = ['10-K', '10-Q', '8-K', 'S-1', 'S-3', 'DEF 14A', '20-F', '6-K', '4', '13D', '13G']
    for form in important_forms:
        for index, row in enumerate(filings['recent']['form']):
            if str(row) == form:
                mapping_latest_forms_doc_index[form] = index
                break
    return mapping_latest_forms_doc_index


def create_base_df_for_sec_company_data(mapping_latest_docs:dict=None,
                                            filings:dict=None, cik:str=None)->pd.DataFrame:
        last_accession_numbers = []
        report_dates = []
        forms = []
        primary_docs = []
        idxs = []

        for _, index in mapping_latest_docs.items():
            last_accession_numbers.append(filings['recent']['accessionNumber'][index].replace('-', ''))
            report_dates.append(filings['recent']['reportDate'][index])
            forms.append(filings['recent']['form'][index])
            primary_docs.append(filings['recent']['primaryDocument'][index])
            idxs.append(index)

        base_sec_df = pd.DataFrame({
            'accession_number': last_accession_numbers,
            'report_date': report_dates,
            'form': forms,
            'docs': primary_docs,
            'cik': [cik] * len(forms),
            'index': str(idxs)
        })
        return base_sec_df
        
        
async def _fetch_selected_company_filings(ctx:Context, cik:str|int, accession:str, filename:str, user_agent:str) -> bytes:
    try:
        headers = {'User-Agent': user_agent}
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{filename}"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=None)
            response.raise_for_status()
            return response.content

    except httpx.HTTPStatusError as e:
        ctx.warning(f"HTTP error: {e}")
    except httpx.RequestError as e:
        ctx.warning(f"Request error: {e}")
    except Exception as e:
        ctx.warning(f"Unexpected error in 'fetch_company_filings': {e}")

    return b""


async def fetch_all_filings(ctx:Context, sec__base_df: pd.DataFrame, user_agent:str) -> pd.Series:
    all_filings = []
    for _, row in sec__base_df.iterrows():
        filings_dict = await _fetch_selected_company_filings(ctx=ctx, cik=str(int(row['cik'])), accession=row['accession_number'], filename=row['docs'], user_agent=user_agent)
        all_filings.append(filings_dict)
    if all_filings:
        ctx.info('Files successfully fetched from SEC.gov')

    return pd.Series(all_filings)


def preprocess_docs_content(raw_content:str) -> str:
    '''
    This function turns the raw html to markdown
    '''
    html_stream = DocumentStream(name='sec_file', stream=BytesIO(raw_content))
    converter = DocumentConverter()
    result = converter.convert(html_stream)
    
    return result


def chunk_docs_content(content:str) -> str:
    '''
    This function chunks too large markdown content for proper llm consumption 
    '''
    markdown_splitter = MarkdownTextSplitter(chunk_size=2, chunk_overlap=0)
    chunks = markdown_splitter.split_text(content)
    
    return chunks

