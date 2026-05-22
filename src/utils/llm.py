# Standard library imports
import io
import csv
import json
import os
import re
import base64
import time
import traceback
import numpy as np
from datetime import datetime
from pathlib import Path
from collections import deque
from io import BytesIO
from typing import Dict, List, Tuple, Optional, Any

# Third-party imports
import pandas as pd
from openai import AzureOpenAI
from PIL import Image

# Internal imports
from src.utils.io_helpers import read_csv_flexible_encoding
from src.utils.parsing import detect_encoding

# ====================================
# OpenAI client initializer
# ====================================

def initialize_azure_openai_client(api_key=None, azure_endpoint=None):

    client = AzureOpenAI(
        api_key=api_key,
        api_version="2024-12-01-preview",
        azure_endpoint=azure_endpoint
    )
    return client

# ====================================
# RAG Framework for Data Source Generation Prompts
# ====================================

def embed_text(text, client):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

def cosine_similarity(vec1, vec2):
    a = np.array(vec1)
    b = np.array(vec2)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def get_closest_example(tab_code, client, rag_index, top_k=1, similarity_threshold=0.0):
    print("\n Embedding input tab code...")
    print(f"Tab length: {len(tab_code)}")
    print(f"Tab preview:\n{tab_code[:300]}...\n")

    new_embedding = embed_text(tab_code, client)

    if not new_embedding:
        print("Could not generate embedding for the current tab.")
        return[]

    print("Embedding generated. Comparing with examples from the index...")

    scored = []

    for entry in rag_index:
        score = cosine_similarity(new_embedding, entry["embedding"])
        print(f" Similarity to '{entry['tab_name']}': {score:.4f}")
        scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Optional filtering by threshold
    top = [entry for score, entry in scored if score >= similarity_threshold]

    print(f"\nTop similar found: {len(top)}")
    if not top:
        print("No examples exceeded the similarity threshold.")

    return top[:top_k]

def build_embedding_m_query(client,assets_folder):

    m_query_rag_txt_path = assets_folder / "rag" / "m_query_rag.txt"
    embedding_m_query_output_path = assets_folder / "rag" / "embedding_index.json"

    #1. Read TXT and transform it to json
    try:
        local_vars = {}
        with open(m_query_rag_txt_path, "r", encoding="utf-8") as file:
            exec(file.read(), {}, local_vars)

        rag_list = []
        i = 1
        while True:
            input_key = "input_tab" if i == 1 else f"input_tab_{i}"
            mquery_key = "m_query" if i == 1 else f"m_query_{i}"

            input_tab = local_vars.get(input_key)
            m_query = local_vars.get(mquery_key)

            if input_tab is None or m_query is None:
                break

            rag_list.append({
                "input_tab": input_tab.strip(),
                "m_query": m_query.strip()
            })

            i += 1
        m_query_rag = rag_list
        output_path = assets_folder / "rag" / "rag_m_query_input.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(m_query_rag, f, indent=2)

        print("Embedding index built successfully.")
        print(f"Loaded {len(m_query_rag)} RAG example(s) from {m_query_rag_txt_path}")
    except Exception as e:
        print(f"Failed to load M Query RAG examples from {m_query_rag_txt_path}: {e}")
        traceback.print_exc()
        return None


    #2. Create the embedding index
    try:
        print("Building embedding index for M Query examples...")
        index = []
        i=0
        for ex in m_query_rag:
            embedding = embed_text(ex["input_tab"], client)
            i = i+1
            index.append({
                "tab_name": str(i),
                "embedding": embedding,
                "input_tab": ex["input_tab"],
                "m_query": ex["m_query"]
            })

        with open(embedding_m_query_output_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)

        print(f"Saved embedding index to {embedding_m_query_output_path}")


    except Exception as e:
        print(f"Failed to build embedding index: {e}")
        traceback.print_exc()
        return None  # o puedes usar raise si prefieres abortar

# ======================================
# Data Source Generation QVS to M Query
# ======================================

def split_qvs_by_tab(script):
    # Split QlikView tabs based on the `///$tab TabName` pattern
    pattern = r"///\$\s*tab\s+(.*)\n"
    splits = re.split(pattern, script)
    tabs = []

    if not splits or len(splits) < 2:
        return [("Main", script)]

    for i in range(1, len(splits), 2):
        tab_name = splits[i].strip()
        tab_code = splits[i + 1] if i + 1 < len(splits) else ""
        tabs.append((tab_name, tab_code.strip()))
    return tabs

def generate_data_source_prompt(tab_name, tab_code, client, assets_folder):

    embedding_m_query_output_path = assets_folder / "rag" / "embedding_index.json"

    # 3. Load embedding index from file
    try:
        with open(embedding_m_query_output_path, "r", encoding="utf-8") as f:
            m_query_rag_index = json.load(f)
        print(f"Loaded embedding index from {embedding_m_query_output_path}")
    except Exception as e:
        print(f"Failed to load embedding index from {embedding_m_query_output_path}: {e}")
        traceback.print_exc()
        return None

    # 4. Retrieve closest examples from index
    try:
        print("Retrieving most similar examples from index...")
        best_examples = get_closest_example(tab_code, client, m_query_rag_index)
        print(f"Retrieved {len(best_examples)} matching example(s).")
    except Exception as e:
        print(f"Failed to retrieve similar examples: {e}")
        traceback.print_exc()
        return None

    if not best_examples:
        return None

    try:
        context_blocks = "\n\n".join(
            f"--- QlikView Example Input ---\n{ex['input_tab']}\n\n--- Expected M Query Output ---\n{ex['m_query']}"
            for ex in best_examples
        )
    except Exception as e:
        print(f"Failed to generate context blocks: {e}")
        traceback.print_exc()
        return None

    if not context_blocks.strip():
        print("No valid context blocks could be generated from best_examples.")
        return None


    return f"""

    You are a QlikView and Power BI expert.

    Your task is to convert the following QlikView tab into an equivalent Power BI M Query script.

    Use the rules below to handle all QlikView constructs and edge cases correctly and accurately. Assume the field metadata is available (types, cardinality, joins).

    ---

    QlikView Tab: "{tab_name}"

    {tab_code}

    ---

    Rules:

    - Convert all QlikView data load steps (e.g., `LOAD`, `SQL SELECT`, `RESIDENT`, `INLINE`, `JOIN`, `MAP`, `APPLYMAP`) into Power BI M Query.

    - Use appropriate M connectors:
        - `Sql.Database(...)` for SQL Server data.
        - `Excel.Workbook(...)`, `Csv.Document(...)`, or `SharePoint.Files(...)` for file sources (Excel, CSV, QVD).
            - Include the 'Promote Headers' step when the file metadata indicates "embedded label." Ensure that column names are correctly detected and promoted as headers.
        - For `INLINE` loads, use `Table.FromRows(...)` with column headers.

    - Separate each logical or physical table (e.g., `LOAD` from different source, `JOIN`, `RESIDENT`) into its own named M Query (Power BI table).
        - Power BI Power Query works per-table — do not combine unrelated tables into a single `let` block.
        - Name each resulting table after its logical purpose (e.g., `CustomerTable`, `AddressTable`, `JoinedCustomerAddress`).

    - Output each M Query as a separate block in the following format only without any Power BI UI steps or extra commentary:
        - Start with a line: `### TableName: [LogicalTableName]`
        - Then output the full M Query script for that table
        - Separate each block with a line `---`

    - This format is used to support programmatic processing and CSV export with headers `TableName` and `MQueryScript`.
    - Handle `JOIN`, `LEFT JOIN`, `INNER JOIN`, `KEEP`, and `CONCATENATE` using `Table.Join(...)`, `Table.Combine(...)`, or similar.
    - Handle `RESIDENT` by referencing previous steps as named let-bound tables.
    - Replicate WHERE clauses (including subqueries or IN clauses) using `Table.SelectRows(...)` or equivalent.
    - Replace Qlik variables defined using `SET` or `LET` with inline values or let-bindings.
    - Translate expressions like `APPLYMAP`, `IF`, `MATCH`, `SUBFIELD`, `WILDMATCH`, and `PICK` into equivalent M logic or custom functions.
    - Rename fields where aliases are used (e.g., `[Field A] as [New A]` to `Table.RenameColumns(...)`).
    - If a field appears in multiple tables, treat it as a possible join key.

    --- QlikView Example Input And Expected M Query Output ---



    Use the structure above to guide how you convert future QlikView tabs.

    Do not include comments used in the example in your response. Comments are used only to guide semantic understanding during training.

    """

def extract_table_blocks(m_output):
    # Parse ### TableName: and code blocks
    matches = re.findall(r"### TableName: (.*?)\n(.*?)\n---", m_output, re.DOTALL)
    return [{"TableName": name.strip(), "MQueryScript": code.strip()} for name, code in matches]

def save_m_query_to_csv(output_rows, qvs_file_path, logger):
    output_folder = os.path.dirname(qvs_file_path)
    output_csv_path = os.path.join(output_folder, "m_query_output.csv")

    try:
        with open(output_csv_path, mode='w', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=["TableName", "MQueryScript"])
            writer.writeheader()
            writer.writerows(output_rows)
        logger.info(f"M Query scripts saved to CSV at '{output_csv_path}'")
        print(f"     Saved: m_query_output.csv ({len(output_rows)} tables)  {output_csv_path}")
    except Exception as e:
        logger.error(f"Error saving CSV: {e}")
        print(f"     Error saving m_query_output.csv: {e}")
        raise

# ===========================================
# QlikView Expressions to DAX RAG Utilities
# ===========================================

def get_dax_type(tags: str) -> str:
    """
    Maps QlikView field tags to appropriate DAX data types.

    Args:
        tags (str): QlikView field tags (case insensitive)

    Returns:
        str: Corresponding DAX data type
    """
    tags = tags.lower()

    # Date and Time types
    if any(tag in tags for tag in ["$timestamp", "$date", "$datetime"]):
        return "DateTime"
    elif "$time" in tags:
        return "DateTime"  # or "Time" if your DAX model supports it

    # Text and String types
    elif any(tag in tags for tag in ["$ascii", "$text", "$string"]):
        return "Text"

    # Numeric types
    elif any(tag in tags for tag in ["$numeric", "$integer", "$int"]):
        return "Whole Number"
    elif any(tag in tags for tag in ["$money", "$currency"]):
        return "Currency"
    elif any(tag in tags for tag in ["$decimal", "$float", "$double"]):
        return "Decimal Number"

    # Boolean type
    elif any(tag in tags for tag in ["$boolean", "$bool"]):
        return "True/False"

    # Key types (usually numeric or text)
    elif "$key" in tags:
        return "Text"  # Keys are often treated as text to preserve leading zeros

    # Geographical types
    elif any(tag in tags for tag in ["$geopoint", "$latitude", "$longitude"]):
        return "Decimal Number"

    # Binary/Image types
    elif any(tag in tags for tag in ["$binary", "$image", "$blob"]):
        return "Binary"  # Note: Limited support in Power BI

    # Default fallback
    else:
        return "Text"  # Changed from "Unknown" to "Text" as safer default

def obtain_semantic_model(csv_fields_path):

    # Try reading the file with a different encoding (likely 'utf-16' or 'latin1')

    # Based on the byte pattern, it's likely encoded in UTF-16 or ANSI
    try:
        df = pd.read_csv(csv_fields_path, encoding='utf-16')
    except UnicodeError:
        df = pd.read_csv(csv_fields_path, encoding='latin1')

    df.columns = df.columns.str.strip()

    # Step 1: Filter out fields with FieldTableCount = 0 (hidden or unused)
    df_filtered = df[df["FieldTableCount"] > 0]

    # Step 2: Group by table and collect field names with type
    tables = {}
    for _, row in df_filtered.iterrows():
        field_name = str(row["FieldName"]).strip()
        field_tags = str(row.get("FieldTags", ""))
        field_table = str(row.get("FieldTables", "")).strip()
        dax_type = get_dax_type(field_tags)

        if not field_table:
            continue  # Skip if no table assigned

        # Clean and split if multiple tables are mentioned
        for table in field_table.split(";"):
            table = table.strip()
            field_entry = f"{field_name} ({dax_type})"
            tables.setdefault(table, []).append(field_entry)

    # Step 3: Infer relationships from fields appearing in multiple tables
    field_usage = {}
    for _, row in df_filtered.iterrows():
        field_name = str(row["FieldName"]).strip()
        field_table = str(row.get("FieldTables", "")).strip()
        if field_name and field_table:
            tables_list = [t.strip() for t in field_table.split(";") if t.strip()]
            field_usage.setdefault(field_name, set()).update(tables_list)

    # Relationships: fields appearing in more than one table
    relationships = []
    for field, used_in_tables in field_usage.items():
        if len(used_in_tables) >= 2:
            sorted_tables = sorted(list(used_in_tables))
            for i in range(len(sorted_tables) - 1):
                relationships.append(f"'{sorted_tables[i]}'[{field}] → '{sorted_tables[i+1]}'[{field}]")

    # Step 4: Format output
    output_lines = []
    output_lines.append("- Tables:")
    for table, fields in tables.items():
        formatted_fields = ", ".join(fields)
        output_lines.append(f"  - '{table}': [{formatted_fields}]")

    output_lines.append("- Relationships:")
    for rel in relationships:
        output_lines.append(f"  - {rel}")

    # Display in VS Code terminal style
    semantic_model_summary = "\n".join(output_lines)
    return semantic_model_summary

# =========================================
# QlikView Expressions to DAX Translation
# =========================================
def generate_dax_prompt():
    return f"""
    You are an expert in Power BI, DAX, and QlikView. You will receive QlikView expression context and a list of fields, their metadata, and the tables they belong to.

        Follow these instructions carefully:

        Task:
        - Translate each QlikView expression context into a valid DAX measure using the provided field metadata to resolve the correct table and column names.
        - Output the results in the standardized Power BI Tabular Editor DAX measure format.

        Constraints:
        - If translation confidence is below 80%:
            - Return "**-Needs manual attention-**" as the DAX measure.
        - Do not include any reasoning, comments, markdown formatting, or additional explanation.
        - Do not fabricate or assume missing information.
        - Only use columns and tables mentioned in the provided field metadata.
        - Do NOT invent columns or tables.
        - Do NOT make assumptions without field evidence.
        - Use standard DAX functions like CALCULATE, SUM, COUNTROWS, DISTINCTCOUNT, AVERAGE, etc., as required by the logic of the QlikView expression.
        - Preserve the exact format and indentation below.
        - Think step-by-step internally, but return only the formatted result.

        Output Format (for each expression):
        Return the DAX measure definition using the following strict format:

        ```
        measure '<MEASURE NAME>' = <DAX_MEASURE>
            displayFolder: $_measure
        ```

        Rules for formatting:
        - The measure name should be in single quotes and be descriptive.
        - Ensure correct syntax and table[column] references based on metadata.
        - The displayFolder should be '$_measure'.
        - If confidence is low (<80%), output:

        ```
        measure '<MEASURE NAME>' = "**-Needs manual attention-**"
            displayFolder: $_measure
        ```


        Example Input:
        QlikView expression context:
        ObjectId, Parent, Enabled, Expression, ExpressionComment
        "CH41","ExpressionData.Definition;Population","true","Sum ([Population(mio)])",""

        Field metadata:
        FieldName, FieldTableCount, FieldValueCount, FieldTables, FieldTags, FieldComment
        "Country",2,191,"Country;Customers;","$key;$ascii;$text;",""
        "Capital",1,189,"Country;","$text;",""
        "Area(km.sq)",1,188,"Country;","$numeric;",""
        "Population(mio)",1,177,"Country;","",""
        "Pop. Growth",1,136,"Country;","",""
        "Currency",1,85,"Country;","$text;",""
        "Inflation",1,16,"Country;","",""

        Expected Output:
        ```
        measure 'Total Population (in millions)' = SUM(Country[Population(mio)])
            displayFolder: $_measure
        ```

        Another Output with Low Confidence:
        ```
        measure 'Estimated Area Growth' = "**-Needs manual attention-**"
            displayFolder: $_measure
        ```
    """

def format_dax_block(raw_dax):
    lines = [
        line.rstrip() for line in raw_dax.strip().splitlines()
        if not line.strip().startswith("```")
    ]
    return "\n".join(lines)

def _format_csv_row(row_list):
    """Internal helper to format a CSV row for DAX prompt construction."""
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(row_list)
    return output.getvalue().strip()

def generate_dax(model_name, client, all_qlik_expressions, logger, overwrite_existing=False, start_file=None, end_file=None):

    system_prompt = generate_dax_prompt()

    total_tokens_used = 0
    request_timestamps = deque()
    total_succesful_request_count = 0
    total_unsuccesful_request_count = 0
    start_time = time.time()

    all_dax_responses = []

    for file_path, content in all_qlik_expressions.items():

        report_name = Path(file_path).parent.name

        if start_file:
            start_file(report_name)

        print(f"\n [{report_name}] Translating expressions  DAX")

        try:
            output_csv_path = file_path.replace("expressions.csv", "expressions_with_dax.csv")
            dax_output_path = os.path.join(os.path.dirname(file_path), "DAX_output.csv")

            #Case 1: Runs but outputs already exist
            if not overwrite_existing and os.path.exists(output_csv_path) and os.path.exists(dax_output_path):
                if end_file:
                    end_file(report_name, "skipped")
                logger.info(f"Skipped DAX generation for {file_path} (outputs already exist).")
                print(f"    Skipping — expressions_with_dax.csv + DAX_output.csv already exist")
                continue

            #Case 2: Overwrite
            if overwrite_existing:
                logger.info(f"Overwriting existing DAX outputs for {file_path}.")

            # Reading the content of the file with Qlik View Expressions
            reader = csv.reader(io.StringIO(content), delimiter=",")
            rows = list(reader)
            if len(rows) < 2:
                if end_file:
                    end_file(report_name, "skipped")
                print(f"    Skipping — expressions.csv has no data rows")
                continue
            header = rows[0]
            data_rows = rows[1:]
            print(f"  \U0001f4c4 {len(data_rows)} expression(s) to translate")

            #Semantic Model Context from fields.csv
            fields_path = os.path.join(os.path.dirname(file_path), "fields.csv")
            fields_content = obtain_semantic_model(fields_path)
            #fields_content = read_file(fields_path, "utf-16", logger)
            if not fields_content:
                print(f"   Missing fields.csv for {file_path}")
                if end_file:
                    end_file(report_name, "failed")
                continue

            updated_rows = []

            for row_list in data_rows:

                row_values = _format_csv_row(row_list)
                user_input = (
                    f"QlikView expression context:\n{','.join(header)}\n{row_values}\n\n"
                    f"Field metadata:\n{fields_content}"
                )

                # Request per minute control to avoid errors with OpenAI
                now = time.time()
                while request_timestamps and request_timestamps[0] < now - 60:
                    request_timestamps.popleft()
                if len(request_timestamps) >= 150:
                    wait_time = 60 - (now - request_timestamps[0])
                    print(f"[Throttle] Waiting {wait_time:.2f} seconds to respect 150 RPM")
                    time.sleep(wait_time)
                request_timestamps.append(time.time())

                # OpenAI calling
                try:
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_input},
                        ],
                        temperature=0.3
                    )

                    # Processing of Open AI response
                    raw_dax = response.choices[0].message.content.strip()
                    formatted = format_dax_block(raw_dax)
                    text_no_measure = re.sub(r"\bmeasure\b\s+", "", formatted)
                    cleaned_text = re.sub(r"^\s*displayFolder:.*$", "", text_no_measure, flags=re.MULTILINE)
                    dax_clean = cleaned_text
                    logger.info(f"Successfully generated DAX expression for {row_values}.")

                    # Resources management
                    total_succesful_request_count += 1
                    if hasattr(response, "usage") and response.usage:
                        total_tokens_used += response.usage.total_tokens

                except Exception as e:
                    formatted = f"Error: {str(e)}"
                    dax_clean = f"Error: {str(e)}"
                    logger.error(f"Failed to generate DAX for row {row_values}: {str(e)}")
                    total_unsuccesful_request_count += 1
                    raise

                #List with all dax responses
                updated_row = row_list + [dax_clean]
                updated_rows.append(updated_row)
                all_dax_responses.append(formatted)

            # Write updated expressions_with_dax.csv with full quoting
            updated_header = header + ["DAX"]
            output_csv_path = file_path.replace("expressions.csv", "expressions_with_dax.csv")
            with open(output_csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                writer.writerow(updated_header)
                writer.writerows(updated_rows)
            print(f"   Saved: expressions_with_dax.csv ({len(updated_rows)} rows)")

            # Write DAX_output.csv
            dax_output_path = os.path.join(os.path.dirname(file_path), "DAX_output.csv")
            with open(dax_output_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                for response in all_dax_responses:
                    writer.writerow([response.strip()])
            print(f"   Saved: DAX_output.csv")
            print(f"   [{report_name}] DAX translation done")

            if end_file:
                end_file(report_name, "success")

        except Exception as e:
            logger.error(f"[ERROR] Failed processing {file_path}: {e}", exc_info=True)
            print(f"   [{report_name}] DAX translation failed: {e}")
            if end_file:
                end_file(report_name, "failed")
            raise

    end_time = time.time()
    total_duration_sec = end_time - start_time

    print("\n[SUMMARY]")
    print(f"Total DAX generations in the last minute: {len(request_timestamps)}")
    print(f"Total tokens used: {total_tokens_used}")
    print(f"Total requests: {total_succesful_request_count}")
    print(f"Total requests: {total_unsuccesful_request_count}")
    print(f"Total duration (minutes): {total_duration_sec/60:.2f}")

    return all_dax_responses

# =============================================================
# Qlik View & Power BI OCR Analysis of Report Pages
# =============================================================

def load_image(image_path):
    """Load an image from disk."""
    return Image.open(image_path)

def image_to_base64(img):
    """Convert a PIL Image to a base64-encoded string."""
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_bytes = buffered.getvalue()
    return base64.b64encode(img_bytes).decode('utf-8')

def create_analysis_prompt(img_b64, user_instruction):
    """Create a prompt for OpenAI's vision model."""
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_b64}"
                    }
                },
                {
                    "type": "text",
                    "text": user_instruction
                }
            ]
        }
    ]

def query_openai(messages, model_name, client):
    """Send a prompt to OpenAI and return the response."""
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=2048
    )
    return response

def extract_model_answer(response):
    """Extract the model's answer from the OpenAI response."""
    try:
        return response.choices[0].message.content
    except (KeyError, TypeError, AttributeError):
        return "No answer found in response."

def process_report_image(image_path, user_instruction, client, model_name):
    """
    Process image pipeline:
    load image, encode, prompt model, and extract answer.

    Args:
        image_path: Path to the image file
        user_instruction: Instruction for the model
        api_key: OpenAI API key
        model_name: Model to use (default: gpt-4o)

    Returns:
        str: Model's response
    """
    # Load and encode image
    img = load_image(image_path)
    img_b64 = image_to_base64(img)

    # Create prompt and get response
    messages = create_analysis_prompt(img_b64, user_instruction)
    response = query_openai(messages, model_name, client)

    return extract_model_answer(response)

def obtain_prompt_for_image_analysis():
    return """Task
    You are given a screenshot of a BI report page (Power BI or QlikView). Extract a complete, normalized, machine-usable representation of the page as STRICT JSON that validates against the schema below. Do not add fields. Do not include comments. If uncertain, use null and add a note in "uncertain" with reasons.

    Assumptions & Rules
    - Platform: infer "power_bi" or "qlikview" from visual cues; set "platform".
    - Coordinates: all positions are absolute pixel bounding boxes [x, y, width, height] relative to the image's top-left (0,0).
    - Numbers: return numeric types when possible; also include "raw" text if formatting is ambiguous.
    - Units: detect and normalize (%, currency, time). Use ISO 4217 for currency (e.g., "AUD").
    - Dates: normalize to ISO 8601 (YYYY-MM-DD or YYYY-MM).
    - Colors: return hex (e.g., "#1F77B4").
    - Confidence: 0–1 per extracted item.
    - Strict JSON only; no trailing commas; no extra prose.

    Output Schema
    {
    "platform": "power_bi" | "qlikview" | "unknown",
    "image_size": {"width": int, "height": int},
    "page_info": {
        "title": string|null,
        "layout": "freeform"|"grid"|"canvas"|"dashboard"|"sheet"|null,
        "theme": {
        "primary_colors": [string],        // hex
        "accent_colors": [string],
        "background_color": string|null,
        "style_notes": string|null
        },
        "tabs": {
        "time_periods": [string],          // e.g., ["2009","2010","2011"]
        "quarters": [string],              // e.g., ["Q1","Q2","Q3","Q4"]
        "months": [string]                 // e.g., ["Jan","Feb",...]
        }|null
    },
    "kpis": [
        {
        "name": string,
        "value": number|null,
        "raw": string|null,                // original text (e.g., "$1.2M")
        "unit": string|null,               // "%","AUD","hrs", etc.
        "trend": "up"|"down"|"flat"|null,
        "target": number|null,
        "variance": number|null,           // signed; same unit as value or %
        "bbox": [int,int,int,int],
        "confidence": number
        }
    ],
    "visualizations": [
        {
        "type": "card"|"table"|"matrix"|"bar"|"column"|"line"|"area"|"pie"|"donut"|"scatter"|"map"|"gauge"|"slicer"|"kpi"|"combo"|"histogram"|"other",
        "title": string|null,
        "bbox": [int,int,int,int],
        "encodings": {                     // what is plotted where
            "x": {"field": string|null, "type":"quantitative|temporal|ordinal|nominal|null"},
            "y": {"field": string|null, "type":"quantitative|temporal|ordinal|nominal|null"},
            "color": {"field": string|null, "values":[string]|null},
            "size": {"field": string|null}|null
        },
        "data_summary": {
            "measures": [{"name": string, "min": number|null, "max": number|null, "sample_values": [number|string]}],
            "dimensions": [{"name": string, "sample_values": [string]}]
        },
        "key_values": [                    // e.g., bars/lines highlighted values
            {"label": string|null, "value": number|null, "raw": string|null, "unit": string|null}
        ],
        "legend": {
            "items": [string],
            "position": "top"|"right"|"bottom"|"left"|null
        },
        "confidence": number
        }
    ],
    "filters": [
        {
        "name": string|null,
        "control_type": "slicer"|"dropdown"|"checkbox"|"date_range"|"tree"|"other",
        "selected": [string]|null,
        "options": [string]|null,
        "bbox": [int,int,int,int],
        "confidence": number
        }
    ],
    "tiles": [
        {
        "title": string|null,
        "content_summary": string|null,
        "bbox": [int,int,int,int],
        "confidence": number
        }
    ],
    "data_elements": [                     // visible table/field names, measures, etc.
        {"type": "table"|"field"|"measure"|"dimension", "name": string, "notes": string|null}
    ],
    "uncertain": [string]                  // short notes on ambiguities
    }

    Extraction Steps (internal)
    1) Detect page size. 2) Run OCR over titles, cards, legends, slicers. 3) Identify visuals by geometry, axes, legends, glyphs. 4) Parse numeric strings → numbers + units. 5) Normalize dates/currencies. 6) Fill schema. 7) Assign confidence per item.

    Return
    - One JSON object strictly matching the schema above.
    """

# ===================================================================
# Power BI  PDF, Image Generation and  OCR Analysis of Report Pages
# ===================================================================

def save_pbi_analysis_result(result, image_path, output_report_folder, page_number, report_name):
    """
    Save analysis result as JSON file with naming convention: {page_number}_{report_name}.json

    Args:
        result: Analysis result from AI
        image_path: Path to the analyzed image
        output_report_folder: Folder to save the JSON result
        page_number: Page number for naming
        report_name: Report name for naming
    """
    try:
        # Try to parse as JSON first to validate
        if isinstance(result, str):
            json_result = json.loads(result)
        else:
            json_result = result

        # Create filename with page number and report name
        filename = f"{page_number}_{report_name}.json"
        output_path = os.path.join(output_report_folder, filename)

        # Save as formatted JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(json_result, f, indent=2, ensure_ascii=False)

        print(f"  Saved analysis: {filename}")

    except json.JSONDecodeError:
        # If result is not valid JSON, save as text with additional info
        filename = f"{page_number}_{report_name}_raw.txt"
        output_path = os.path.join(output_report_folder, filename)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"Image: {image_path}\n")
            f.write(f"Analysis Result:\n{result}")

        print(f"  Saved raw result: {filename}")

def save_analysis_result(result, image_path, output_dir):
    """
    Save the analysis result as a JSON file.

    Args:
        result: Analysis result (string or dict)
        image_path: Original image path for naming
        output_dir: Directory to save the JSON file

    Returns:
        str: Path to the saved JSON file
    """
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Generate filename
    image_filename = os.path.basename(image_path)
    image_name_no_ext = os.path.splitext(image_filename)[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"analysis_{image_name_no_ext}_{timestamp}.json")

    try:
        # Clean up the result if it's a string
        if isinstance(result, str):
            # Remove markdown code blocks if present
            cleaned_result = result.strip()

            # Handle markdown code blocks properly
            if cleaned_result.startswith("```json"):
                cleaned_result = cleaned_result[7:]  # Remove "```json"
            elif cleaned_result.startswith("```"):
                cleaned_result = cleaned_result[3:]  # Remove "```"

            if cleaned_result.endswith("```"):
                cleaned_result = cleaned_result[:-3]  # Remove trailing "```"

            # Clean up any remaining whitespace
            cleaned_result = cleaned_result.strip()

            # Parse the cleaned JSON
            try:
                result_json = json.loads(cleaned_result)
                print(f"Successfully parsed JSON from model response")
            except json.JSONDecodeError as e:
                print(f"Warning: Could not parse JSON, saving as raw output. Error: {e}")
                print(f"First 200 chars of cleaned result: {cleaned_result[:200]}")
                result_json = {
                    "raw_output": result,
                    "cleaned_attempt": cleaned_result[:500],  # First 500 chars for debugging
                    "parse_error": str(e)
                }
        else:
            result_json = result

        # Add the image path to the JSON (always add this field)
        if isinstance(result_json, dict):
            result_json["source_image_path"] = image_path
            result_json["source_image_filename"] = os.path.basename(image_path)
        else:
            # If result_json is not a dict, wrap it
            result_json = {
                "analysis_data": result_json,
                "source_image_path": image_path,
                "source_image_filename": os.path.basename(image_path)
            }
        # Save to JSON file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result_json, f, indent=4, ensure_ascii=False)

        print(f"Analysis saved to: {output_path}")
        return output_path

    except Exception as e:
        print(f"Failed to save analysis: {e}")
        # Try to save raw content for debugging
        try:
            debug_path = output_path.replace('.json', '_debug.txt')
            with open(debug_path, 'w', encoding='utf-8') as f:
                f.write(str(result))
            print(f"Raw content saved to: {debug_path}")
        except:
            pass
        return None

# ====================================
# Validation: Comparison of Power BI JSON and Qlik View JSON
# ====================================

def extract_page_number_from_standard_name(filename: str) -> int:
    """
    Extract page number from standard naming convention: analysis_page_01, analysis_page_02, etc.
    Also handles variations like 1_reportname.json
    """
    # Remove extension
    base_name = filename.replace('.json', '').replace('.txt', '')

    # Pattern for analysis_page_XX format
    pattern = r'analysis_page_(\d+)'
    match = re.search(pattern, base_name, re.IGNORECASE)
    if match:
        return int(match.group(1))

    # Pattern for number at start: 1_reportname, 2_reportname, etc.
    pattern2 = r'^(\d+)_'
    match2 = re.search(pattern2, base_name)
    if match2:
        return int(match2.group(1))

    # Fallback: find any number in filename
    numbers = re.findall(r'\d+', base_name)
    if numbers:
        return int(numbers[0])

    # Default if no number found
    return 1

def load_json_file(file_path: str):
    """Load JSON file and return parsed content."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        # Try to read as text file if JSON parsing fails
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                return {"raw_content": content, "type": "raw_text"}
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return None
    except Exception as e:
        print(f"Error loading file {file_path}: {e}")
        return None

def get_report_pages(report_folder_path: str) -> List[tuple[int, str, Dict]]:
    """
    Get all JSON files from a report folder, sorted by page number from filename.
    Standard naming: analysis_page_01, analysis_page_02, etc.

    Returns:
        List of (page_number, filename, json_content) tuples
    """
    pages = []

    if not os.path.exists(report_folder_path):
        return pages

    for filename in os.listdir(report_folder_path):
        if filename.lower().endswith(('.json', '.txt')):
            file_path = os.path.join(report_folder_path, filename)
            json_content = load_json_file(file_path)

            if json_content:
                page_number = extract_page_number_from_standard_name(filename)
                pages.append((page_number, filename, json_content))

    # Sort by page number
    pages.sort(key=lambda x: x[0])
    return pages

def create_comparison_prompt(qlik_data: Dict, pbi_data: Dict, page_info: str) -> List[Dict]:
    """
    Create a prompt for AI to compare QlikView and Power BI report pages.

    Args:
        qlik_data: QlikView report page JSON data
        pbi_data: Power BI report page JSON data
        page_info: Information about which pages are being compared

    Returns:
        Messages list for OpenAI API
    """
    prompt_text = f"""You are an expert business intelligence analyst tasked with evaluating how well a Power BI report replicates the original QlikView implementation.

    **Task**: Compare the Power BI report against the QlikView master and provide similarity scores showing how closely Power BI matches the original QlikView design and functionality.

    **Page Information**: {page_info}

    **QlikView Report Data**:
    ```json
    {json.dumps(qlik_data, indent=2)}
    ```

    **Power BI Report Data**:
    ```json
    {json.dumps(pbi_data, indent=2)}
    ```

    **Analysis Requirements**:
    Evaluate how similar Power BI is to the original QlikView using scores (0-100):

    100: Perfect match to QlikView
    80-99: Very close match with minor differences
    60-79: Good similarity with some notable differences
    40-59: Moderate similarity with significant differences
    20-39: Poor similarity with major differences
    0-19: Very poor similarity, substantially different

    1. KPI Similarity: How closely do Power BI KPIs match QlikView values, formatting, and presentation?
    2. Layout Similarity: How well does Power BI replicate QlikView's positioning, structure, and organization?
    3. Design Similarity: How closely does Power BI match QlikView's visual design, colors, fonts, and styling?
    4. Overall Similarity: General assessment of how well Power BI replicates the QlikView original

    Issue Identification:
    Identify where Power BI deviates from the QlikView master:

    Severity: "High" (major deviation), "Medium" (noticeable difference), "Low" (minor variation)
    Object: Specific element from the data (e.g., "KPI-Sales", "Chart-Revenue", "Filter-Date")
    Detail: How Power BI differs from the QlikView original

    **Required JSON Response Format**:

    {{
    "reportName": "extract from page info or data",
    "page": "extract page number from page info",
    "scores": {{
        "kpi": 85,
        "layout": 78,
        "design": 92,
        "overall": 82
    }},
    "issues": [
        {{
        "severity": "High",
        "object": "KPI-Revenue",
        "detail": "Value mismatch of 15% between platforms"
        }},
        {{
        "severity": "Medium",
        "object": "Chart-Sales",
        "detail": "Missing data labels in Power BI version"
        }}
    ],
    "summary": "Migration shows good overall fidelity with most KPIs accurately transferred. Layout differences are minor but some design elements need attention.",
    "timestamp": "2024-12-01T15:30:45.123Z"
    }}


    **Instructions**:
    QlikView is always the reference standard - evaluate how well Power BI matches it
    Focus on the most significant deviations from QlikView (max 10 issues)
    Use actual object names from the provided data
    Scores reflect similarity to QlikView, not general quality
    Summary should highlight key differences from the QlikView master

    Provide your analysis as valid JSON following this exact structure.

    """

    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt_text
                }
            ]
        }
    ]

def query_openai_comparison(messages: List[Dict], model_name: str, client) -> str:
    """Send comparison prompt to OpenAI and return the response."""
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            max_tokens=4096,
            temperature=0.1  # Lower temperature for more consistent analysis
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error querying OpenAI: {e}")
        return json.dumps({
            "error": f"Failed to get AI analysis: {str(e)}",
            "comparison_summary": {"overall_similarity_score": 0, "migration_quality_score": 0}
        })

def extract_json_from_markdown(content: str) -> dict:
    """Extract JSON from markdown code blocks or return parsed JSON."""
    try:
        # First, try to parse as direct JSON
        return json.loads(content)
    except json.JSONDecodeError:
        # If that fails, look for JSON in markdown code blocks
        json_pattern = r'```json\s*\n(.*?)\n```'
        match = re.search(json_pattern, content, re.DOTALL)
        if match:
            json_str = match.group(1)
            return json.loads(json_str)
        else:
            # Try to find any JSON-like content
            json_pattern = r'\{.*\}'
            match = re.search(json_pattern, content, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            else:
                raise ValueError("No valid JSON found in content")

def save_comparison_to_files(comparison_folder: str, report_name: str,
                            qlik_page: Tuple, pbi_page: Tuple, analysis_result: str):
    """
    Save comparison result to folder structure with JSON files.

    Structure: comparison_folder/report_name/page_XX.json
    """
    # Create report folder
    report_folder = os.path.join(comparison_folder, report_name)
    os.makedirs(report_folder, exist_ok=True)

    try:
        # Parse analysis result if it's a string
        if isinstance(analysis_result, str):
            try:
                analysis_json = json.loads(analysis_result)
            except json.JSONDecodeError:
                # If not valid JSON, wrap in error structure
                analysis_json = {
                    "error": "Failed to parse AI response",
                    "raw_response": analysis_result,
                    "comparison_summary": {
                        "overall_similarity_score": 0,
                        "migration_quality_score": 0
                    }
                }
        else:
            analysis_json = analysis_result

        # Add metadata about the comparison
        analysis_json["comparison_metadata"] = {
            "qlik_page_number": qlik_page[0],
            "qlik_filename": qlik_page[1],
            "pbi_page_number": pbi_page[0],
            "pbi_filename": pbi_page[1],
            "comparison_timestamp": datetime.now().isoformat(),
            "report_name": report_name
        }

        # Create filename with zero-padded page number: page_01.json, page_02.json, etc.
        page_num = qlik_page[0]  # Use QlikView page number as reference
        filename = f"page_{page_num:02d}.json"
        filepath = os.path.join(report_folder, filename)

        # Save JSON file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(analysis_json, f, indent=2, ensure_ascii=False)

        print(f"  Saved: {report_name}/{filename}")

    except Exception as e:
        print(f"Error saving comparison for {report_name}: {e}")

        # Save error file
        page_num = qlik_page[0] if qlik_page else pbi_page[0]
        error_filename = f"page_{page_num:02d}_ERROR.json"
        error_filepath = os.path.join(report_folder, error_filename)

        error_data = {
            "error": f"Failed to save comparison: {str(e)}",
            "comparison_metadata": {
                "qlik_page_number": qlik_page[0] if qlik_page else None,
                "qlik_filename": qlik_page[1] if qlik_page else None,
                "pbi_page_number": pbi_page[0] if pbi_page else None,
                "pbi_filename": pbi_page[1] if pbi_page else None,
                "comparison_timestamp": datetime.now().isoformat(),
                "report_name": report_name,
                "status": "error"
            }
        }

        try:
            with open(error_filepath, 'w', encoding='utf-8') as f:
                json.dump(error_data, f, indent=2, ensure_ascii=False)
        except Exception as save_error:
            print(f"Failed to save error file: {save_error}")

def extract_image_url_from_json(json_data):
    """
    Extract image URL from JSON data (either from source_image_path or other URL fields).

    Args:
        json_data: The JSON data from QlikView or Power BI analysis

    Returns:
        str: Image URL or path, or None if not found
    """
    if isinstance(json_data, dict):
        # Look for common image URL fields
        url_fields = [
            "source_image_path",
            "source_image_filename",
            "image_url",
            "image_path",
            "original_image",
            "source_image"
        ]

        for field in url_fields:
            if field in json_data:
                return json_data[field]

    elif isinstance(json_data, str):
        # If json_data is a string, try to parse it first
        try:
            parsed_data = json.loads(json_data)
            return extract_image_url_from_json(parsed_data)
        except json.JSONDecodeError:
            pass

    return None
