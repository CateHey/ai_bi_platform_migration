import io, csv, json, os, shutil, time
import hashlib
import fitz
import pandas as pd
import requests
from pathlib import Path
from urllib.parse import quote
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
LOGS_DIR = PROJECT_ROOT / "output" / "logs"

# ====================================
# Settings & File I/O
# ====================================
def load_settings(settings_file="../settings.json"):
    config = {}
    if os.path.exists(settings_file):
        with open(settings_file, "r") as f:
            config = json.load(f)

    # Specify required keys and prompt for missing values
    required_keys = [
        "DOCUMENT_ANALYZER_PATH",
        "local_folder_path",
        "root_folder_path",
        "assets_folder_path",
        "output_qv_folder_path",
        "output_qv_restructured_folder_path",
        "api_key",
        "azure_endpoint",
        "field_mapping_file_path",
    ]

    for key in required_keys:
        if key not in config or not config[key]:
            user_value = input(f"Enter value for {key}: ").strip()
            config[key] = user_value

    return config

def format_csv_row(row_list):
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(row_list)
    return output.getvalue().strip()

def read_file(file_path, encoding, logger):
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File {file_path} not found.")
        with open(file_path, 'r', encoding=encoding) as file:
            content = file.read()
        logger.info(f"Successfully read file: {file_path}")
        return content
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return None
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return None

def process_files_by_name(root_folder_path, target_filename, encoding, logger):
    """
    Walk through all folders under root_folder_path and call read_file
    whenever a file with target_filename is found.
    """
    file_contents = {}  # Dictionary to store file paths and their contents

    for dirpath, _, filenames in os.walk(root_folder_path):
        for filename in filenames:
            if filename.lower() == target_filename.lower():
                file_path = os.path.join(dirpath, filename)
                logger.info(f"Found {target_filename} file: {file_path}")
                content = read_file(file_path, encoding, logger)
                if content:
                    file_contents[file_path] = content

    if not file_contents:
        message = f"No '{target_filename}' files found in '{output_qv_restructured_folder_path}'."
        logger.error(message)
        raise FileNotFoundError(message)

    return file_contents

def read_csv_flexible_encoding(path):
    try:
        return pd.read_csv(path, encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return pd.read_csv(path, encoding="utf-16")
        except UnicodeDecodeError:
            return pd.read_csv(path, encoding="latin-1")

# ====================================
# Caching
# ====================================
def get_file_hash(file_path: Path, algo: str = "sha256") -> str:
    """Calculate the hash of a file using the given algorithm."""
    hasher = hashlib.new(algo)
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def load_qvw_cache(cache_path) -> dict:
    """Load the QVW metadata cache from disk."""
    cache_path = Path(cache_path)
    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_qvw_cache(cache_path: Path, data: dict):
    """Save the QVW metadata cache to disk."""
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def should_process_qvw(file_path: Path, cache: dict, relative_to: Path) -> bool:
    file_str = str(file_path.relative_to(relative_to))
    current_stat = file_path.stat()
    cached_entry = cache.get(file_str)

    if not cached_entry:
        return True  # New file, process it

    # Compare timestamps first (fast check)
    if current_stat.st_mtime == cached_entry.get("last_modified"):
        return False  # No change

    # Timestamp changed → now check hash to confirm
    current_hash = get_file_hash(file_path)
    return current_hash != cached_entry.get("hash")

def update_qvw_cache_entry(file_path: Path, cache: dict, relative_to: Path):
    file_str = str(file_path.relative_to(relative_to))
    cache[file_str] = {
        "hash": get_file_hash(file_path),
        "last_modified": file_path.stat().st_mtime
    }

# ====================================
# Folder management
# ====================================
# Function to ignore files in the directory
def ignore_files(dir, files):
    return [f for f in files if os.path.isfile(os.path.join(dir, f))]

# Function to create a restructured folder by copying the root folder
def create_restructured_folder(root_folder_path, output_qv_restructured_folder_path, overwrite_existing, logger):
    shutil.copytree(root_folder_path, output_qv_restructured_folder_path,
                    ignore=ignore_files, dirs_exist_ok=True)

def copy_output_to_restructured_by_source_structure(root_folder: Path, metadata_folder: Path, metadata_folder_input: Path, logger, overwrite_existing=False):
    try:
        # Clear the entire restructured folder if overwrite is True
        if overwrite_existing and metadata_folder.exists():
            try:
                logger.info(f"Overwrite enabled - removing existing restructured folder: {metadata_folder}")
                shutil.rmtree(metadata_folder)
                logger.info(f"Deleted: {metadata_folder}")
            except Exception:
                raise

        source_output_folder = metadata_folder_input
        destination_folder = metadata_folder

        if not (source_output_folder.exists() and source_output_folder.is_dir()):
            msg = (
                f"DocumentAnalyzer output folder not found at {source_output_folder}. "
                f"Check that 'output_qv_folder_path' in settings.json matches where "
                f"DocumentAnalyzer actually writes its CSVs."
            )
            logger.error(msg)
            raise FileNotFoundError(msg)

        destination_folder.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_output_folder, destination_folder, dirs_exist_ok=True)
        logger.info(f"Copied {source_output_folder} to {destination_folder}")
    except Exception:
            raise

def validate_output_folder(source_folder_path, output_folder_path):
    """
    Validates that all QVW files in the source folder have corresponding processed outputs
    in the restructured folder, preserving the folder structure.

    Args:
        source_folder_path (str): Path to the source folder containing QVW files
        output_folder_path (str): Path to the restructured output folder

    Returns:
        tuple: (bool, list) - (validation result, list of missing/invalid folders)
    """
    missing_outputs = []
    source_path = Path(source_folder_path)
    output_path = Path(output_folder_path)

    # Validate the source and output folders exist
    if not source_path.exists():
        return False, ["Source folder does not exist"]
    if not output_path.exists():
        return False, ["Output folder does not exist"]

    # Get all relative paths of QVW files (minus .qvw extension)
    source_qvw_relative_paths = {
        file.relative_to(source_path).with_suffix('') for file in source_path.rglob("*.qvw")
    }

    # Check if each corresponding folder exists in the output path
    for rel_path in source_qvw_relative_paths:
        expected_output_folder = output_path / rel_path
        if not expected_output_folder.is_dir():
            missing_outputs.append(f"Missing output folder for QVW file: {rel_path}")

    validation_passed = len(missing_outputs) == 0
    return validation_passed, missing_outputs

def handle_incorrect_extracting(root_folder, logger):
    missing_logs = []
    output_log = LOGS_DIR / "incorrect_extracting_logs.log"

    for dirpath, _, filenames in os.walk(root_folder):
        if "DocumentAnalyzerExtract.log" in filenames:
            log_path = Path(dirpath) / "DocumentAnalyzerExtract.log"
            try:
                with log_path.open("r", encoding="utf-16") as f:
                    content = f.read()
                    if "extracting" not in content.lower():
                        missing_logs.append(str(log_path))

            except Exception as e:
                logger.warning(f"Error reading {log_path}: {e}")

    with output_log.open("w", encoding="utf-8") as f:
        for path in missing_logs:
            f.write(f"{path}\n")

    logger.info(f"Scan complete. {len(missing_logs)} logs without proper extraction written to {output_log}")

# ====================================
# PDF processing
# ====================================
def wait_for_pdf_stable_size(path, logger=None, timeout=5000, check_interval=5, required_stable_checks=3):

    stable_checks = 0
    last_size = -1
    start_time = time.time() + 10

    while time.time() - start_time < timeout:
        if not os.path.exists(path):
            if logger:
                logger.debug("PDF not found yet.")
            stable_checks = 0
            last_size = -1
        else:
            current_size = os.path.getsize(path)

            if current_size == 0:
                if logger:
                    logger.debug("PDF exists but is still 0 bytes.")
                stable_checks = 0
                last_size = 0
            elif current_size == last_size:
                stable_checks += 1
                if logger:
                    logger.debug(f" PDF size stable at {current_size} bytes ({stable_checks}/{required_stable_checks})")
                if stable_checks >= required_stable_checks:
                    if logger:
                        logger.info(f"PDF is ready and stable: {path}")
                    return True
            else:
                if logger:
                    logger.debug(f"PDF size changed: {last_size} -> {current_size}. Resetting stability check.")
                stable_checks = 1
                last_size = current_size

        time.sleep(check_interval)

    if logger:
        logger.warning(f"Timed out after {timeout} seconds waiting for PDF: {path}")
    return False

def split_pdf_by_sheets(pdf_path, sheets_csv_path, output_folder, logger):
    """
    Splits the given PDF into individual pages using sheet names from CSV.
    Each page is saved as '{index}_{SheetName}.pdf' in output_folder.
    """
    output_folder = Path(output_folder)
    os.makedirs(output_folder, exist_ok=True)

    # Load sheet names
    try:
        sheets_df = pd.read_csv(
            sheets_csv_path,
            encoding="utf-16",
            sep=",",
            quotechar='"',
            engine="python"
        )
        sheets_df.columns = [col.strip().replace('\ufeff', '') for col in sheets_df.columns]
    except Exception as e:
        logger.error(f"Error reading sheets.csv for {report_name}: {e}")
        raise

    if "SheetName" not in sheets_df.columns:
        logger.error(f"'SheetName' column not found in {sheets_csv_path}. Found columns: {sheets_df.columns.tolist()}")
        raise KeyError("'SheetName' column missing in sheets.csv")

    sheet_names = sheets_df["SheetName"].fillna("Unnamed").tolist()

    # Convert PDF pages to images
    doc = fitz.open(pdf_path)
    # Save each page as PNG
    page_metadata = []

    try:
        for i, page in enumerate(doc, start=0):
            sheet_name = sheet_names[i] if i < len(sheet_names) else f"Page{i+1}"
            clean_name = sheet_name.strip().replace(" ", "_").replace("/", "_")
            output_png = output_folder / f"{i+1:02d}_{clean_name}.png"

            try:
                # 1. Render PDF page to image (fitz pixmap)
                pix = page.get_pixmap(dpi=300)
                full_width_px = pix.width
                full_height_px = pix.height

                # 2. Convert to PIL Image for analysis
                image_bytes = pix.tobytes("png")
                image_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")

                # 3. Detect background color (usually white)
                bg_color = image_pil.getpixel((0, 0))
                img_rgba = image_pil.convert("RGBA")
                datas = img_rgba.getdata()

                # 4. Make background transparent
                tolerance = 5
                new_data = []
                for item in datas:
                    r, g, b, a = item
                    if abs(r - bg_color[0]) <= tolerance and abs(g - bg_color[1]) <= tolerance and abs(b - bg_color[2]) <= tolerance:
                        new_data.append((255, 255, 255, 0))  # transparent
                    else:
                        new_data.append((r, g, b, 255))
                img_rgba.putdata(new_data)

                # 5. Get content bounding box
                bbox = img_rgba.getbbox()

                if bbox:
                    x0, y0, x1, y1 = bbox
                    content_width = x1 - x0
                    content_height = y1 - y0

                    # 6. Relative position
                    rel_x = x0 / full_width_px
                    rel_y = y0 / full_height_px
                    rel_w = content_width / full_width_px
                    rel_h = content_height / full_height_px

                    # 7. Crop and save
                    cropped_img = image_pil.crop(bbox)
                    cropped_img.save(output_png)
                    logger.info(f"Saved cropped image: {output_png}")
                    print(f"Saved: {output_png} | {content_width}×{content_height} px")

                    # 8. Save metadata
                    page_metadata.append({
                        "page": i + 1,
                        "sheet_name": sheet_name,
                        "file_name": output_png.name,
                        "full_size_px": [full_width_px, full_height_px],
                        "content_bbox_px": [x0, y0, x1, y1],
                        "content_size_px": [content_width, content_height],
                        "content_size_cm": [
                            round(content_width / 300 * 2.54, 2),
                            round(content_height / 300 * 2.54, 2)
                        ],
                        "relative_position": {
                            "x": round(rel_x, 3),
                            "y": round(rel_y, 3),
                            "width": round(rel_w, 3),
                            "height": round(rel_h, 3)
                        }
                    })
                else:
                    logger.warning(f"No content detected in page {i+1}. Skipping crop.")
                    image_pil.save(output_png)

            except Exception as e:
                logger.error(f"Failed to process page {i+1}: {e}")

        # Write metadata at the end
        metadata_path = output_folder / "page_dimensions.json"
        with open(metadata_path, "w") as f:
            json.dump(page_metadata, f, indent=2)
        logger.info(f"Saved page metadata to {metadata_path}")

    except Exception as e:
        logger.error(f"Failed to convert PDF to images: {e}")
        return

# ====================================
# SharePoint
# ====================================
def recursively_upload_folder_to_sharepoint(local_dir: Path, remote_dir: str, cookies: dict, logger) -> bool:
    """
    Recursively creates folders and uploads files from local_dir to remote_dir on SharePoint.

    Args:
        local_dir (Path): Root local directory to walk through.
        remote_dir (str): Root SharePoint relative path (e.g. "/Shared Documents/…").
        cookies (dict): Dictionary with "FedAuth" and "rtFa" cookies.
        logger: Logger instance for debug output.

    Returns:
        bool: True if all uploads succeeded, False otherwise.
    """
    try:
        # Get x-requestdigest token
        digest_response = requests.post(
            "https://one51comau.sharepoint.com/_api/contextinfo",
            headers={"Accept": "application/json;odata=verbose"},
            cookies=cookies,
        )
        if digest_response.status_code != 200:
            logger.error("X Failed to get x-requestdigest.")
            return False

        digest = digest_response.json()['d']['GetContextWebInformation']['FormDigestValue']
        logger.info("OK Obtained x-requestdigest.")

        for root, dirs, files in os.walk(local_dir):
            relative_path = Path(root).relative_to(local_dir)
            sp_folder_path = Path(remote_dir) / relative_path
            sp_folder_url = str(sp_folder_path).replace("\\", "/")

            # STEP 1: Ensure folder exists
            created = create_sharepoint_folder(sp_folder_url, cookies, digest, logger)
            if not created:
                logger.warning(f" Could not create folder: {sp_folder_url}")

            # STEP 2: Upload all files in this folder
            for file_name in files:
                local_file_path = Path(root) / file_name
                sp_file_path = f"{sp_folder_url}/{file_name}"
                uploaded = upload_file_to_sharepoint(local_file_path, sp_folder_url, file_name, cookies, digest, logger)
                if not uploaded:
                    logger.error(f"X Failed to upload {file_name} to {sp_file_path}")
                else:
                    logger.info(f"OK Uploaded: {file_name} → {sp_file_path}")

        return True

    except Exception as e:
        logger.exception(f" Unexpected error in recursive upload: {e}")
        return False

def get_sharepoint_digest(cookies: dict) -> str:
    try:
        resp = requests.post(
            'https://one51comau.sharepoint.com/_api/contextinfo',
            headers={'Accept': 'application/json;odata=verbose'},
            cookies=cookies
        )
        if resp.status_code == 200:
            return resp.json()['d']['GetContextWebInformation']['FormDigestValue']
    except Exception as e:
        print(f"Error getting digest: {e}")
    return None

def upload_file_to_sharepoint(local_file_path: Path, sp_folder_url: str, file_name: str,
                              cookies: dict, digest: str, logger) -> bool:
    """
    Uploads a file to a SharePoint folder.
    """
    encoded_folder = quote(sp_folder_url)
    encoded_file = quote(file_name)
    url = (
        f"https://one51comau.sharepoint.com/_api/web/"
        f"GetFolderByServerRelativePath(DecodedUrl='{encoded_folder}')"
        f"/Files/AddUsingPath(DecodedUrl='{encoded_file}',Overwrite=true)"
    )

    try:
        with open(local_file_path, "rb") as f:
            file_bytes = f.read()

        response = requests.post(
            url,
            headers={
                'Accept': 'application/json;odata=verbose',
                'Content-Type': 'application/octet-stream',
                'x-requestdigest': digest,
            },
            cookies=cookies,
            data=file_bytes
        )

        return response.status_code in [200, 201]

    except Exception as e:
        logger.exception(f"❌ Error uploading file {file_name}: {e}")
        return False

def create_sharepoint_folder(folder_path: str, cookies: dict, digest: str, logger) -> bool:
    """
    Creates a folder in SharePoint if it doesn't exist.
    """
    encoded_path = quote(folder_path)
    url = f"https://one51comau.sharepoint.com/_api/web/folders/AddUsingPath(DecodedUrl='{encoded_path}',overwrite=true)"

    response = requests.post(
        url,
        headers={
            'Accept': 'application/json;odata=verbose',
            'Content-Type': 'application/json;odata=verbose',
            'x-requestdigest': digest,
        },
        cookies=cookies
    )

    if response.status_code in [200, 201]:
        return True
    elif "already exists" in response.text:
        return True
    else:
        logger.warning(f"⚠️ Failed to create folder {folder_path}: {response.status_code}")
        return False

def upload_qvw_stream(filename: str, file_bytes: bytes, cookies: dict, digest: str, logger) -> bool:
    folder_path = "/Shared Documents/MigrationQlikFabric/input_qvw_samples"

    upload_url = (
        "https://one51comau.sharepoint.com/_api/web/"
        f"GetFolderByServerRelativePath(DecodedUrl=@a1)/Files/AddUsingPath("
        f"DecodedUrl=@a2,AutoCheckoutOnInvalidData=@a3)?"
        f"@a1='{folder_path}'&@a2='{filename}'&@a3=true"
    )

    try:
        response = requests.post(
            upload_url,
            headers={
                "Accept": "application/json;odata=verbose",
                "Content-Type": "application/octet-stream",
                "x-requestdigest": digest,
            },
            cookies=cookies,
            data=file_bytes,
        )

        if response.status_code == 200:
            logger.info(f"✅ Uploaded '{filename}' to SharePoint.")
            return True
        else:
            logger.error(f"❌ Upload failed ({response.status_code}): {response.text}")
            return False

    except Exception as e:
        logger.exception(f"❌ Exception during upload: {e}")
        return False
