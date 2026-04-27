# QlikView to Fabric Power BI Migration

## Project Structure

```plaintext
project_root/
├── assets/
├── data/
│   ├── input_qvw_extras/
│   └── input_qvw_samples/
├── output/
│   ├── logs/
│   ├── qvw_metadata/
│   └── qvw_metadata_restructured/
├── scripts/
│   └── (legacy scripts, to be refactored into src/)
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── executor.py
│   └── utils.py
├── .venv
├── .gitignore
├── README.md
├── requirements.txt
├── settings.json
└── settings.json.example
```

## Getting Started

Follow these steps to set up and run the project locally.

**Prerequisite**: [Install QlikView and DocumentAnalyzer v3.10](https://one51.atlassian.net/wiki/spaces/da/pages/363659265/Initial+Qlikview+Setup+for+Migration+Script)

### 1. Clone the repository

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
.venv/Scripts/activate             # Windows
source .venv/bin/activate          # Linux/macOS
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Add data files

Get data: [Link to sample folders to use](https://one51comau-my.sharepoint.com/my?id=%2Fpersonal%2Foswin%5Fhakim%5Fone51%5Fcom%5Fau%2FDocuments%2FMicrosoft%20Teams%20Chat%20Files%2Finput%5Fqvw%5Fextras%2Ezip&parent=%2Fpersonal%2Foswin%5Fhakim%5Fone51%5Fcom%5Fau%2FDocuments%2FMicrosoft%20Teams%20Chat%20Files)

Move the input_qvw_extras and input_qvw_samples folders into the `data/` folder

- input_qvw_extras: more reports for testing
- input_qvw_samples: smaller number of reports for testing

### 5. Set up configuration

Copy the example settings file and modify it accordingly:

```bash
cp settings.json.example settings.json
```

Then edit settings.json using the format below:

```json
{
  "DOCUMENT_ANALYZER_PATH": "C:/Users/YourName/Documents/DocumentAnalyzer_V3.10.qvw",
  "root_folder_path": "C:/Users/YourName/Documents/project_root/data/input_qvw_samples",
  "output_qv_folder_path": "C:/Users/YourName/Documents/project_root/output/qvw_metadata/qvwork",
  "output_qv_restructured_folder_path": "C:/Users/YourName/Documents/project_root/output/qvw_metadata_restructured",
  "api_key": "your api key",
  "azure_endpoint": "your azure openai endpoint",
  "field_mapping_file_path": "C:/Users/YourName/Documents/project_root/assets/field_mapping.csv"
}
```

Field Descriptions:

- DOCUMENT_ANALYZER_PATH: The full path to the DocumentAnalyzer.qvw file you extracted and successfully opened.
- root_folder_path: The folder containing the .qvw files you want to process (use `data/input_qvw_samples` path).
- output_qv_folder_path: The full path where QlikView stores its output, based on GetTempPath() + /qvwork. QlikView will create this subfolder automatically, so be sure to include it.
- output_qv_restructured_folder_path: The path to the folder where you want to store restructured output files. This folder doesn’t need to exist beforehand—the script will create it if needed.
- api_key: The API key for your Azure OpenAI resource.
- azure_endpoint: Your Azure OpenAI resourc endpoint url.
- field_mapping_file_path: the full file path for `field_mapper.csv`.

### 6. Run Project

Run the main script from the project root using:

```bash
python -m src.main
```

Run the GUI for the project using:
```bash
Powershell: .venv/Scripts/activate 
CMD: set PYTHONPATH=.

streamlit run src/app.py
```

## Troubleshooting

- Make sure you're running the script from the project root, not from within src/.
- Ensure settings.json is correctly formatted JSON and contains all required keys.
- Check the output/logs/ folder for any runtime errors or stack traces.

