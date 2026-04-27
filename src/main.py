from pathlib import Path
from src.utils import load_settings, setup_logger, prompt_user, initialize_azure_openai_client, process_user_input, initial_user_input
from src.executor import transform_output_from_csv,extract_qv_metadata, analyze_qlikview_reports, report_exports, check_and_rerun_if_needed, parse_xml, map_fields, generate_data_source, generate_expression_to_dax, upload_restructured_metadata_to_sharepoint, process_all_reports, compare_qlikview_powerbi_reports

def main():
    try:
        print("Starting script execution...")
        
        # Make sure output/logs folder exists
        Path("output/logs").mkdir(exist_ok=True)

        # Setup separate loggers for app, metadata and data source
        app_logger = setup_logger("app_logger", "output/logs/app.log")
        metadata_logger = setup_logger("metadata_logger", "output/logs/qv_metadata_automation.log")
        report_pages_logger = setup_logger("report_pages_logger", "output/logs/qv_report_pages_logger.log")
        datasource_logger = setup_logger("datasource_logger", "output/logs/datasource_creation.log")
        xml_parser_logger = setup_logger("xml_parser_logger", "output/logs/xml_parser.log")
        field_mapping_logger = setup_logger("field_mapping_logger", "output/logs/field_mapping.log")
        expression_logger = setup_logger("dax_logger", "output/logs/expression_translation.log")
        output_logger = setup_logger("output_analysis_logger", "output/logs/output_analysis.log")
        upload_logger = setup_logger("upload_logger", "output/logs/upload_sharepoint.log")
        comparison_qlikview_powerbi_logger = setup_logger("comparison_qlikview_powerbi_logger", "output/logs/comparison_qlikview_powerbi.log")

        # Load settings from JSON file
        app_logger.info("Starting script execution")
        app_logger.info("Loading settings from settings.json")
        settings_path = Path("settings.json")

        if not settings_path.is_file():
            app_logger.error(f"Settings file not found: {settings_path}")
            print(f"Settings file not found: {settings_path}")
            exit(1)

        settings = load_settings(str(settings_path))

        overwrite_existing = False

        # ====================================
        # Prompt User for Run Procedure
        # ====================================

        app_logger.info("User prompted for run procedure")
        response = initial_user_input()
        run_all_steps = response

        if run_all_steps:
            print("Proceeding with the full migration procedure...")
            app_logger.info("User chose to run all steps")
        else:
            print("You will be prompted to choose each step individually.")
            app_logger.info("User chose to run steps individually")
        
        # ====================================
        # QV Metadata Extraction
        # ====================================

        if (overwrite_existing := process_user_input("QV Metadata Extraction", run_all_steps, app_logger)) is not None:
            try:
                msg_suffix = " with overwrite" if overwrite_existing else ""
                metadata_logger.info(f"Starting metadata extraction{msg_suffix}")
                print(f"Starting metadata extraction{msg_suffix}...")
                extract_qv_metadata(settings, metadata_logger, overwrite_existing=overwrite_existing)
                metadata_logger.info(f"Metadata extraction{msg_suffix} completed")
                print(f"Metadata extraction{msg_suffix} completed")

                # Check and rerun if needed
                print("Checking for missing or invalid output folders...")
                check_and_rerun_if_needed(settings, metadata_logger)
                print("Missing or invalid output folders checked and handled.")
            except Exception:
                metadata_logger.exception("Metadata extraction failed")
                print("Metadata extraction failed. Check logs for details.")
                raise
        
        # ====================================
        # XML Parser
        # ====================================

        if (overwrite_existing := process_user_input("XML Parser", run_all_steps, app_logger)) is not None:
            try:
                msg_suffix = " with overwrite" if overwrite_existing else ""
                xml_parser_logger.info(f"Starting XML parsing{msg_suffix}")
                print(f"Starting XML parsing{msg_suffix}...")
                parse_xml(settings, xml_parser_logger, overwrite_existing=overwrite_existing)
                xml_parser_logger.info("XML parsing completed")
                print(f"XML parsing{msg_suffix} completed")
                app_logger.info(f"XML parsing{msg_suffix} completed")
            except Exception:
                xml_parser_logger.exception("XML parsing failed")
                print("XML parsing failed. Check logs for details.")
                raise

        # ====================================
        # Fields Mapping (dependent on XML parser)
        # ====================================

        if (overwrite_existing := process_user_input("Fields Mapping", run_all_steps, app_logger)) is not None:
            try:
                msg_suffix = " with overwrite" if overwrite_existing else ""
                field_mapping_logger.info(f"Starting Fields Mapping{msg_suffix}")
                print(f"Starting Fields Mapping{msg_suffix}...")
                map_fields(settings, field_mapping_logger, overwrite_existing=overwrite_existing)
                field_mapping_logger.info(f"Fields mapping{msg_suffix} completed")
                print(f"Fields mapping{msg_suffix} completed")
                app_logger.info(f"Fields mapping{msg_suffix} completed")
            except Exception:
                field_mapping_logger.exception("Fields mapping failed")
                print("Fields mapping failed. Check logs for details.")
                raise

        # ====================================
        # Initialise Azure OpenAI
        # ====================================

        try:
            app_logger.info("Initialising Azure OpenAI client...")
            print("Initialising Azure OpenAI client...")
            api_key = settings["api_key"]
            azure_endpoint = settings["azure_endpoint"]
            client = initialize_azure_openai_client(api_key, azure_endpoint)
            app_logger.info("Azure OpenAI client initialized successfully.")
            print("Azure OpenAI client initialized")
        except:
            app_logger.error("Failed to initialize Azure OpenAI client.")
            raise ValueError("Failed to initialize Azure OpenAI client. Check your API key and endpoint.")
        
        # ====================================
        # Data Source Creation
        # ====================================

        if (overwrite_existing := process_user_input("Data Source Creation", run_all_steps, app_logger)) is not None:
            try:
                msg_suffix = " with overwrite" if overwrite_existing else ""
                datasource_logger.info(f"Starting data source creation{msg_suffix}")
                print(f"Starting data source creation{msg_suffix}...")
                split = input("Do you want to split the script by tabs and process them individually? [y/n]: ")
                model_name = "gpt-4o"
                generate_data_source(model_name, client, settings, datasource_logger, overwrite_existing=overwrite_existing,split=split)
                datasource_logger.info(f"Data source creation{msg_suffix} completed")
                print(f"Data source creation{msg_suffix} completed")
            except Exception:
                datasource_logger.exception("Data source creation failed")
                raise
        
        # ====================================
        # QlikView Expressions to DAX Translation
        # ====================================

        if (overwrite_existing := process_user_input("QlikView Expressions to DAX Translation", run_all_steps, app_logger)) is not None:
            try:
                msg_suffix = " with overwrite" if overwrite_existing else ""
                expression_logger.info(f"Starting QlikView expressions to DAX translation{msg_suffix}")
                print(f"Starting QlikView expressions to DAX translation{msg_suffix}...")
                model_name = "gpt-4o"
                generate_expression_to_dax(model_name, client, settings, expression_logger, overwrite_existing=overwrite_existing)
                expression_logger.info(f"QlikView expressions to DAX translation{msg_suffix} completed")
                print(f"QlikView expressions to DAX translation{msg_suffix} completed")
                app_logger.info(f"QlikView expressions to DAX translation{msg_suffix} completed")
            except Exception:
                expression_logger.exception("QlikView expressions to DAX translation failed")
                raise
        
        # ====================================
        # QV Report PDF Generation
        # ====================================

        if (overwrite_existing := process_user_input("QV Report PDF Generation", run_all_steps, app_logger)) is not None:
            try:
                msg_suffix = " with overwrite" if overwrite_existing else ""
                report_pages_logger.info(f"Starting report PDF generation{msg_suffix}")
                print(f"Starting report PDF generation{msg_suffix}...")
                report_exports(settings, report_pages_logger, overwrite_existing=overwrite_existing, multiplier=1)
                report_pages_logger.info(f"Report PDF generation{msg_suffix} completed")
                print(f"Report PDF generation{msg_suffix} completed")
            except Exception:
                report_pages_logger.exception("Report PDF generation")
                print("Report PDF generation. Check logs for details.")
                raise
            
        # ================================
        # QVW Structured Output Generation
        # ================================
        if (overwrite_existing := process_user_input("Generate Structured Output", run_all_steps, app_logger)) is not None:
            try:
                output_logger.info("Starting structured output generation from QVW metadata...")
                transform_output_from_csv(settings, output_logger, overwrite_existing=overwrite_existing)
                output_logger.info("Structured output completed")
                print("Structured output completed.")
            except Exception:
                output_logger.exception("Structured output generation failed")
                print("Output generation failed. Check logs.")
                raise

        # ================================
        # Upload Structured Output to SharePoint
        # ================================
        if (process_user_input("Upload structured output to SharePoint", run_all_steps, app_logger)) is not None:
            try:
                # Prompt for cookies
                print("Please enter your SharePoint authentication cookies:")
                fedauth = input("FedAuth: ").strip().replace(" ", "")
                rtfa = input("rtFa: ").strip().replace(" ", "")

                cookies = {
                    "FedAuth": fedauth,
                    "rtFa": rtfa
                }

                upload_logger.info("Starting recursive upload to SharePoint...")
                success = upload_restructured_metadata_to_sharepoint(settings, cookies, output_logger)

                if success:
                    upload_logger.info("SharePoint upload completed successfully.")
                    print(" Upload completed successfully.")
                else:
                    upload_logger.error("One or more files failed to upload.")
                    print(" Upload finished with some errors. Check logs.")

            except Exception as e:
                upload_logger.exception("SharePoint upload failed")
                print(" Upload failed. Check logs.")
                raise


        # ================================
        # Qlik View and Power BI Report Pages Analysis and Comparison for Validation
        # ================================

        if (overwrite_existing := process_user_input("Validation of reports through images analysis", run_all_steps, app_logger)) is not None:
            try:
                msg_suffix = " with overwrite" if overwrite_existing else ""
                comparison_qlikview_powerbi_logger.info(f"Starting validation of reports{msg_suffix}")
                print(f"Starting validation of reports{msg_suffix}...")
                compare_qlikview_powerbi_reports(settings, client, comparison_qlikview_powerbi_logger, overwrite_existing=overwrite_existing)
                comparison_qlikview_powerbi_logger.info(f"Validation of reports{msg_suffix} completed")
                print(f"Validation of reports{msg_suffix} completed")
            except Exception:
                comparison_qlikview_powerbi_logger.exception("Validation of reports failed")
                print("Validation of reports failed. Check logs for details.")
                raise

        

    # ====================================
    # Finalization and Error Handling
    # ====================================

    except KeyboardInterrupt:
        app_logger.warning("Script interrupted by user (KeyboardInterrupt).")
        print("Script interrupted by user. Exiting...")
        exit(1)
        
    except Exception as e:
        app_logger.critical("Script terminated due to errors", exc_info=True)
        print(f"Script failed: {e}. Check logs for details.")
        exit(1)

    finally:
        app_logger.info("Script execution finished")
        print("Script execution finished. Check logs for details.")

if __name__ == "__main__":
    main()
