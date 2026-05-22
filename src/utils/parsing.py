import os
import json
from pathlib import Path
from collections import defaultdict

import chardet
import xmltodict
import pandas as pd
import numpy as np

from src.utils.io_helpers import read_csv_flexible_encoding


def detect_encoding(file_path):
    with open(file_path, 'rb') as file:
        raw_data = file.read()
        result = chardet.detect(raw_data)
        return result['encoding']

def flatten_dict(d, parent_key='', sep='_'):
    items = []
    for key, value in d.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        if isinstance(value, dict):
            items.extend(flatten_dict(value, new_key, sep=sep).items())
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    items.extend(flatten_dict(
                        item, f"{new_key}[{i}]", sep=sep).items())
                else:
                    items.append((f"{new_key}[{i}]", item))
        else:
            items.append((new_key, value))
    return dict(items)

def process_xml_file(xml_file_path, field_occurrence, logger, overwrite_existing=False):
    csv_file_path = os.path.splitext(xml_file_path)[0] + ".csv"

    # Check if CSV already exists
    if os.path.exists(csv_file_path) and not overwrite_existing:
        logger.info(f"Skipped processing '{xml_file_path}' because CSV already exists.")
        return 0

    if overwrite_existing and os.path.exists(csv_file_path):
        logger.info(f"Overwriting existing CSV for '{xml_file_path}'.")

    try:
        encoding = detect_encoding(xml_file_path)
        with open(xml_file_path, 'r', encoding=encoding) as file:
            xml_data = file.read()

        if not xml_data.strip():
            logger.warning(f"Warning: '{xml_file_path}' is empty.")
            return 0

        data_dict = xmltodict.parse(xml_data)

        button_properties = data_dict.get(
            'QVObjects', {}).get('ButtonProperties', {})
        if not button_properties:
            button_properties = data_dict.get('QVObjects', {})
        if not button_properties:
            button_properties = data_dict

        if not button_properties:
            logger.warning(f"No data in '{xml_file_path}'. Skipping.")
            return 0

        flattened_data = flatten_dict(button_properties)
        if not flattened_data:
            logger.warning(f"Flattened data is empty for '{xml_file_path}'. Skipping.")
            return 0

        # Track all field names
        file_base = os.path.splitext(os.path.basename(xml_file_path))[0]
        # remove numeric suffix
        file_base = ''.join(filter(lambda c: not c.isdigit(), file_base))
        for field in flattened_data.keys():
            field_occurrence[field].add(file_base)

        # Save CSV
        df = pd.DataFrame([flattened_data])
        df.to_csv(csv_file_path, index=False)
        logger.info(f"Processed and saved: {csv_file_path}")
        return 1

    except Exception as e:
        logger.error(f"Error processing '{xml_file_path}': {e}")
        return 0

def process_document_folders(base_path, logger, overwrite_existing=False):
    # Dictionary to track field frequency across all files
    field_occurrence = defaultdict(set)  # store filenames where field appears
    total_files_processed = 0

    for root, _, files in os.walk(base_path):
        if os.path.basename(root) == 'Document':
            xml_files = [f for f in files if f.lower().endswith('.xml')]
            for xml_file in xml_files:
                xml_file_path = os.path.join(root, xml_file)
                total_files_processed += process_xml_file(
                    xml_file_path, field_occurrence, logger, overwrite_existing=overwrite_existing)

    return field_occurrence, total_files_processed

def save_all_fields_report(output_path, field_occurrence, total_files_processed, logger):

    if not field_occurrence:
        logger.info("No fields collected. Skipping report.")
        return

    # Flatten field -> [list of files]
    records = []
    max_depth = 0

    for field, file_bases in field_occurrence.items():
        parts = field.split('_')
        max_depth = max(max_depth, len(parts))
        for base_name in file_bases:
            records.append((parts, base_name))

    rows = []
    for parts, base_name in records:
        row = parts + [''] * (max_depth - len(parts))  # pad missing levels
        row += [1, round((1 / total_files_processed) * 100, 2), base_name]
        rows.append(row)

    headers = [f"Level_{i+1}" for i in range(max_depth)] + ["FileCount", "PercentFiles", "BaseFileName"]
    df = pd.DataFrame(rows, columns=headers)

    df.to_csv(output_path, index=False)
    logger.info(f"Saved all fields breakdown to '{output_path}' with {len(df)} rows and max depth {max_depth}.")

def load_mapping(field_mapping_file_path, logger):
    try:
        # Load the mapping CSV
        mapping_df = pd.read_csv(field_mapping_file_path)
        # Build a dictionary like: {'CH': [col1, col2], 'LB': [...]}
        mapping_dict = mapping_df.groupby('BaseFileName')['relevant_field'].apply(list).to_dict()

        logger.info("Successfully load field mapping csv")
        return mapping_dict
    except Exception as e:
        logger.error(f"Failed to load field mapping csv: {e}")

def process_unfiltered_fields_file(file_path, relevant_fields, logger, overwrite_existing=False):
    try:
        # Determine output file path first
        base, ext = os.path.splitext(os.path.basename(file_path))
        output_file = f"{base}_mapped_pivoted{ext}"
        output_path = os.path.join(os.path.dirname(file_path), output_file)

        # Check if mapped file already exists
        if os.path.exists(output_path) and not overwrite_existing:
            logger.info(f"Skipped mapping for '{file_path}' because mapped file already exists.")
            print(f"      Skipped (already mapped): {os.path.basename(output_path)}")
            return

        df = pd.read_csv(file_path)
        logger.info(f"Original columns: {list(df.columns)}")

        # Filter only the relevant fields that exist in the file
        filtered_columns = [col for col in relevant_fields if col in df.columns]
        filtered_df = df[filtered_columns]
        logger.info(f"Filtered columns: {filtered_columns}")

        # Take only the first row and pivot it
        if not filtered_df.empty:
            first_row = filtered_df.iloc[0]
            pivot_df = pd.DataFrame({
                "attribute": first_row.index,
                "value": first_row.values
            })

            pivot_df.to_csv(output_path, index=False)
            logger.info(f"Processed and pivoted: {output_path}")
            print(f"     Saved: {os.path.basename(output_path)} ({len(filtered_columns)} fields)")
        else:
            logger.warning(f"No data to process in: {file_path}")
            print(f"      No relevant fields found in: {os.path.basename(file_path)}")

    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        print(f"     Error mapping {os.path.basename(file_path)}: {e}")

def generate_outputanalysis_jsons(report_folder: Path, logger, field_mapping: Path):
    logger.info("Starting structured JSON generation from QVW metadata...")

    try:
        paths = {
            "objects": report_folder / "objects.csv",
            "daxOutput": report_folder / "DAX_output.csv",
            "objectSheets": report_folder / "objectSheets.csv",
            "sheets": report_folder / "sheets.csv",
            "field_mapping": field_mapping,
            "expressions": report_folder / "expressions.csv",
            "dax": report_folder / "expressions_with_dax.csv",
            "fields": report_folder / "fields.csv",
            "m_query": report_folder / "m_query_output.csv"
        }

        # Read files with robust encoding fallback
        dfs = {key: read_csv_flexible_encoding(path) for key, path in paths.items() if path.exists()}

        # Report which files are present and which are missing
        for key, path in paths.items():
            if key in dfs:
                dfs[key].columns = dfs[key].columns.str.strip()
                logger.info(f"Loaded {key} with {dfs[key].shape[0]} rows and columns: {list(dfs[key].columns)}")
                print(f"       Found: {path.name}")
            else:
                logger.warning(f"Missing: {path} — skipping dependent outputs")
                print(f"        Missing: {path.name} (skipping dependent outputs)")

        output_dir = report_folder / "Outputanalysis"
        output_dir.mkdir(parents=True, exist_ok=True)

        objects_df = dfs.get("objects")
        object_sheets_df = dfs.get("objectSheets")
        sheets_df = dfs.get("sheets")
        field_mapping_df = dfs.get("field_mapping")
        expressions_df = dfs.get("expressions")
        dax_df = dfs.get("dax")

        # Build enriched objects only if we have the required base files
        enriched_final = None
        if objects_df is not None and object_sheets_df is not None and sheets_df is not None:
            object_sheet = object_sheets_df.merge(sheets_df, on="SheetId", how="left")
            enriched = objects_df.merge(object_sheet, on="ObjectId", how="left")

            if field_mapping_df is not None:
                field_mapping_df["BaseFileName"] = field_mapping_df["BaseFileName"].str.strip()
                object_pbi_type_map = field_mapping_df[["BaseFileName", "ObjectType", "PowerBIObjectType"]].drop_duplicates()
                enriched["BaseFileName"] = enriched["ObjectId"].str[:2]
                enriched = enriched.merge(object_pbi_type_map, on="BaseFileName", how="left")
            else:
                print(f"        field_mapping.csv missing — skipping PBI type mapping")
                enriched["ObjectType_y"] = ""
                enriched["PowerBIObjectType"] = ""

            # Attach expressions (and DAX if available)
            if expressions_df is not None:
                if dax_df is not None:
                    dax_cols = [c for c in ["Expression", "DAX", "ExpressionComment"] if c in dax_df.columns]
                    merged_exprs = expressions_df.merge(dax_df[dax_cols], on="Expression", how="left").fillna("")
                else:
                    print(f"        expressions_with_dax.csv missing — expressions without DAX translations")
                    merged_exprs = expressions_df.copy()
                    merged_exprs["DAX"] = ""

                expr_group = merged_exprs.groupby("ObjectId").apply(
                    lambda grp: grp[["Expression", "DAX"]].to_dict(orient="records")
                ).to_dict()
                enriched["Expressions"] = enriched["ObjectId"].map(expr_group)
            else:
                enriched["Expressions"] = None

            select_cols = ["ObjectId", "Caption", "SheetId", "SheetName", "ObjectType_y",
                           "PowerBIObjectType", "Expressions"]
            available_cols = [c for c in select_cols if c in enriched.columns]
            enriched_final = enriched[available_cols].fillna("")
            enriched_final = enriched_final.rename(columns={
                'ObjectType_y': 'Object Type QlikView',
                'PowerBIObjectType': 'Object Type Power BI Equivalent',
                'Expressions': 'Associated Expressions',
                'Caption': 'Object Name',
                'SheetName': 'Sheet Name'
            })
        else:
            missing = [n for n, d in [("objects.csv", objects_df), ("objectSheets.csv", object_sheets_df), ("sheets.csv", sheets_df)] if d is None]
            print(f"        Cannot build enriched objects — missing: {', '.join(missing)}")

        # Save enriched_dax.json (objects that have DAX expressions)
        if enriched_final is not None:
            if dax_df is not None and "Associated Expressions" in enriched_final.columns:
                enriched_with_dax = enriched_final[
                    enriched_final["Associated Expressions"].apply(
                        lambda exprs: isinstance(exprs, list) and any(e.get("DAX", "").strip() for e in exprs)
                    )
                ].copy()
            else:
                enriched_with_dax = enriched_final.copy()

            for col in enriched_with_dax.columns:
                if enriched_with_dax[col].apply(lambda x: isinstance(x, np.ndarray)).any():
                    enriched_with_dax[col] = enriched_with_dax[col].apply(lambda x: x.tolist() if isinstance(x, np.ndarray) else x)

            output_path = output_dir / "enriched_dax.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(enriched_with_dax.to_dict(orient="records"), f, indent=2, ensure_ascii=False)
            print(f"       Saved: enriched_dax.json ({len(enriched_with_dax)} objects)")

        # Save m_query_output.json
        if "m_query" in dfs:
            m_query_df = dfs["m_query"]
            m_query_df.columns = m_query_df.columns.str.strip()
            m_query_output = m_query_df.to_dict(orient="records")
            with open(output_dir / "m_query_output.json", "w", encoding="utf-8") as f:
                json.dump(m_query_output, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved m_query_output.json with {len(m_query_output)} entries")
            print(f"       Saved: m_query_output.json ({len(m_query_output)} tables)")

        # Save report_pages.json
        report_pages_dir = report_folder / "ReportPages"
        if report_pages_dir.exists():
            images = sorted([str(p.resolve()) for p in report_pages_dir.glob("*.png")])
            if images:
                with open(output_dir / "report_pages.json", "w", encoding="utf-8") as f:
                    json.dump(images, f, indent=2)
                logger.info(f"Saved report_pages.json with {len(images)} images")
                print(f"       Saved: report_pages.json ({len(images)} images)")
            else:
                print(f"        ReportPages/ exists but contains no PNG files")
        else:
            print(f"        ReportPages/ not found — run PDF Generation (Step 6) first")

    except Exception as e:
        logger.exception(f"Failed to generate structured JSON output for {report_folder.name}: {str(e)}")
        print(f"       Output analysis failed: {e}")
