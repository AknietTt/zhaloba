import os
import re
from typing import Optional

from PIL import Image

try:
    from pyzbar.pyzbar import decode as qr_decode
except Exception:
    qr_decode = None
  
try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    from pdf2image import convert_from_path
except Exception:
    convert_from_path = None

try:
    import PyPDF2
except Exception:
    PyPDF2 = None

try:
    import openpyxl
except Exception:
    openpyxl = None

try:
    import xlrd
except Exception:
    xlrd = None

XLS_PATH = os.path.join(os.path.dirname(__file__), 'QR-код на ТС.xls')
XLSX_PATH = os.path.join(os.path.dirname(__file__), 'qr_codes.xlsx')


def _load_bus_rows():
    """Load rows from XLS or XLSX. Returns list of row value lists."""
    if xlrd and os.path.exists(XLS_PATH):
        wb = xlrd.open_workbook(XLS_PATH)
        sheet = wb.sheet_by_index(0)
        return [sheet.row_values(i) for i in range(sheet.nrows)]
    if openpyxl and os.path.exists(XLSX_PATH):
        wb = openpyxl.load_workbook(XLSX_PATH, read_only=True)
        sheet = wb.active
        return [[cell for cell in row] for row in sheet.iter_rows(values_only=True)]
    return []


def _extract_number_from_image(path: str) -> Optional[str]:
    # Try QR decode first
    try:
        if qr_decode:
            img = Image.open(path)
            decoded = qr_decode(img)
            for d in decoded:
                try:
                    text = d.data.decode(errors='ignore')
                except Exception:
                    continue
                m = re.search(r"(\d{5})", text)
                if m:
                    return m.group(1)
    except Exception:
        pass

    # Fallback to OCR
    if pytesseract:
        try:
            img = Image.open(path)
            text = pytesseract.image_to_string(img, lang='eng+rus')
            result = _extract_transport_number(text)
            if result:
                return result
        except Exception:
            pass

    return None


def _extract_transport_number(text: str) -> Optional[str]:
    """
    Extract transport number from receipt text.
    Priority:
      1. 'Номер транспорта' / 'Транспорт нөмірі' field — value on same OR next line
      2. Standalone 5-digit number that is NOT a substring of a longer number
    """
    # Halyk Bank: label and value can be on same line or next line
    m = re.search(
        r'(?:Номер\s+транспорта|Транспорт\s+н[өо]м[іи]р[іи])'
        r'[\s\S]{0,30}?(?<!\d)(\d{4,6})(?!\d)',
        text, re.IGNORECASE
    )
    if m:
        return m.group(1)

    # Generic: find all standalone 5-digit numbers, return last one
    # (transport numbers usually appear near the bottom of the receipt)
    matches = re.findall(r'(?<!\d)(\d{5})(?!\d)', text)
    if matches:
        return matches[-1]

    return None


def _extract_number_from_pdf(path: str) -> Optional[str]:
    if PyPDF2 is not None:
        try:
            with open(path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                pages_text = []
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        pages_text.append(page_text)
                if pages_text:
                    full_text = '\n'.join(pages_text)
                    result = _extract_transport_number(full_text)
                    if result:
                        return result
        except Exception:
            pass
    return None


def find_bus_entry(number: str, excel_path: str = None) -> Optional[dict[str, str]]:
    """
    Search bus by QR-code number (col 8, 'Код ЛРТ') or garage number (col 1, 'Код').
    XLS columns: [0]=empty, [1]=Гараж.№, [2]=Наименование, [3]=Марка, [4]=Гос.номер, [5]=Колонна, [8]=Код ЛРТ
    """
    try:
        rows = _load_bus_rows()
        num_str = str(number).strip()
        num_float = None
        try:
            num_float = float(number)
        except Exception:
            pass

        for row in rows:
            if not row or len(row) < 2:
                continue
            garage = str(row[1]).strip() if row[1] is not None else ''
            qr_code = row[8] if len(row) > 8 else None

            # Match by QR code (col 8)
            qr_match = (
                qr_code is not None and (
                    (isinstance(qr_code, float) and qr_code == num_float) or
                    str(qr_code).strip().replace('.0', '') == num_str
                )
            )
            # Match by garage number (col 1)
            garage_match = garage == num_str or garage.replace(' ', '') == num_str

            if qr_match or garage_match:
                plate = str(row[4]).strip() if len(row) > 4 and row[4] else ''
                make  = str(row[3]).strip() if len(row) > 3 and row[3] else ''
                name  = str(row[2]).strip() if len(row) > 2 and row[2] else ''
                col   = str(row[5]).strip() if len(row) > 5 and row[5] else ''
                return {
                    'garage_number': garage,
                    'name': name,
                    'make': make,
                    'plate': plate,
                    'column': col,
                    'raw': f"{garage} | {name} | {make} | {plate} | {col}",
                }
    except Exception:
        pass
    return None


def format_bus_info(entry: dict[str, str] | None) -> Optional[str]:
    if not entry:
        return None
    parts = []
    if entry.get('garage_number'):
        parts.append(f"Гараж: {entry['garage_number']}")
    if entry.get('plate'):
        parts.append(f"Гос: {entry['plate']}")
    if entry.get('make'):
        parts.append(f"Модель: {entry['make']}")
    if entry.get('column'):
        parts.append(f"Колонна: {entry['column']}")
    if parts:
        return ' · '.join(parts)
    return entry.get('raw')


def find_bus_by_plate(plate: str) -> Optional[dict[str, str]]:
    """Search bus by license plate (col 4 in XLS)."""
    import re as _re
    plate_norm = _re.sub(r'[\s\-]', '', plate).upper()
    # Normalize Cyrillic А/В/Е/К/М/Н/О/Р/С/Т/Х to Latin lookalikes for comparison
    _cyr_to_lat = str.maketrans('АВЕКМНОРСТХ', 'ABEKMNOPCTX')
    plate_norm_lat = plate_norm.translate(_cyr_to_lat)

    try:
        rows = _load_bus_rows()
        for row in rows:
            if not row or len(row) < 5:
                continue
            raw_plate = str(row[4]).strip() if row[4] else ''
            rp_norm = _re.sub(r'[\s\-]', '', raw_plate).upper().translate(_cyr_to_lat)
            if rp_norm == plate_norm_lat:
                garage = str(row[1]).strip() if row[1] is not None else ''
                make   = str(row[3]).strip() if len(row) > 3 and row[3] else ''
                name   = str(row[2]).strip() if len(row) > 2 and row[2] else ''
                col    = str(row[5]).strip() if len(row) > 5 and row[5] else ''
                return {
                    'garage_number': garage,
                    'name': name,
                    'make': make,
                    'plate': raw_plate,
                    'column': col,
                    'raw': f"{garage} | {name} | {make} | {raw_plate} | {col}",
                }
    except Exception:
        pass
    return None


def find_bus(number: str, excel_path: str = 'qr_codes.xlsx') -> Optional[str]:
    entry = find_bus_entry(number, excel_path=excel_path)
    return format_bus_info(entry) if entry else None


def process_receipt(path: str, excel_path: str = 'qr_codes.xlsx') -> tuple[Optional[str], Optional[str], Optional[dict[str, str]]]:
    img_path = path
    tmp_generated = None
    number = None
    entry = None
    if path.lower().endswith('.pdf'):
        number = _extract_number_from_pdf(path)
        if number:
            entry = find_bus_entry(number, excel_path=excel_path)
            return number, format_bus_info(entry), entry
        if convert_from_path:
            try:
                pages = convert_from_path(path, first_page=1, last_page=1)
                if pages:
                    tmp_generated = path + '.page0.png'
                    pages[0].save(tmp_generated, 'PNG')
                    img_path = tmp_generated
            except Exception:
                img_path = path  # fall back; will likely fail

    number = _extract_number_from_image(img_path)
    bus = None
    if number:
        entry = find_bus_entry(number, excel_path=excel_path)
        bus = format_bus_info(entry)

    # cleanup
    if tmp_generated and os.path.exists(tmp_generated):
        try:
            os.remove(tmp_generated)
        except Exception:
            pass

    return number, bus, entry
