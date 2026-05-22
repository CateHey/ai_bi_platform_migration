from pathlib import Path
from src.utils import *
import json
from typing import List, Dict, Any

# ====================================
# QV Metadata Extraction
# ====================================

def extract_qv_metadata(settings, logger, overwrite_existing=False, multiplier=1):

    root_folder = Path(settings["root_folder_path"])
    output_qv_restructured_folder_path = Path(settings["output_qv_restructured_folder_path"])
    qv_output_folder = Path(settings["output_qv_folder_path"])

    qvw_files = list(root_folder.rglob("*.qvw"))
    cache_path = "output/qvw_metadata_cache.json"
    cache = load_qvw_cache(cache_path)
    window_opened = False

    # Create the output structure if needed
    create_restructured_folder(root_folder, output_qv_restructured_folder_path, overwrite_existing, logger)

    print(f"Executing start_step_tracking for metadata.")
    execution_path = output_qv_restructured_folder_path / "execution_log.json"
    start_file, end_file, finalize = start_step_tracking("extract_qv_metadata", json_path=execution_path)

    for qvw_file in qvw_files:
      
        report_name = qvw_file.stem
        
        metadata_folder = output_qv_restructured_folder_path / report_name
        metadata_folder_input = qv_output_folder / report_name

        window_opened = False

        start_file(report_name)
        print(f"Executing start_file of " + report_name)

        # Check if qvwork already has data for this report — skip DocumentAnalyzer only
        qvwork_has_data = metadata_folder_input.exists() and any(metadata_folder_input.iterdir())

        if qvwork_has_data and not overwrite_existing:
            logger.info(f"[SKIP DA] qvwork data exists for {qvw_file.name}. Skipping DocumentAnalyzer.")
            print(f"[SKIP DA] qvwork data exists for {qvw_file.name}. Skipping DocumentAnalyzer.")
        else:
            if overwrite_existing:
                logger.info(f"[OVERWRITE] Forcing metadata extraction for: {qvw_file.name}")
                print(f"[OVERWRITE] Forcing metadata extraction for: {qvw_file.name}")
            else:
                logger.info(f"[NEW] No qvwork data for {qvw_file.name}. Running DocumentAnalyzer.")
                print(f"[NEW] Extracting metadata for: {qvw_file.name}")

            try:
                automate_qlikview(settings["DOCUMENT_ANALYZER_PATH"], str(qvw_file), logger, multiplier=multiplier)
                window_opened = True
                time.sleep(2)
                update_qvw_cache_entry(qvw_file, cache, relative_to=root_folder)
                time.sleep(8)
            except Exception as e:
                logger.error(f"[ERROR] DocumentAnalyzer failed for {report_name}: {str(e)}", exc_info=True)
                end_file(report_name, "failed")
                continue

        # Always run the copy step
        try:
            logger.info(f"Copying output to restructured: {metadata_folder}")
            print(f"Copying output to restructured: {metadata_folder}")

            copy_output_to_restructured_by_source_structure(
                root_folder,
                metadata_folder,
                metadata_folder_input,
                logger,
                overwrite_existing=overwrite_existing
            )
            end_file(report_name, "success")
            print(f"Done: {qvw_file.name}")
        except Exception as e:
            logger.error(f"[ERROR] Copy failed for {report_name}: {str(e)}", exc_info=True)
            end_file(report_name, "failed")
                      
    
    # Save updated cache
    save_qvw_cache(cache_path, cache)
    
    window_close_failed = False
    if window_opened:
        try:
            close_qv_window(logger)
            print("window closed")
        except Exception:
            print("error window")
            logger.error("Window close failed — will mark step as failed")
            window_close_failed = True

    summary = finalize(logger, force_fail=window_close_failed)
    
def check_and_rerun_if_needed(settings, logger):
    root_folder = Path(settings["root_folder_path"])
    output_qv_restructured_folder_path = Path(settings["output_qv_restructured_folder_path"])
    
    max_retries = 3
    retry_count = 0
    multiplier = 0.5

    while retry_count < max_retries:
        
        logger.info("Checking for missing or invalid output folders...")
        result, missing = validate_output_folder(root_folder, output_qv_restructured_folder_path)

        if result:
            logger.info("Validation successful: All QVW files have corresponding output folders.")
            
            break  # Exit the loop when all files are validated
        
        logger.info("Validation failed: Some QVW files are missing output folders.")
        logger.info("Rerunning QlikView automation for missing files...")

        multiplier += 1 # Increment multiplier to increase delay for each retry attempt
            
        # Rerun only for missing files
        for missing_file in missing:
            # Extract just the relative path from the message
            if missing_file.startswith("Missing output folder for QVW file: "):
                relative_path = missing_file.replace("Missing output folder for QVW file: ", "")
                missing_file_path = root_folder / (relative_path + ".qvw")
                logger.warning(f"Still missing: {missing_file_path}")
                if missing_file_path.exists():
                    logger.info(f"Rerunning QlikView automation for: {missing_file_path}")
                    automate_qlikview(settings["DOCUMENT_ANALYZER_PATH"], str(missing_file_path), logger, multiplier=multiplier)
                    time.sleep(2)
                else:
                    logger.warning(f"Missing file not found in source folder: {missing_file_path}")

        close_qv_window(logger)
        retry_count += 1

    if retry_count == max_retries:
        logger.error("Maximum retry attempts reached. Some QVW outputs are still missing.")

    # Look through the restructured metadata, ensure the metadata are extracted
    handle_incorrect_extracting(output_qv_restructured_folder_path, logger)


# ====================================
# XML Parser
# ====================================

def parse_xml(settings, logger, overwrite_existing=False):

    output_qv_restructured_folder_path = settings["output_qv_restructured_folder_path"]

    execution_path = Path(output_qv_restructured_folder_path) / "execution_log.json"
    start_file, end_file, finalize = start_step_tracking("parse_xml", json_path=execution_path)
    step_failed = False

    print(f"\n{'='*60}")
    print(f" XML PARSING")
    print(f"{'='*60}")
    print(f"Scanning Document folders in: {output_qv_restructured_folder_path}")
    print(f"Overwrite existing: {overwrite_existing}")

    try:
        start_file("all_reports")

        field_occurrence, total_files_processed = process_document_folders(
            output_qv_restructured_folder_path,
            logger,
            overwrite_existing=overwrite_existing
        )

        print(f"   Processed {total_files_processed} XML file(s)")
        print(f"   Collected {len(field_occurrence)} unique field(s)")

        output_csv_path = os.path.join(output_qv_restructured_folder_path, "objects_all_fields.csv")
        save_all_fields_report(output_csv_path, field_occurrence, total_files_processed, logger)
        if os.path.exists(output_csv_path):
            print(f"   Saved: objects_all_fields.csv  {output_csv_path}")

        end_file("all_reports", "success")
        print(f"\n{'='*60}")
        print(f" XML PARSING SUMMARY: {total_files_processed} XML files, {len(field_occurrence)} fields")
        print(f"{'='*60}\n")
    except Exception as e:
        logger.error(f"[ERROR] parse_xml failed: {str(e)}", exc_info=True)
        print(f" XML parsing failed: {e}")
        end_file("all_reports", "failed")
        step_failed = True

    finalize(logger, force_fail=step_failed)

# ====================================
# Field Mapping
# ====================================

def map_fields(settings, logger, overwrite_existing=False):

    output_qv_restructured_folder_path = settings["output_qv_restructured_folder_path"]
    field_mapping_file_path = settings["field_mapping_file_path"]

    execution_path = Path(output_qv_restructured_folder_path) / "execution_log.json"
    start_file, end_file, finalize = start_step_tracking("map_fields", json_path=execution_path)
    step_failed = False

    processed_reports = set()

    print(f"\n{'='*60}")
    print(f" FIELD MAPPING")
    print(f"{'='*60}")
    print(f"Loading field mapping from: {field_mapping_file_path}")
    field_mapping_dict = load_mapping(field_mapping_file_path, logger)
    print(f"Loaded {len(field_mapping_dict)} prefix mappings: {sorted(field_mapping_dict.keys())}")
    print(f"Scanning for reports in: {output_qv_restructured_folder_path}")
    logger.info("Scanning for 'Document' folder")

    reports_ok = 0
    reports_failed = 0

    try:
        for subdir, _, files in os.walk(output_qv_restructured_folder_path):
            if os.path.basename(subdir) == 'Document':
                report_folder = Path(subdir).parent
                report_name = report_folder.name

                logger.info(f"Found: {subdir}")
                if report_name in processed_reports:
                    continue  # Avoid duplicate processing
                processed_reports.add(report_name)

                print(f"\n Mapping report: {report_name}")
                start_file(report_name)
                try:
                    mapped_count = 0
                    for file in files:
                        if file.endswith('.csv') and not file.endswith('_mapped.csv'):
                            prefix = file[:2]  # First 2 characters
                            file_path = os.path.join(subdir, file)

                            if prefix in field_mapping_dict:
                                process_unfiltered_fields_file(file_path, field_mapping_dict[prefix], logger,
                                                            overwrite_existing=overwrite_existing)
                                mapped_count += 1
                            else:
                                logger.debug(f"Skipped (no mapping for prefix): {file_path}")
                    print(f"   {report_name}: processed {mapped_count} CSV file(s)")
                    end_file(report_name, "success")
                    reports_ok += 1
                except Exception as inner_e:
                    logger.error(f"[ERROR] Failed processing report {report_name}: {str(inner_e)}", exc_info=True)
                    end_file(report_name, "failed")
                    step_failed = True
                    reports_failed += 1
                    print(f"   Failed to map fields for {report_name}: {inner_e}")
    except Exception as outer_e:
        logger.error(f"[ERROR] map_fields global failure: {str(outer_e)}", exc_info=True)
        step_failed = True
        print(f"map_fields step failed: {outer_e}")

    print(f"\n{'='*60}")
    print(f" FIELD MAPPING SUMMARY: {reports_ok} ok, {reports_failed} failed, {len(processed_reports)} total")
    print(f"{'='*60}\n")

    finalize(logger, force_fail=step_failed)

# ====================================
# Data Source Creation
# ====================================

def generate_data_source(model_name, client, settings, logger, overwrite_existing=False,split=True):

    assets_folder = Path(settings["assets_folder_path"])

    #Path where the origin file used to obtain m_query code is
    output_qv_restructured_folder_path = Path(settings["output_qv_restructured_folder_path"])

    print(f"\n{'='*60}")
    print(f" DATA SOURCE CREATION (M QUERY)")
    print(f"{'='*60}")
    print(f"Scanning for script.qvs files in: {output_qv_restructured_folder_path}")

    all_qvs_scripts = process_files_by_name(output_qv_restructured_folder_path, "script.qvs", "utf-16", logger)
    print(f"Found {len(all_qvs_scripts)} script.qvs file(s) to process")
    print(f"Model: {model_name} | overwrite={overwrite_existing} | split={split}")

    # ========Execution history and monitoring ========
    execution_path = output_qv_restructured_folder_path / "execution_log.json"
    start_file, end_file, finalize = start_step_tracking("generate_data_source", json_path=execution_path)
    step_failed = False

    reports_ok = 0
    reports_skipped = 0
    reports_failed = 0

    try:
        # Process each QVS script
        for file_path, qvs_content in all_qvs_scripts.items():

            qvw_name = Path(file_path).parts[-3]

            print(f"\n [{qvw_name}] Generating M query from {os.path.basename(file_path)}")

            # ========Execution history and monitoring ========
            start_file(qvw_name)

            #File location
            m_output_path = os.path.join(os.path.dirname(file_path), "m_query_output.csv")

            # Case 2 Run Option: If output already exists we move to the next step
            if os.path.exists(m_output_path) and not overwrite_existing:
                logger.info(f"Skipping {file_path} - m_query_output.csv already exists.")
                print(f"    Skipping — m_query_output.csv already exists at {m_output_path}")

                # ========Execution history and monitoring ========
                end_file(qvw_name, "skipped")
                reports_skipped += 1
                continue

            # Case 2 Overwrite Option: Overwrite enabled → force process
            elif overwrite_existing and os.path.exists(m_output_path):
                logger.info(f"Overwriting existing: m_query_output.csv for {qvw_name} ")
                print(f"   Overwriting existing m_query_output.csv for {qvw_name}")
                try:
                    if os.path.exists(m_output_path):
                        os.remove(m_output_path)
                        print(f"    Deleted stale file: {m_output_path}")
                except Exception as e:
                    print(f"    Failed to delete {m_output_path}: {e}")

            line_count = len(qvs_content.splitlines())
            print(f"   Script has {line_count} lines")
            logger.info(f"The script {file_path} has {line_count} lines.")

            split = str(split).strip().lower() in ("y", "yes", "true", "1")

            tabs = split_qvs_by_tab(qvs_content) if split else [("FullScript", qvs_content)]
            print(f"   Split into {len(tabs)} tab(s)")
            output_rows = []

            #Building of the RAG embedded knowledge database
            build_embedding_m_query(client,assets_folder)

            for tab_name, tab_code in tabs:
                try:
                    print(f"      Processing tab: {tab_name} ({len(tab_code.splitlines())} lines)  calling {model_name}")
                    logger.info(f"Processing tab: {tab_name} ({len(tab_code.splitlines())} lines)")

                    prompt = generate_data_source_prompt(tab_name, tab_code, client, assets_folder)

                    response = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": "You are a data transformation expert specializing in Power BI M Query."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.5
                    )

                    output_text = response.choices[0].message.content.strip().replace("```m", "").replace("```", "")
                    parsed = extract_table_blocks(output_text)
                    print(f"     Tab {tab_name}: extracted {len(parsed)} table block(s)")
                    output_rows.extend(parsed)

                except Exception as e:
                    print(f"     Failed processing tab: {tab_name} - {e}")
                    logger.error(f"Failed processing tab: {tab_name} - {e}")

            try:
                # Save CSV with each table split into rows
                save_m_query_to_csv(output_rows, file_path, logger)

                # ========Execution history and monitoring ========
                end_file(qvw_name, "success")
                reports_ok += 1
                print(f"   {qvw_name}: {len(output_rows)} M query table(s) saved")

            except Exception as e:

                # ========Execution history and monitoring ========
                step_failed=True
                end_file(qvw_name, "failed")
                reports_failed += 1

                print(f"   Failed to generate M Query script for {qvw_name}: {e}")
                logger.error(f"Failed to generate M Query script for {file_path}: {e}")

    except Exception as e:
        # ========Execution history and monitoring ========
        step_failed=True
        print(f" generate_data_source global failure: {e}")
        logger.error(f"generate_data_source global failure: {e}", exc_info=True)

    print(f"\n{'='*60}")
    print(f" DATA SOURCE SUMMARY: {reports_ok} ok, {reports_skipped} skipped, {reports_failed} failed")
    print(f"{'='*60}\n")

    # ========Execution history and monitoring ========
    finalize(logger, force_fail=step_failed)

# ====================================
# QlikView Expressions to DAX Translation
# ====================================

def generate_expression_to_dax(model_name, client, settings, logger, overwrite_existing=False):

    output_qv_restructured_folder_path = Path(settings["output_qv_restructured_folder_path"])

    execution_path = output_qv_restructured_folder_path / "execution_log.json"
    start_file, end_file, finalize = start_step_tracking("generate_expression_to_dax", json_path=execution_path)

    print(f"\n{'='*60}")
    print(f" EXPRESSION  DAX TRANSLATION")
    print(f"{'='*60}")
    print(f"Scanning for expressions.csv in: {output_qv_restructured_folder_path}")
    print(f"Model: {model_name} | overwrite={overwrite_existing}")

    step_failed = False
    try:
        all_qlik_expressions = process_files_by_name(
            output_qv_restructured_folder_path,
            "expressions.csv",
            "utf-16",
            logger)
        print(f"Found {len(all_qlik_expressions)} expressions.csv file(s) to translate")
        generate_dax(
            model_name, client,
            all_qlik_expressions,
            logger,
            overwrite_existing=overwrite_existing,
            start_file=start_file,
            end_file=end_file)
        print(f"\n{'='*60}")
        print(f" DAX TRANSLATION COMPLETED")
        print(f"{'='*60}\n")
    except Exception as e:
        step_failed=True
        logger.error(f"[FATAL] DAX generation failed: {e}", exc_info=True)
        print(f" DAX generation failed: {e}")

    finalize(logger, force_fail=step_failed)

# ====================================
# QV Export PDF and Save Images Per Page
# ====================================

def report_exports(settings, logger, overwrite_existing=False, multiplier=1):

    root_folder = Path(settings["root_folder_path"])
    output_qv_restructured_folder_path = Path(settings["output_qv_restructured_folder_path"])
    qv_output_folder = Path(settings["output_qv_folder_path"])

    execution_path = output_qv_restructured_folder_path / "execution_log.json"

    qvw_files = list(root_folder.rglob("*.qvw"))
    cache_path = "output/qvw_metadata_cache.json"
    cache = load_qvw_cache(cache_path)

    print(f"\n{'='*60}")
    print(f" REPORT PDF EXPORT")
    print(f"{'='*60}")
    print(f"Scanning QVWs in: {root_folder}")
    print(f"Found {len(qvw_files)} QVW file(s) | overwrite={overwrite_existing}")

    reports_ok = 0
    reports_skipped = 0
    reports_failed = 0

    # === Setup step tracking ===
    start_file, end_file, finalize = start_step_tracking("report_exports", json_path=execution_path)

    #only folders we dont have, filter it
    for qvw_file in qvw_files:
        try:
            report_name = qvw_file.stem
            start_file(report_name)

            #output/qvw_metadata_restructured/{report_name}
            reports_pdf_folder = output_qv_restructured_folder_path / report_name

            #output/qvw_metadata_restructured/{report_name}/ReportPages
            reportpages_folder = reports_pdf_folder / "ReportPages"

            #output/qvw_metadata_restructured/{report_name}/ReportPages/page_dimensions.json
            json_path = os.path.join(reportpages_folder,"page_dimensions.json")

            #output/qvw_metadata_restructured/{report_name}/ReportPages/Pages_{report_name}.pdf
            output_pdf_path = os.path.join(reportpages_folder, f"Pages_{report_name}.pdf")
            
            metadata_folder = qv_output_folder / report_name
            sheets_csv_path= metadata_folder / "sheets.csv"

            needs_processing = False
            window_opened = False

            # Case 1 Run Option: Final json does not exist → always process
            if not os.path.exists(json_path):
                os.makedirs(reportpages_folder, exist_ok=True)
                logger.info(f"[NEW] PDF doesn't exist for {qvw_file.name}. Processing it.")
                print(f"\n [NEW] Generating PDF for: {qvw_file.name}")
                needs_processing = True

            # Case 2 Overwrite Option: Overwrite enabled → force process
            elif overwrite_existing:
                logger.info(f"Overwriting existing PDF for: {qvw_file.name}")
                print(f"\n [OVERWRITE] Regenerating PDF for: {qvw_file.name}")
                if os.path.exists(reportpages_folder):
                    shutil.rmtree(reportpages_folder)
                    os.makedirs(reportpages_folder, exist_ok=True)
                needs_processing = True

            # Case 3: Check if the file has changed for Run option
            elif should_process_qvw(qvw_file, cache, relative_to=root_folder):
                logger.info(f"Auto-processing changed file: {qvw_file.name}")
                print(f"\n [CHANGED] Auto-processing: {qvw_file.name}")
                if os.path.exists(reportpages_folder):
                    shutil.rmtree(reportpages_folder)
                    os.makedirs(reportpages_folder, exist_ok=True, parent_dir=True)
                needs_processing = True

            # Case 4: No action needed
            else:
                logger.info(f"No changes in {qvw_file.name}. Skipping.")
                print(f"    [SKIP] No changes in {qvw_file.name}")
                end_file(report_name, "skipped")
                reports_skipped += 1
                continue

            # Perform processing if needed
            if needs_processing:
                print(f"    Automating QlikView  PDF export")
                automate_qlikview_report_to_pdf(qvw_file, output_pdf_path, logger, multiplier=multiplier)
                time.sleep(2)
                print(f"    Splitting PDF by sheets using {sheets_csv_path.name}")
                split_pdf_by_sheets(
                    output_pdf_path,
                    sheets_csv_path,
                    reportpages_folder,
                    logger
                )
                close_qv_window(logger)
                update_qvw_cache_entry(qvw_file, cache, relative_to=root_folder)
                end_file(report_name, "success")
                reports_ok += 1
                print(f"   Report exported: {output_pdf_path}")

        except Exception as e:
            print(f"   Report export failed for {qvw_file.name}: {e}")
            logger.error(f"[ERROR] Failed to process {qvw_file.name}: {str(e)}", exc_info=True)
            end_file(report_name, "failed")
            reports_failed += 1

    save_qvw_cache(cache_path, cache)

    print(f"\n{'='*60}")
    print(f" REPORT PDF EXPORT SUMMARY: {reports_ok} ok, {reports_skipped} skipped, {reports_failed} failed")
    print(f"{'='*60}\n")

    summary = finalize(logger)

# ====================================
# Generate insights of outputs
# ====================================
def transform_output_from_csv(settings, logger,overwrite_existing=False):
    output_root = Path(settings["output_qv_restructured_folder_path"])
    root_folder = Path(settings["root_folder_path"])
    field_mapping = Path(settings["field_mapping_file_path"])
    qvw_files = list(root_folder.rglob("*.qvw"))

    execution_path = output_root / "execution_log.json"
    start_file, end_file, finalize = start_step_tracking("output_analysis", json_path=execution_path)
    step_failed = False

    print(f"\n{'='*60}")
    print(f" OUTPUT ANALYSIS (structured JSON)")
    print(f"{'='*60}")
    print(f"Scanning QVWs in: {root_folder}")
    print(f"Found {len(qvw_files)} QVW file(s) | overwrite={overwrite_existing}")

    reports_ok = 0
    reports_skipped = 0
    reports_failed = 0

    for qvw_file in qvw_files:

        try:
            report_name = qvw_file.stem
            start_file(report_name)
            report_folder = output_root / report_name
            output_analysis_folder = report_folder / "Outputanalysis"
            output_analysis_file = output_analysis_folder / "enriched_objects.json"

            needs_processing = False
            logger.info(f"Processing QVW folder: {qvw_file.name}")

            # Case 1: Output does not exist
            if not output_analysis_file.exists():
                logger.info(f"[NEW] Analysis output missing for {qvw_file.name}. Will generate.")
                print(f"\n [NEW] Generating analysis for: {qvw_file.name}")
                needs_processing = True

            # Case 2: Overwrite is enabled
            elif overwrite_existing:
                if output_analysis_folder.exists():
                    shutil.rmtree(output_analysis_folder)
                logger.info(f"[OVERWRITE] Forcing analysis output for: {qvw_file.name}")
                print(f"\n [OVERWRITE] Regenerating analysis for: {qvw_file.name}")
                needs_processing = True

            # Case 4: No changes
            else:
                logger.info(f"[SKIP] Analysis already exists for {qvw_file.name}.")
                print(f"    [SKIP] Analysis already exists for {qvw_file.name}")
                end_file(report_name, "skipped")
                reports_skipped += 1
                continue

            # Execute processing
            if needs_processing:
                print(f"    Generating structured JSONs under {output_analysis_folder}")
                generate_outputanalysis_jsons(report_folder, logger, field_mapping)
                logger.info(f"JSON output generated for: {qvw_file.name}")
                if output_analysis_folder.exists():
                    files_created = sorted(output_analysis_folder.glob("*"))
                    print(f"   Created {len(files_created)} file(s) in Outputanalysis/")
                    for f in files_created:
                        print(f"      - {f.name}")
                print(f"   Analysis done for: {qvw_file.name}")
                end_file(report_name, "success")
                reports_ok += 1
        except Exception as e:
            end_file(report_name, "failed")
            step_failed = True
            reports_failed += 1
            logger.error(f"Failed to process {qvw_file.name}: {str(e)}", exc_info=True)
            print(f"   Failed analysis for {qvw_file.name}: {e}")

    print(f"\n{'='*60}")
    print(f" OUTPUT ANALYSIS SUMMARY: {reports_ok} ok, {reports_skipped} skipped, {reports_failed} failed")
    print(f"{'='*60}\n")

    finalize(logger, force_fail=step_failed)

# ====================================
# Upload files
# ====================================
def upload_qvw_stream_to_sharepoint(file_bytes: bytes, filename: str, cookies: dict, logger) -> bool:
    digest = get_sharepoint_digest(cookies)
    if not digest:
        logger.error("❌ Could not retrieve x-requestdigest.")
        return False

    return upload_qvw_stream(filename, file_bytes, cookies, digest, logger)

# ====================================
# Replicate output_qv_restructured_folder_path directory in sharepoint
# ====================================
def upload_restructured_metadata_to_sharepoint(settings: dict, cookies: dict, logger) -> bool:

    """
    Orchestrates the upload of the entire 'qvw_metadata_restructured' folder to SharePoint.
    
    Args:
        settings (dict): Your global settings, must contain 'output_qv_restructured_folder_path'.
        cookies (dict): Dictionary with SharePoint authentication cookies.
        logger: Logger instance.

    Returns:
        bool: True if upload succeeded, False otherwise.
    """
    local_dir = Path(settings["output_qv_restructured_folder_path"])
    remote_dir = "/Shared Documents/MigrationQlikFabric/qvw_metadata_restructured"

    logger.info(f"Starting recursive upload from {local_dir} to {remote_dir}")
    
    success = recursively_upload_folder_to_sharepoint(local_dir, remote_dir, cookies, logger)

    if success:
        logger.info("All folders and files uploaded successfully.")
    else:
        logger.error("Some uploads failed or were skipped.")

    return success

# ====================================
# Validation - Analyze PBI Report
# ====================================

def process_all_reports(settings, client, logger, overwrite_existing=False) -> List[Dict[str, Any]]:
    
    """Process all Power BI reports in the specified directory"""
    
    logger.info(f"Starting Power BI report processing...")
    local_folder_path = Path(settings["local_folder_path"])

    #Base Path
    output_folder_path = os.path.join(local_folder_path, "output")
    validation_folder_path = os.path.join(output_folder_path, "qlik_pbi_validation")
    pbi_validation_folder_path = os.path.join(validation_folder_path, "pbi")

    #Input path: C:\Users\CatherineVaras\Documents\DataMigrationTool\Fabric Migration\output\qlik_pbi_validation\pbi\original_pbi_report
    input_path = Path(os.path.join(pbi_validation_folder_path, "original_pbi_report"))

    #Output path: C:\Users\CatherineVaras\Documents\DataMigrationTool\Fabric Migration\output\qlik_pbi_validation\pbi\json_reports_analysis
    output_path = Path(os.path.join(pbi_validation_folder_path, "extracted_reports_images"))

    logger.info(f"Input path: {input_path}")
    logger.info(f"Output path: {output_path}")
    
    # Ensure output directory exists
    ensure_output_directory(output_path)
    
    # Get all Power BI files
    pbi_files = get_pbi_files(input_path, logger)
    
    if not pbi_files:
        logger.warning(f"No Power BI files found in {input_path}")
        return []
    
    logger.info(f"Found {len(pbi_files)} Power BI files to process")
    
    results = []

    # Process each file
    for i, pbi_file in enumerate(pbi_files, 1):
        logger.info(f"Processing file {i}/{len(pbi_files)}: {pbi_file.name}")
        
        result = process_single_report(pbi_file, output_path, logger,overwrite_existing)
        results.append(result)
        
        # Add delay between files to allow system recovery
        if i < len(pbi_files):
            logger.info("Waiting before processing next file...")
            time.sleep(3)
    
    convert_all_pdfs_to_images(output_path, logger)

    analyze_powerbi_reports(settings, client, logger, overwrite_existing=False)

    return results

# ====================================
# Validation - Analyze QlikView Report
# ====================================

def analyze_qlikview_reports(settings, client, logger, overwrite_existing=False):
    """
    Process all report pages (images) in each QVW report folder and generate structured JSON analysis.

    Args:
        output_qv_restructured_folder_path (str): Base path to 'qvw_metadata_restructured'
        validation_output_folder (str): Path where the output JSON folders will be stored
    """
    instruction = obtain_prompt_for_image_analysis()
    
    local_folder_path = Path(settings["local_folder_path"])
    output_qv_restructured_folder_path = Path(settings["output_qv_restructured_folder_path"])

    # Output folder for current report

    output_folder_path = os.path.join(local_folder_path, "output")
    validation_folder_path = os.path.join(output_folder_path, "qlik_pbi_validation")
    qlik_validation_folder_path = os.path.join(validation_folder_path, "qlik_view")

    model_name = "gpt-4o"

    # Walk through each QVW report directory
    for report_name in os.listdir(output_qv_restructured_folder_path):
        report_path = os.path.join(output_qv_restructured_folder_path, report_name)
        report_pages_path = os.path.join(report_path, "ReportPages")
        
        output_report_folder = os.path.join(qlik_validation_folder_path, report_name)

        if not os.path.isdir(report_pages_path):
            continue  # Skip if no ReportPages
        
        # Case: Overwrite is enabled
        if overwrite_existing:
            if os.path.exists(output_report_folder):
                shutil.rmtree(output_report_folder)
            logger.info(f"[OVERWRITE] Image output missing for {report_name}.")
            print(f"[OVERWRITE] Image output missing for {report_name}.")
        # Case: Folder doesn’t exist or is empty (first-time run)
        elif not os.path.exists(output_report_folder) or not os.listdir(output_report_folder):
            logger.info(f"[NEW] Image output missing for {report_name}. Will extract.")
            print(f"[NEW] Extracting Image info for: {report_name}")
        # Case: Folder already exists and is not empty and overwrite is False → skip
        elif os.path.exists(output_report_folder) and os.listdir(output_report_folder):
            logger.info(f"[SKIP] Image output already exists for {report_name}.")
            print(f"[SKIP] Image output already exists for {report_name}")
            continue
        
        print(f" Processing report: {report_name}")
        os.makedirs(output_report_folder, exist_ok=True)

        for filename in os.listdir(report_pages_path):
            if not filename.lower().endswith((".png", ".jpg", ".jpeg")):
                continue
            
            os.makedirs(output_report_folder, exist_ok=True)

            image_path = os.path.join(report_pages_path, filename)
            print(f" Analyzing: {image_path}")

            try:
                result = process_report_image(image_path, instruction, client, model_name)
                save_analysis_result(result, image_path, output_report_folder)
            except Exception as e:
                print(f"Error processing {image_path}: {e}")

# ====================================
# Validation - Compare PBI with Qlik View Report
# ====================================

def compare_qlikview_powerbi_reports(settings, client, logger, overwrite_existing = False):
    """
    Compare QlikView and Power BI reports using AI analysis.
    
    Args:
        settings: Dictionary containing paths and configuration
        client: OpenAI client instance
        logger: Logger instance
        overwrite_existing: Whether to overwrite existing comparisons
    """
    output_qv_restructured_folder_path = Path(settings["output_qv_restructured_folder_path"])

    #Obtain info from the from the Qlik View report pages
    
    analyze_qlikview_reports(settings, client, logger, overwrite_existing)

    #Obtain info from the Power BI report pages
    
    process_all_reports(settings, client, logger, overwrite_existing) 

    # Get paths from settings
    local_folder_path = Path(settings["local_folder_path"])

    #Base Path
    output_folder_path = os.path.join(local_folder_path, "output")
    validation_folder_path = os.path.join(output_folder_path, "qlik_pbi_validation")    
    
    # Path to QlikView JSON reports: C:\Users\CatherineVaras\Documents\DataMigrationTool\Fabric Migration\output\qlik_pbi_validation\qlik_view
    qlik_json_path = Path(os.path.join(validation_folder_path, "qlik_view"))

    # Path to Power BI JSON reports: C:\Users\CatherineVaras\Documents\DataMigrationTool\Fabric Migration\output\qlik_pbi_validation\pbi\json_reports_analysis
    pbi_validation_folder_path = os.path.join(validation_folder_path, "pbi")
    pbi_json_path = Path(os.path.join(pbi_validation_folder_path, "json_reports_analysis"))
    
    # Define output paths
    output_folder = os.path.join(local_folder_path, "output")
    analysis_folder = os.path.join(output_folder, "qlik_pbi_validation")
    comparison_folder = os.path.join(output_folder, "qlik_pbi_comparison")

    model_name = "gpt-4o"
    
    # Validate paths
    if not os.path.exists(qlik_json_path):
        logger.error(f"QlikView JSON path does not exist: {qlik_json_path}")
        return
    
    if not os.path.exists(pbi_json_path):
        logger.error(f"Power BI JSON path does not exist: {pbi_json_path}")
        return
    
    # Get all report names from QlikView folder
    qlik_reports = [d for d in os.listdir(qlik_json_path) 
                   if os.path.isdir(os.path.join(qlik_json_path, d))]
    
    # Get all report names from Power BI folder
    pbi_reports = [d for d in os.listdir(pbi_json_path) 
                  if os.path.isdir(os.path.join(pbi_json_path, d))]
    
    print(f"Found {len(qlik_reports)} QlikView reports and {len(pbi_reports)} Power BI reports")
    
    # Find matching reports
    matching_reports = set(qlik_reports) & set(pbi_reports)
    missing_in_pbi = set(qlik_reports) - set(pbi_reports)
    missing_in_qlik = set(pbi_reports) - set(qlik_reports)
    
    if missing_in_pbi:
        print(f"Reports in QlikView but not in Power BI: {missing_in_pbi}")
    if missing_in_qlik:
        print(f"Reports in Power BI but not in QlikView: {missing_in_qlik}")
        
    print(f"Matching reports to compare: {len(matching_reports)}")
    
    # ================  Execution history and monitoring ================      
    execution_path = output_qv_restructured_folder_path / "execution_log.json"
    start_file, end_file, finalize = start_step_tracking("comparison_qlikview_powerbi", json_path=execution_path)
    step_failed = False

    # Process each matching report
    for report_name in matching_reports:
        print(f"\nComparing report: {report_name}")
    
        # ========Execution history and monitoring ========
        start_file(report_name)

        # Get QlikView pages
        qlik_report_path = os.path.join(qlik_json_path, report_name)
        qlik_pages = get_report_pages(qlik_report_path)
        
        # Get Power BI pages
        pbi_report_path = os.path.join(pbi_json_path, report_name)
        pbi_pages = get_report_pages(pbi_report_path)
        
        print(f"  QlikView pages: {len(qlik_pages)}, Power BI pages: {len(pbi_pages)}")
        
        # Compare pages (match by page number or order)
        max_pages = max(len(qlik_pages), len(pbi_pages))
        
        for i in range(max_pages):
            qlik_page = qlik_pages[i] if i < len(qlik_pages) else None
            pbi_page = pbi_pages[i] if i < len(pbi_pages) else None
            
            if qlik_page and pbi_page:
                page_info = f"QlikView Page {qlik_page[0]} ({qlik_page[1]}) vs Power BI Page {pbi_page[0]} ({pbi_page[1]})"
                print(f"  Comparing: {page_info}")
                
                try:
                    # Create comparison prompt
                    messages = create_comparison_prompt(qlik_page[2], pbi_page[2], page_info)
                    print(f"  Succesful message generation.")

                    # Get AI analysis
                    analysis_result = query_openai_comparison(messages, model_name, client)
                    print(f"  Succesful analysis result.")

                    # Extract image URLs from both JSON files
                    qlik_image_url = extract_image_url_from_json(qlik_page[2])
                    pbi_image_url = extract_image_url_from_json(pbi_page[2])

                    #Create the folder path to save the result
                    folder_path = Path(os.path.join(comparison_folder, report_name))
                    folder_path.mkdir(parents=True, exist_ok=True)

                    # Also save as JSON file for reference
                    json_filename = f"{report_name}_page{qlik_page[0]}_vs_page{pbi_page[0]}_comparison.json"
                    json_filepath = os.path.join(folder_path, json_filename)
                    
                    print(f" Succesful comparison.")

                    try:

                        # Try to extract and parse JSON from the AI response
                        parsed_json = extract_json_from_markdown(analysis_result)
                        
                        # Add image URLs to the comparison result
                        if isinstance(parsed_json, dict):
                            parsed_json["qlikview_image"] = qlik_image_url
                            parsed_json["pbi_image"] = pbi_image_url
                            parsed_json["qlikview_page_info"] = {
                                "page_number": qlik_page[0],
                                "page_name": qlik_page[1]
                            }
                            parsed_json["pbi_page_info"] = {
                                "page_number": pbi_page[0],
                                "page_name": pbi_page[1]
                            }
                        else:
                            # If parsed_json is not a dict, wrap everything
                            parsed_json = {
                                "comparison_analysis": parsed_json,
                                "qlikview_image": qlik_image_url,
                                "pbi_image": pbi_image_url,
                                "qlikview_page_info": {
                                    "page_number": qlik_page[0],
                                    "page_name": qlik_page[1]
                                },
                                "pbi_page_info": {
                                    "page_number": pbi_page[0],
                                    "page_name": pbi_page[1]
                                }
                            }
                        
                        # Only create file if JSON parsing was successful
                        with open(json_filepath, 'w', encoding='utf-8') as f:
                            json.dump(parsed_json, f, indent=2, ensure_ascii=False)

                    except (json.JSONDecodeError, ValueError) as e:
                        print(f"Error: Could not parse JSON from AI response: {e}")
                        print(f"Failed to create comparison file for {report_name} page {qlik_page[0]} vs page {pbi_page[0]}. No file will be created.")
                        step_failed = True
                    
                    print(f"\nComparison completed. Results saved to: {comparison_folder}")

                except Exception as e:
                    # ========Execution history and monitoring ========
                    step_failed=True
                    end_file(report_name, "failed")

                    logger.error(f"Error comparing {report_name} pages: {e}")
                    print(f"  Error: {e}")
                
                # ========Execution history and monitoring ========
                end_file(report_name, "success")
            
            elif qlik_page and not pbi_page:
                print(f"  QlikView page {qlik_page[0]} has no corresponding Power BI page")
                # Log missing page
                
                # ========Execution history and monitoring ========
                end_file(report_name, "skipped")

            elif pbi_page and not qlik_page:
                print(f"  Power BI page {pbi_page[0]} has no corresponding QlikView page")
                # Log additional page
                
                # ========Execution history and monitoring ========
                end_file(report_name, "skipped")

    # ========Execution history and monitoring ========
    finalize(logger, force_fail=step_failed)

    









